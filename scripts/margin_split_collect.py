"""Public TWSE/TPEx margin financing balance and estimated maintenance ratio."""
from pathlib import Path
from datetime import datetime,date
from decimal import Decimal, InvalidOperation
import json, urllib.request, re, hashlib
from credit_collect import save,read,stamp
VERSION='margin-split-v1'
START='2026-11-19'
TW='https://www.twse.com.tw/rwd/zh/'
OT='https://www.tpex.org.tw/'
OT_AMOUNT=OT+'data/home/dayChart.json'
OT_QUOTES=OT+'openapi/v1/tpex_mainboard_daily_close_quotes'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r:
        b=r.read(32_000_001)
    if len(b)>32_000_000:raise ValueError('oversize')
    return json.loads(b.decode('utf-8-sig')),hashlib.sha256(b).hexdigest()

def number(x):
    if isinstance(x,bool):raise ValueError('boolean')
    try:v=Decimal(str(x).replace(',','').strip())
    except InvalidOperation:raise ValueError('invalid number')
    if not v.is_finite():raise ValueError('nonfinite')
    return v

def roc(day):
    d=date.fromisoformat(day)
    return f'{d.year-1911:03d}{d.month:02d}{d.day:02d}'
def iso_roc(s):
    s=str(s)
    if not re.fullmatch(r'\d{7}',s):raise ValueError('invalid ROC date')
    return date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()
def validate(obj,day):
    if obj.get('stat')!='OK' or obj.get('date')!=day.replace('-',''):
        raise ValueError('source date/status mismatch')
def table(obj,fields):
    return next(t['data'] for t in obj['tables'] if t.get('fields',[])[:len(fields)]==fields)
