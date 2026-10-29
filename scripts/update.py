#!/usr/bin/env python3
"""RHEA 台股官方外部行情蒐集中心 v1.0。僅蒐集公開日資料；不下單、不修改私有檔案。

設計紅線：失敗、兩市場日期不一致或名冊不完整時，不寫入正式輪動快照。
"""
from __future__ import annotations
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DAILY = DATA / 'daily'
THEMES = ROOT / 'config' / 'themes.json'
TWN = timezone(timedelta(hours=8))
SOURCES = {
    'TWSE_daily': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    'TPEx_daily': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
    'TPEx_daily_backup': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes',
    'TWSE_companies': 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L',
    'TPEx_companies': 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O',
    'TWSE_notice': 'https://openapi.twse.com.tw/v1/announcement/notice',
    'TWSE_disposal': 'https://openapi.twse.com.tw/v1/announcement/punish',
    'TPEx_notice': 'https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information',
    'TPEx_disposal': 'https://www.tpex.org.tw/openapi/v1/tpex_disposal_information',
}
INDUSTRIES = {
    '01':'水泥','02':'食品','03':'塑膠','04':'紡織纖維','05':'電機機械','06':'電器電纜',
    '08':'玻璃陶瓷','09':'造紙','10':'鋼鐵','11':'橡膠','12':'汽車','14':'建材營造',
    '15':'航運','16':'觀光餐旅','17':'金融保險','18':'貿易百貨','20':'其他',
    '21':'化學','22':'生技醫療','23':'油電燃氣','24':'半導體','25':'電腦及週邊設備',
    '26':'光電','27':'通信網路','28':'電子零組件','29':'電子通路','30':'資訊服務','31':'其他電子',
    '32':'文化創意','33':'農業科技','34':'電子商務','35':'綠能環保',
}

def now_iso(): return datetime.now(TWN).isoformat(timespec='seconds')

def fetch_json(url, timeout=28, attempts=2):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent':'Mozilla/5.0 (compatible; RHEA-public-market-research/1.0)',
                'Accept':'application/json', 'Cache-Control':'no-cache'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200: raise ValueError('HTTP status: '+str(r.status))
                b=r.read(20_000_001)
                if len(b)>20_000_000: raise ValueError('excessive payload')
            res=json.loads(b.decode('utf-8-sig'))
            if not isinstance(res, list): raise ValueError('API response is not an array')
            return res
        except (ValueError,UnicodeError,urllib.error.URLError,TimeoutError) as e:
            last=e
            if i+1<attempts: time.sleep(1.5)
    raise RuntimeError(f'official feed unavailable: {url}: {last}')

def fetch_tpex_quotes():
    """Use only official quote endpoints; validate the backup independently.

    Never repair malformed JSON by guessing or silently skipping broken lines.
    This second endpoint is separately documented by TPEx as daily close quotes.
    """
    problems=[]
    for key in ('TPEx_daily','TPEx_daily_backup'):
        url=SOURCES[key]
        try:
            rows=fetch_json(url)
            day=qdate(rows)
            valid=normalize(rows,'TPEx')
            if len(valid)<600:
                raise ValueError(f'quote coverage insufficient: {len(valid)}')
            return rows, key, day
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            problems.append(f'{key}: {str(exc)[:230]}')
    raise RuntimeError('TPEx primary and backup both failed; '+ ' | '.join(problems))


def num(x):
    if x is None: return None
    s=str(x).strip().replace(',','').replace('＋','+').replace('－','-').replace('−','-').replace(' ','')
    if s in ('','--','---','-','—','N/A','X','除權息','暫停交易'): return None
    if s.startswith('▲'): s='+'+s[1:]
    if s.startswith('▼'): s='-'+s[1:]
    # X or other corporate-action text is deliberately skipped
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',s): return None
    try:
        v=float(s)
        return v if math.isfinite(v) else None
    except ValueError: return None

def iso_date(x):
    s=str(x).strip().replace('-','').replace('/','')
    if re.fullmatch(r'\d{7}',s): s=str(int(s[:3])+1911)+s[3:]
    if not re.fullmatch(r'\d{8}',s): raise ValueError(f'invalid official date {x!r}')
    return datetime.strptime(s,'%Y%m%d').date().isoformat()

def qdate(rows):
    if not isinstance(rows,list) or len(rows)<100: raise ValueError('price rows insufficient (<100)')
    sample=rows[:min(60,len(rows))]
    dates=[iso_date(r['Date']) for r in sample if isinstance(r,dict) and r.get('Date')]
    if len(dates)<40 or len(set(dates))!=1: raise ValueError('price data dates missing/mixed')
    return dates[0]