def unique(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError('duplicate '+k)
        out[k]=v
    return out

def valuation(bal,quotes,amount):
    if amount<=0:raise ValueError('nonpositive financing amount')
    total=Decimal(0); missing=[]; refs=[]; shares=Decimal(0)
    for code,qty in bal.items():
        q=number(qty)
        if q<0 or q!=q.to_integral_value():raise ValueError('invalid lots')
        if not q:continue
        shares+=q
        close,ref=quotes.get(code,(None,None))
        try:
            p=number(close)
            if p<=0:raise ValueError('nonpositive close')
        except ValueError:
            try:
                p=number(ref)
                if p<=0:raise ValueError('nonpositive reference')
                refs.append({'code':code,'lots':int(q),'next_reference_price':float(p)})
            except ValueError:
                missing.append({'code':code,'lots':int(q)})
                continue
        total+=q*1000*p
    return {'financing_lots':int(shares),'valued_market_yuan':float(total),
            'maintenance_pct':None if missing else float(total/amount*100),
            'reference_prices':refs,'missing_prices':missing,
            'valuation_status':'partial' if missing else ('reference_estimate' if refs else 'close_estimate')}

def tse(day):
    y=day.replace('-','')
    mu=TW+'marginTrading/MI_MARGN?response=json&date='+y+'&selectType=ALL'
    qu=TW+'afterTrading/MI_INDEX?response=json&date='+y+'&type=ALLBUT0999'
    m,mh=get(mu);validate(m,day)
    den=next(r for r in table(m,['項目','買進']) if r[0]=='融資金額(仟元)')
    amount=number(den[-1])*1000;prev=number(den[-2])*1000
    if min(amount,prev)<=0:raise ValueError('invalid amount')
    bal=unique((r[0],r[6]) for r in table(m,['代號','名稱']))
    result={'balance_yuan':float(amount),'previous_balance_yuan':float(prev),'change_yuan':float(amount-prev),
            'sources':{mu:mh},'official_precision_yuan':1000}
    try:
        q,qh=get(qu);validate(q,day)
        prices=unique((r[0],(r[8],None)) for r in table(q,['證券代號','證券名稱','成交股數']))
        v=valuation(bal,prices,amount)
        if v['financing_lots']!=int(number(next(r for r in table(m,['項目','買進']) if r[0]=='融資(交易單位)')[-1])):raise ValueError('listed lot total mismatch')
        result.update(v);result['sources'][qu]=qh
    except Exception as e:result.update(maintenance_pct=None,valuation_status='partial',valuation_error=str(e)[:180])
    return result

def otc_amounts(obj):
    anchor=iso_roc(obj['dataDate'])
    out={}
    for r in obj['marginPurchaseValue10Days']:
        mm,dd=map(int,r['date'].split('-'))
        yr=int(anchor[:4]);d=date(yr,mm,dd)
        if d.isoformat()>anchor:d=date(yr-1,mm,dd)
        day=d.isoformat()
        if day in out or d.weekday()>=5:raise ValueError('invalid OTC amount date')
        amt=number(r['amt'])*100000000;dif=number(r['dif'])*100000000
        if amt<=0 or amt-dif<=0:raise ValueError('invalid OTC amount')
        out[day]={'balance_yuan':float(amt),'change_yuan':float(dif),'previous_balance_yuan':float(amt-dif),'official_precision_yuan':1000000}
    last=obj['marginPurchaseValue']
    if anchor not in out or out[anchor]['balance_yuan']!=float(number(last['mbal'])*100000000) or out[anchor]['change_yuan']!=float(number(last['mdif'])*100000000):
        raise ValueError('OTC latest aggregate mismatch')
    return anchor,out

def otc(day,amount,amount_hash,quotes,quote_hash):
    result={**amount,'sources':{OT_AMOUNT:amount_hash}}
    try:
        d=date.fromisoformat(day)
        url=OT+'web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=json&d='+f'{d.year-1911}/{d.month:02d}/{d.day:02d}'
        m,mh=get(url);validate(m,day)
        bal=unique((r[0],r[6]) for r in table(m,['代號','名稱','前資餘額(張)']))
        prices=unique((r['SecuritiesCompanyCode'],(r['Close'],r.get('NextReferencePrice'))) for r in quotes if r['Date']==roc(day))
        if not prices:raise ValueError('OTC quotes not available for date')
        v=valuation(bal,prices,number(amount['balance_yuan']))
        result.update(v);result['sources'].update({url:mh,OT_QUOTES:quote_hash})
    except Exception as e:result.update(maintenance_pct=None,valuation_status='partial',valuation_error=str(e)[:180])
    return result

def history(folder,day,market,raw):
    p=folder/(day+'.json')
    versions=read(p)
    old=versions[-1]['markets'] if versions else {}
    prev=old.get(market,{})
    # A temporary quote failure never erases a previously verified ratio for unchanged amount.
    if prev.get('maintenance_pct') is not None and raw.get('maintenance_pct') is None and prev.get('balance_yuan')==raw.get('balance_yuan'):
        return
    merged={**old,market:raw}
    if merged!=old:
        versions.append({'date':day,'observed_at':stamp(),'markets':merged})
        save(p,versions)

def overview(data,days,errors):
    folder=data/'margin_split_history'
    hist={}
    for p in sorted(folder.glob('????-??-??.json')):
        v=read(p)
        if v:hist[p.stem]=(v[-1],len(v))
    rows=[]
    for day,(v,n) in sorted(hist.items()):
        prev=days[days.index(day)-1] if day in days and days.index(day)>0 else None
        pr=hist.get(prev,({},0))[0].get('markets',{})
        markets={}
        for k,r in v['markets'].items():
            x=r.get('maintenance_pct');y=pr.get(k,{}).get('maintenance_pct')
            b=r['balance_yuan'];a=r['previous_balance_yuan']
            markets[k]={**r,'maintenance_change_pp':None if x is None or y is None else x-y,'balance_change_pct':100*r['change_yuan']/a if a else None}
        rows.append({'date':day,'observed_at':v['observed_at'],'revision_count':n,'markets':markets})
    latest=rows[-1] if rows else {}
    m=latest.get('markets',{})
    complete=latest.get('date')==(days[-1] if days else None) and all(m.get(k,{}).get('maintenance_pct') is not None for k in ('TSE','OTC'))
    return {'version':VERSION,'checked_at':stamp(),'market_date':days[-1] if days else None,'latest_date':latest.get('date'),'state':'ok' if complete and not errors else 'partial','errors':errors,'history_count':len(rows),'rows':rows[-5:]}

def run(data):
    data=Path(data);folder=data/'margin_split_history';errors=[]
    days=[]
    for p in sorted((data/'daily').glob('????-??-??.json')):
        try:
            d=read(p);c=d.get('coverage',{})
            if d.get('date')==p.stem and c.get('TWSE',0)>=800 and c.get('TPEx',0)>=600:days.append(p.stem)
        except Exception:continue
    targets=[d for d in days[-5:] if d>=START]
    if not targets:errors.append('No verified market dates')
    try:
        a,ah=get(OT_AMOUNT);anchor,amounts=otc_amounts(a)
        if anchor>(days[-1] if days else ''):raise ValueError('OTC amount beyond verified market date')
    except Exception as e:amounts={};ah=None;errors.append('OTC amount: '+str(e)[:180])
    try:q,qh=get(OT_QUOTES)
    except Exception as e:q=[];qh=None;errors.append('OTC quotes: '+str(e)[:180])
    for day in targets:
        for market,collect in [('TSE',lambda:tse(day)),('OTC',lambda:otc(day,amounts[day],ah,q,qh))]:
            try:
                raw=collect();history(folder,day,market,raw)
                if raw.get('maintenance_pct') is None:errors.append(day+' '+market+': '+raw.get('valuation_error','unpriced lots'))
            except Exception as e:errors.append(day+' '+market+': '+str(e)[:180])
    result=overview(data,days,errors);save(data/'margin_split.json',result)
    print('Margin split:',result['state'],result['latest_date'],result['history_count'],errors)
    return result