def normalize(rows, market):
    out={}
    for r in rows:
        if not isinstance(r,dict): continue
        code=str(r.get('Code') if market=='TWSE' else r.get('SecuritiesCompanyCode','')).strip()
        if not re.fullmatch(r'\d{4}', code) or code.startswith('0'): continue
        name=str(r.get('Name') if market=='TWSE' else r.get('CompanyName','')).strip()
        price=num(r.get('ClosingPrice') if market=='TWSE' else r.get('Close'))
        change=num(r.get('Change'))
        amount=num(r.get('TradeValue') if market=='TWSE' else r.get('TransactionAmount'))
        if price is None or change is None or price<=0 or price-change<=0: continue
        pct=100*change/(price-change)
        if not -22<pct<22: continue
        out[code]={'code':code,'name':name,'market':market,'pct':round(pct,4),
                   'amount':round(amount,2) if amount is not None and amount>=0 else None}
    return out

def companies(rows, market):
    out={}
    for r in rows:
        if not isinstance(r,dict): continue
        code=str(r.get('公司代號') if market=='TWSE' else r.get('SecuritiesCompanyCode','')).strip()
        if not re.fullmatch(r'\d{4}',code): continue
        ind=str(r.get('產業別') if market=='TWSE' else r.get('SecuritiesIndustryCode','')).strip()
        if not ind: continue
        out[code]={'industry':ind.zfill(2),'market':market}
    if len(out)<300: raise ValueError(f'{market} company roster insufficient ({len(out)})')
    return out

def daily_result(day, quote_by_market, catalog_by_market, groups):
    # Keep market identity even if duplicated codes appear in either source.
    stocks={}
    for market in ('TWSE','TPEx'):
        quotes=quote_by_market[market]; catalog=catalog_by_market[market]
        for c,v in quotes.items():
            if c in catalog: stocks[(market,c)]={**v,'industry':catalog[c]['industry']}
    eligible={}
    for (market,c),s in stocks.items():
        industry=s['industry']; k='official-'+industry
        g=eligible.setdefault(k,{'name':INDUSTRIES.get(industry,'產業代碼 '+industry),
                                 'type':'official','codes':[], 'min_n':5})
        g['codes'].append((market,c))
    for g in groups:
        k=g['id']; eligible[k]={'name':g['name'],'type':'custom','codes':[],
                               'min_n':g['min_n'],'basket_n':len(g['members'])}
        for market in ('TWSE','TPEx'):
            for c in g['members']:
                if (market,c) in stocks: eligible[k]['codes'].append((market,c))
    results={}
    for k,g in eligible.items():
        a=[stocks[c] for c in g['codes'] if c in stocks]
        if len(a)<g['min_n']: continue
        ret=sum(s['pct'] for s in a)/len(a)
        a_sorted=sorted(a,key=lambda s:(-s['pct'],s['code']))
        n=len(a)
        results[k]={
            'name':g['name'],'type':g['type'],'n':n,'basket_n':g.get('basket_n',n),
            'avg':round(ret,3), 'up':sum(s['pct']>0 for s in a),
            'breadth':round(100*sum(s['pct']>0 for s in a)/n,1),
            'amount_100m':round(sum(s['amount'] or 0 for s in a)/100_000_000,2),
            'leaders':[{'code':s['code'],'name':s['name'],'pct':round(s['pct'],2)} for s in a_sorted[:5]],
            'members':[{'code':s['code'],'name':s['name'],'pct':round(s['pct'],2),'market':s['market']} for s in a_sorted]}
    for typ in ('official','custom'):
        ranking=sorted(((k,s) for k,s in results.items() if s['type']==typ),
                       key=lambda kv:(-kv[1]['avg'],kv[0]))
        for rank,(_,s) in enumerate(ranking,1): s['rank']=rank
    return {'date':day,'coverage':{
        'TWSE':sum(k[0]=='TWSE' for k in stocks),
        'TPEx':sum(k[0]=='TPEx' for k in stocks)},'sectors':results}

def build_dashboard():
    valid=[]
    for file in sorted(DAILY.glob('????-??-??.json'))[-40:]:
        try:
            row=json.loads(file.read_text(encoding='utf-8'))
            if row.get('date')==file.stem and row.get('sectors') and row.get('coverage'):
                valid.append(row)
        except (OSError, ValueError, TypeError): pass
    five=valid[-5:]
    if not five: return {'status':'awaiting_data','dates':[],'days':[],
                         'notice':'尚無經兩市同日核驗的真實行情；不可展示示範數字作實況。'}
    return {'status':'ok','generated_at':now_iso(),'dates':[x['date'] for x in five],
            'days':five, 'coverage':five[-1]['coverage'],
            'theme_version':json.loads(THEMES.read_text('utf-8'))['version'],
            'sources':{k:v for k,v in SOURCES.items() if k in ('TWSE_daily','TPEx_daily','TWSE_companies','TPEx_companies')},
            'actual_quote_sources':five[-1].get('quote_sources',{}),
            'method':'每日個股收盤相對當日參考價的變化百分比等權；不是開盤放空至13:30的ROI，也未做除權息復權；自訂族群僅固定觀察籃。'}

def save_json(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(p)

def notices(rows, market, label):
    if not isinstance(rows,list): raise ValueError('announcement schema invalid')
    out=[]
    for r in rows[:250]:
        if not isinstance(r,dict): continue
        # Display source fields without inferring trade/settlement rules.
        code=''
        for field in ('證券代號','股票代號','代號','Code','SecuritiesCompanyCode','SecuritiesCode','SecurityCode'):
            v=str(r.get(field,'')).strip()
            if re.fullmatch(r'\d{4}',v): code=v;break
        if not code: continue
        name=next((str(r[k]).strip() for k in ('證券名稱','股票名稱','名稱','Name','CompanyName','SecuritiesName') if r.get(k)), '')
        day=next((str(r[k]).strip() for k in ('日期','公告日期','處置開始日期','公告日','Date','PublishDate','DisposalDate') if r.get(k)), '')
        out.append({'code':code,'name':name,'raw_date':day,'market':market,'type':label})
        if len(out)>=60:break
    return out

def update():
    DATA.mkdir(exist_ok=True);DAILY.mkdir(exist_ok=True)
    events=[]
    try:
        raw={'TWSE_daily':fetch_json(SOURCES['TWSE_daily'])}
        raw['TPEx_daily'],tpex_feed,tpex_day=fetch_tpex_quotes()
        for key in ('TWSE_companies','TPEx_companies'):
            raw[key]=fetch_json(SOURCES[key])
        days={'TWSE':qdate(raw['TWSE_daily']),'TPEx':tpex_day}
        if days['TWSE']!=days['TPEx']: raise ValueError(f'TWSE/TPEx different dates: {days}')
        day=days['TWSE']
        tdate=date.fromisoformat(day); today=datetime.now(TWN).date()
        if tdate>today: raise ValueError('future trading date in official feed')
        if (today-tdate).days>10: raise ValueError(f'official market snapshot too stale: {day}')
        qs={m:normalize(raw[f'{m}_daily'],m) for m in ('TWSE','TPEx')}
        cs={m:companies(raw[f'{m}_companies'],m) for m in ('TWSE','TPEx')}
        if len(qs['TWSE'])<800 or len(qs['TPEx'])<600: raise ValueError(f'quote coverage insufficient {len(qs["TWSE"])}+{len(qs["TPEx"])}')
        theme=json.loads(THEMES.read_text(encoding='utf-8'))
        record=daily_result(day,qs,cs,theme['groups'])
        record['quote_sources']={'TWSE':SOURCES['TWSE_daily'],'TPEx':SOURCES[tpex_feed]}
        if record['coverage']['TWSE']<800 or record['coverage']['TPEx']<600:
            raise ValueError(f'catalog matched coverage insufficient {record["coverage"]}')
        if len([k for k in record['sectors'] if k.startswith('official-')])<15:
            raise ValueError('too few official industries')
        target=DAILY/(day+'.json')
        save_json(target,record)
        dashboard=build_dashboard()
        save_json(DATA/'dashboard.json',dashboard)
        events.append('TWSE/TPEx同日報價、公司名冊及覆蓋率驗證通過')
        if tpex_feed=='TPEx_daily_backup':
            events.append('櫃買主要端點失效；已改用官方備援收盤行情且通過格式/覆蓋率/同日檢查')
        outcome='ok' if tdate==today else 'stale'
        if outcome=='stale': events.append('API仍停留於'+day+'，網頁顯示實際資料日')
        # Optional announcement feeds do not block valid daily-price snapshots.
        alerts={'as_of_fetch':now_iso(),'items':{},'errors':{}}
        for market in ('TWSE','TPEx'):
            for typ in ('notice','disposal'):
                key=market+'_'+typ
                try:
                    feed=fetch_json(SOURCES[key],attempts=1)
                    parsed=notices(feed,market,typ)
                    alerts['items'][key]={'source':SOURCES[key],'count_parsed':len(parsed),'rows':parsed,
                                           'note':'官方公告快照；日期與適用期間需以原始公告核對，非今日正在處置的完整清單'}
                except Exception as e:
                    alerts['errors'][key]=str(e)[:240]
        save_json(DATA/'alerts.json',alerts)
        save_json(DATA/'status.json',{'ok':True,'state':outcome,'at':now_iso(),'date':day,
                                     'messages':events,'alert_errors':list(alerts['errors'])})
        print(f'OK date={day} state={outcome} coverage={record["coverage"]} sectors={len(record["sectors"])}')
    except Exception as e:
        # Keep the previously verified dashboard untouched; surface only the failure.
        save_json(DATA/'status.json',{'ok':False,'state':'error','at':now_iso(),
                                     'error':str(e)[:350],
                                     'message':'不更新輪動排行榜，保留上次通過檢查的資料。'})
        print('ERROR: '+str(e),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(update())
