"""Public, fixed-cohort active ETF observation. No private data or trading signals."""
import hashlib
import json
import math
import re
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

BASE='https://raw.githubusercontent.com/nctuwanglin/active-etf/main/'
SOURCE='https://github.com/nctuwanglin/active-etf'
VERSION='AEP-B25-v0.1-20261125'
COHORT=tuple('00400A 00401A 00403A 00404A 00405A 00406A 00407A 00408A 00410A 00413A 00415A 00416A 00418A 00980A 00981A 00982A 00984A 00985A 00987A 00991A 00992A 00993A 00994A 00995A 00999A'.split())
EXCLUDED={'00996A':'上游來源停用；固定觀察籃之外'}
TWN=timezone(timedelta(hours=8))

def now():
    return datetime.now(TWN).isoformat(timespec='seconds')

def read(p, default=None):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return default

def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    tmp.replace(p)

def fetch(path):
    req=urllib.request.Request(BASE+path,headers={'User-Agent':'RHEA-public-observation/1.0','Accept':'application/json','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=18) as res:
        raw=res.read(8_000_001)
    if len(raw)>8_000_000:
        raise ValueError('source payload too large')
    obj=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(obj,dict):
        raise ValueError('source is not a JSON object')
    return obj,hashlib.sha256(raw).hexdigest()

def daystr(value):
    if not isinstance(value,str):
        raise ValueError('date missing')
    return date.fromisoformat(value).isoformat()

def is_open(d, cal):
    ds=d.isoformat()
    if not cal['coverage_start']<=ds<=cal['coverage_end']:
        raise ValueError('交易日曆涵蓋不足')
    return ds in cal.get('open_dates',[]) or (d.weekday()<5 and ds not in cal.get('closed_dates',[]))

def adjacent(day, direction, cal):
    d=date.fromisoformat(day)
    if not is_open(d,cal):
        raise ValueError('非交易日')
    for _ in range(14):
        d+=timedelta(days=direction)
        if is_open(d,cal):
            return d.isoformat()
    raise ValueError('找不到相鄰交易日')

def positive(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>0

def holdings(e):
    raw=e.get('holdings')
    if not isinstance(raw,list) or not raw:
        raise ValueError('持股清單缺失')
    # Keep raw four-digit ordinary-stock-code candidates; don't treat nonstock holdings as zero.
    h={}
    for x in raw:
        code=x.get('code')
        if not isinstance(code,str) or not re.fullmatch(r'[1-9]\d{3}',code):
            continue
        v=x.get('shares')
        if code in h or not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0 or int(v)!=v:
            raise ValueError('股數或代號異常')
        h[code]=int(v)
    if not h:
        raise ValueError('台股持股缺失')
    return h

def pair(a,b,previous,day):
    if any(e.get('status')!='ok' for e in (a,b)) or a.get('data_date')!=previous or b.get('data_date')!=day:
        raise ValueError('持股日不同或來源狀態非ok')
    m,n=a.get('meta',{}),b.get('meta',{})
    u,v=m.get('units'),n.get('units')
    p,q=m.get('nav_per_unit'),n.get('nav_per_unit')
    s,t=m.get('scale'),n.get('scale')
    if not all(positive(x) for x in (u,v,p,q,s,t)) or int(u)!=u or int(v)!=v:
        raise ValueError('單位數／NAV／規模缺值')
    # NAV is rounded in upstream snapshots; this is a consistency check, not independent source verification.
    if abs(u*p-s)/s>.01 or abs(v*q-t)/t>.01:
        raise ValueError('單位×NAV與規模差異>1%')
    # Reject obvious split-like discontinuities; not a full corporate-action adjustment.
    if ((v/u>=1.5 and q/p<.8) or (v/u<=2/3 and q/p>1.25)) and .8<=t/s<=1.25:
        raise ValueError('疑似單位分割或反分割')
    h,j=holdings(a),holdings(b)
    if min(len(h),len(j))<.5*max(len(h),len(j)):
        raise ValueError('持股檔數跳變>50%')
    up=down=flat=0
    reductions=[]
    for c in sorted(h.keys()|j.keys()):
        delta=j.get(c,0)-h.get(c,0)
        if delta>0: up+=1
        elif delta<0:
            down+=1
            reductions.append(c)
        else: flat+=1
    return {'units_before':int(u),'units_after':int(v),'nav_before':p,'nav_after':q,
            'scale_before':s,'scale_after':t,'unit_delta':int(v-u),
            'estimate':(v-u)*p,'up':up,'down':down,'flat':flat,'reductions':reductions}

def summarize(day, previous, next_day, snaps, observed_at, known_market_dates, active=None, cohort=COHORT):
    details={}
    missing={}
    for code in cohort:
        a,b=snaps.get((code,previous)),snaps.get((code,day))
        if not a or not b:
            missing[code]='缺前日或本日有效同日快照'
            continue
        try:
            # Where the latest active.json matches this exact holding date, cross-check its raw shares
            # against the history snapshot; both are from the SAME source, not two independent feeds.
            live=(active or {}).get('etfs',{}).get(code)
            if live and live.get('status')=='ok' and live.get('data_date')==day:
                if holdings(live)!=holdings(b['data']):
                    raise ValueError('同源最新清單與歷史快照有修訂差異')
            d=pair(a['data'],b['data'],previous,day)
            d['before_batch']=a['batch']
            d['after_batch']=b['batch']
            d['before_hash']=a['hash']
            d['after_hash']=b['hash']
            d['before_source']=a.get('source',SOURCE)
            d['after_source']=b.get('source',SOURCE)
            details[code]=d
        except (ValueError,TypeError,KeyError,ArithmeticError) as e:
            missing[code]=str(e)[:100]
    n=len(details)
    complete=bool(cohort) and n==len(cohort) and day in known_market_dates and previous in known_market_dates
    rows=list(details.values())
    increases=sum(r['unit_delta']>0 for r in rows)
    decreases=sum(r['unit_delta']<0 for r in rows)
    unchanged=n-increases-decreases
    amount=sum(r['estimate'] for r in rows)
    scale=sum(r['scale_before'] for r in rows)
    up=sum(r['up'] for r in rows)
    down=sum(r['down'] for r in rows)
    flat=sum(r['flat'] for r in rows)
    sync=Counter(c for r in rows for c in r['reductions'])
    cutoff=next_day+'T08:30:00+08:00'
    timely=complete and datetime.fromisoformat(observed_at)<=datetime.fromisoformat(cutoff)
    return {'version':VERSION,'date':day,'previous_date':previous,'next_date':next_day,
            'observed_at':observed_at,'cutoff':cutoff,'timely':timely,
            'state':'complete' if complete else 'partial','n':n,'expected':len(cohort),
            'plus':increases,'minus':decreases,'flat':unchanged,
            'aep1':round(100*(increases-decreases)/n,6) if complete else None,
            'flow_100m':round(amount/1e8,6) if complete else None,
            'flow_pct':round(100*amount/scale,6) if complete and scale else None,
            'hold_breadth':round(100*(down-up)/(up+down+flat),6) if complete and up+down+flat else None,
            'hold_up':up,'hold_down':down,'hold_flat':flat,'sync_reduce':sum(v>=2 for v in sync.values()),
            'partial_flow_100m':round(amount/1e8,6) if n else None,
            'missing':missing,'details':details}

def fingerprint(row):
    # Identical measurements keep their first actual observation timestamp.
    # Source hashes may change for unrelated ETFs; don't treat these as a revised value.
    stable={k:v for k,v in row.items() if k not in ('observed_at','timely','details')}
    stable['details']={k:{a:b for a,b in v.items() if a not in ('before_hash','after_hash','before_batch','after_batch','before_source','after_source')} for k,v in row.get('details',{}).items()}
    return hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def append_version(data_dir,row,folder='aep_history'):
    file=data_dir/folder/(row['date']+'.json')
    versions=read(file,[]) or []
    if not isinstance(versions,list):
        raise ValueError('AEP歷史檔格式錯誤')
    fp=fingerprint(row)
    # Compare last version, not all historical versions: A -> B -> A is a real new observation.
    if not versions or fingerprint(versions[-1])!=fp:
        versions.append(row)
        save(file,versions)
    return versions

def public_row(row):
    return {k:v for k,v in row.items() if k!='details'}

def assemble(data_dir, days, cal, observed_at, errors, extras):
    rows=[]
    bydate={}
    for day in days:
        versions=read(data_dir/'aep_history'/(day+'.json'),[]) or []
        versions=[v for v in versions if v.get('version')==VERSION]
        if not versions:
            rows.append({'date':day,'state':'waiting','n':0,'expected':len(COHORT)})
            continue
        current=public_row(versions[-1])
        locked=next((public_row(v) for v in versions if v.get('state')=='complete' and v.get('timely')),None)
        current['locked']=locked
        current['revision_count']=len(versions)
        bydate[day]=current
        rows.append(current)
    for row in rows:
        d=row['date']
        try:
            p=adjacent(d,-1,cal)
            pp=adjacent(p,-1,cal)
        except ValueError:
            continue
        seq=[bydate.get(x) for x in (pp,p,d)]
        row['aep3']=round(sum(x['aep1'] for x in seq),6) if all(x and x.get('aep1') is not None for x in seq) else None
        if row.get('locked'):
            locks=[x.get('locked') if x else None for x in seq]
            row['locked']['aep3']=round(sum(x['aep1'] for x in locks),6) if all(x and x.get('aep1') is not None for x in locks) else None
    return {'version':VERSION,'state':'ok','checked_at':observed_at,'source':SOURCE,
            'cohort':list(COHORT),'excluded':EXCLUDED,'extra_codes':extras,'market_date':days[-1],
            'errors':errors,'rows':rows[-5:]}

def source_cohort(live):
    # The upstream explicitly tracks Taiwan active equity ETFs. This is its observed
    # universe, not an official complete roster; retain stale funds in the denominator.
    etfs=live.get('etfs',{})
    if not isinstance(etfs,dict) or not etfs:
        raise ValueError('來源追蹤名單空白')
    codes=tuple(sorted(k for k,v in etfs.items() if re.fullmatch(r'0\d{4}A',k) and isinstance(v,dict) and k not in EXCLUDED))
    if not codes:
        raise ValueError('來源ETF代號格式改變')
    return codes

def current_scope(data_dir,days,cal,snaps,live,cohort,observed_at):
    # Save a dated membership snapshot. Do not apply today's list retrospectively.
    day=days[-1]
    prev=adjacent(day,-1,cal)
    nxt=adjacent(day,1,cal)
    roster_id='SRC-'+hashlib.sha256(','.join(cohort).encode()).hexdigest()[:12]
    row=summarize(day,prev,nxt,snaps,observed_at,set(days),live,cohort)
    row.update({'cohort':list(cohort),'roster_id':roster_id,
                'scope':'upstream_tracked_not_official_universe',
                'source_batch':live.get('updated'),
                'added_vs_fixed':sorted(set(cohort)-set(COHORT)),
                'absent_vs_fixed':sorted(set(COHORT)-set(cohort))})
    # Membership changes are real observations, not corrections to older dates.
    # Only fixed-basket history gets the research clock lock. Dynamic series is descriptive
    # until source/official roster continuity and membership-effective dates are validated.
    row['timely']=False
    versions=append_version(data_dir,row,'aep_scope_history')
    out=public_row(versions[-1])
    out['revision_count']=len(versions)
    return out

# Independent official MIS unit-change observation; never a substitute for PCF holdings.
MIS_URL='https://mis.twse.com.tw/stock/data/all_etf.txt'

def official_flow(payload, day, observed_at, cohort=COHORT):
    if isinstance(payload.get('a1'),list):
        groups=payload['a1']
        records=[x for g in groups if isinstance(g,dict) and g.get('rtCode')=='0000' and isinstance(g.get('msgArray'),list) for x in g['msgArray']]
    elif payload.get('rtCode')=='0000' and isinstance(payload.get('msgArray'),list):
        records=payload['msgArray']
    else:
        raise ValueError('MIS response status/schema')
    if not records:
        raise ValueError('MIS empty records')
    def integer(s):
        if isinstance(s,(int,float)) and not isinstance(s,bool) and math.isfinite(s) and int(s)==s:
            return int(s)
        if not isinstance(s,str) or not re.fullmatch(r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)',s.strip()):
            raise ValueError('invalid integer')
        return int(s.replace(',',''))
    details={}
    missing={}
    for code in cohort:
        matches=[x for x in records if isinstance(x,dict) and x.get('a')==code]
        try:
            if len(matches)!=1:
                raise ValueError('missing or duplicate code')
            x=matches[0]
            if x.get('i')!=day.replace('-',''):
                raise ValueError('stale data date')
            stamp=time.fromisoformat(x['j'])
            if stamp<time(13,30) or stamp.tzinfo is not None:
                raise ValueError('pre-close or invalid timestamp')
            if datetime.fromisoformat(day+'T'+x['j']+'+08:00')>datetime.fromisoformat(observed_at):
                raise ValueError('future timestamp')
            units,delta=integer(x.get('c')),integer(x.get('d'))
            nav=float(x['h'])
            if units<=0 or units-delta<=0 or not positive(nav):
                raise ValueError('invalid units or prior NAV')
            # Large unit changes can include splits; no corporate-action adjustment here.
            if abs(delta)/(units-delta)>=0.5:
                raise ValueError('large unit change: corporate-action review')
            details[code]={'units':units,'unit_delta':delta,'prior_nav':nav,'estimate':delta*nav,'source_time':x['j']}
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            missing[code]=str(exc)[:100]
    n=len(details)
    amount=sum(x['estimate'] for x in details.values())
    plus=sum(x['unit_delta']>0 for x in details.values())
    minus=sum(x['unit_delta']<0 for x in details.values())
    return {'date':day,'observed_at':observed_at,'source':MIS_URL,'state':'complete' if n==len(cohort) else 'partial',
            'n':n,'expected':len(cohort),'plus':plus,'minus':minus,'flat':n-plus-minus,
            'flow_100m':round(amount/1e8,6) if n==len(cohort) else None,
            'partial_flow_100m':round(amount/1e8,6) if n else None,'missing':missing,
            'details':details,'redeem_100m':round(sum(-x['estimate'] for x in details.values() if x['estimate']<0)/1e8,6),'subscribe_100m':round(sum(x['estimate'] for x in details.values() if x['estimate']>0)/1e8,6),'aep1':round(100*(plus-minus)/n,6) if n==len(cohort) else None,'research_only':True}

def collect_official_flow(data_dir,day):
    try:
        req=urllib.request.Request(MIS_URL,headers={'User-Agent':'RHEA-public-observation/1.0','Accept':'application/json','Cache-Control':'no-cache'})
        with urllib.request.urlopen(req,timeout=15) as response:
            raw=response.read(4_000_001)
        if len(raw)>4_000_000:
            raise ValueError('MIS payload too large')
        row=official_flow(json.loads(raw.decode('utf-8-sig')),day,now())
        row['source_hash']=hashlib.sha256(raw).hexdigest()
        path=data_dir/'aep_official_history'/(day+'.json')
        versions=read(path,[]) or []
        if not isinstance(versions,list):
            raise ValueError('MIS history format')
        # Keep revisions, but identical parsed observations retain first acquisition time.
        signature=lambda x:{k:v for k,v in x.items() if k not in ('observed_at','source_hash')}
        if not versions or signature(versions[-1])!=signature(row):
            versions.append(row)
            save(path,versions)
        return {**versions[-1],'checked_at':now()}
    except Exception as exc:
        return {'date':day,'observed_at':now(),'source':MIS_URL,'state':'error','n':0,'expected':len(COHORT),
                'error':str(exc)[:160],'research_only':True}



# Targeted issuer fallback for the five repeatedly delayed funds.
ISSUER_CODES={'00980A':'nomura','00985A':'nomura','00999A':'nomura','00984A':'allianz','00993A':'allianz'}

def issuer_snapshots(day,next_day,codes):
    import http.cookiejar
    from urllib.parse import urlencode
    found={}
    errors={}
    def session():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(op,url,body=None,headers=None):
        h={'User-Agent':'RHEA-public-observation/1.0','Accept':'application/json'}
        if body is not None:h['Content-Type']='application/json'
        h.update(headers or {})
        req=urllib.request.Request(url,data=None if body is None else json.dumps(body).encode(),headers=h)
        with op.open(req,timeout=12) as res:
            raw=res.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError('issuer payload too large')
        return json.loads(raw.decode('utf-8-sig')),hashlib.sha256(raw).hexdigest()
    def num(x):
        return float(str(x).replace(',','').strip().rstrip('%'))
    def shares(x):
        n=num(x)
        if not math.isfinite(n) or n<0 or int(n)!=n:raise ValueError('invalid issuer shares')
        return int(n)
    def make(e,rows,actual,source,h):
        if actual!=day:raise ValueError('issuer holding date '+str(actual))
        result={'status':'ok','data_date':actual,'holdings':rows,'meta':{'units':shares(e['CAnceTotalIssues']),'nav_per_unit':num(e['CAnceNav']),'scale':num(e['CAnceTotalAv'])}}
        holdings(result)
        if len(rows)<10:raise ValueError('issuer holdings incomplete')
        m=result['meta']
        if not all(positive(m[k]) for k in ('units','nav_per_unit','scale')) or abs(m['units']*m['nav_per_unit']-m['scale'])/m['scale']>.01:raise ValueError('issuer NAV mismatch')
        return {'data':result,'batch':day,'hash':h,'source':source}
    for code in codes:
        if ISSUER_CODES.get(code)!='nomura':continue
        u='https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundTradeInfo'
        try:
            op=session()
            for q in (next_day,day):
                d,h=request(op,u,{'Type':1,'Keyword':'','FundNo':code,'Date':q})
                e=d.get('Entries') or {}
                actual=str(e.get('CNavDtStr','')).replace('/','-')
                if actual!=day:continue
                rows=[{'code':str(x['CStockCode']).strip(),'name':str(x['CStockName']),'shares':shares(x['CQuantity']),'weight':num(x['CWeightsPct'])} for x in e['Stocks']]
                found[code]=make(e,rows,actual,u,h)
                break
            if code not in found:raise ValueError('no exact date')
        except Exception as exc:errors[code]=str(exc)[:100]
    targets=[c for c in codes if ISSUER_CODES.get(c)=='allianz']
    if targets:
        base='https://etf.allianzgi.com.tw'
        api=base+'/webapi/api/'
        try:
            op=session()
            with op.open(urllib.request.Request(base+'/list-trade',headers={'User-Agent':'RHEA-public-observation/1.0'}),timeout=12) as res:res.read(1_000_000)
            tok,_=request(op,api+'AntiForgery/GetAntiForgeryToken')
            hdr={'X-XSRF-TOKEN':tok['token'],'Referer':base+'/list-trade'}
            t,_=request(op,api+'Category/GetFundTypeDropdownOptions',{},hdr)
            typ=next(x['Id'] for x in t['Entries'] if '主動' in x.get('Name',''))
            f,_=request(op,api+'Category/GetFundDropdownOptions',{'TypeId':typ},hdr)
            ids={x.get('SecuritiesCode'):x['FundNo'] for x in f['Entries'] if x.get('SecuritiesCode')}
            for code in targets:
                try:
                    for q in (next_day,day):
                        d,h=request(op,api+'Fund/GetFundTradeInfo',{'Type':1,'Keyword':'','FundNo':ids[code],'Date':q},hdr)
                        e=d.get('Entries') or {}
                        actual=str(e.get('CNavDt',''))[:10]
                        if actual!=day:continue
                        t=next(x for x in e['DynamicTableData'] if x.get('TableTitle','').startswith('股票'))
                        rows=[{'code':str(x[1]).strip(),'name':str(x[2]),'shares':shares(x[3]),'weight':num(x[4])} for x in t['Rows'] if len(x)>=5]
                        found[code]=make(e,rows,actual,api+'Fund/GetFundTradeInfo',h)
                        break
                    if code not in found:raise ValueError('no exact date')
                except Exception as exc:errors[code]=str(exc)[:100]
        except Exception as exc:
            for code in targets:errors[code]=str(exc)[:100]
    return found,errors

def descriptive_snapshot(day,prev,snaps,live,observed_at):
    # Same-date PCF metadata may be usable even when holdings are missing; coverage is independent.
    funds=[]
    reductions={}
    for code in COHORT:
        aa,bb=snaps.get((code,prev)),snaps.get((code,day))
        if not aa or not bb:continue
        try:
            a,b=aa['data'],bb['data']
            d=pair(a,b,prev,day)
            h,j=holdings(a),holdings(b)
            weight=sum(float(x['weight']) for x in b['holdings'] if re.fullmatch(r'[1-9]\d{3}',str(x.get('code',''))))
            residual=round(100-weight,4) if 0<=weight<=100 else None
            # Residual is not cash: it may include other assets, liabilities and rounding.
            delta=d['unit_delta']
            f={'code':code,'flow_100m':round(d['estimate']/1e8,6),'unit_delta':delta,'nav_before':d['nav_before'],'nav_after':d['nav_after'],'up':d['up'],'down':d['down'],'nonstock_residual_pct':residual,'source':bb.get('source',SOURCE)}
            increase=decrease=0.0
            unpriced=0
            for c in h.keys()|j.keys():
                diff=j.get(c,0)-h.get(c,0)
                if not diff:continue
                q=live.get('stocks',{}).get(c,{})
                price=q.get('close')
                if q.get('quote_date')!=day or not positive(price):
                    unpriced+=1
                    continue
                money=diff*price
                if money>0:increase+=money
                else:
                    decrease-=money
                    if delta<0:
                        t=reductions.setdefault(c,{'code':c,'name':q.get('name',c),'value':0,'etfs':[]})
                        t['value']-=money
                        t['etfs'].append(code)
            f.update({'hold_increase_100m':round(increase/1e8,6),'hold_decrease_100m':round(decrease/1e8,6),'unpriced_changes':unpriced})
            funds.append(f)
        except (ValueError,TypeError,KeyError,ArithmeticError):continue
    n=len(funds)
    redeem=sum(-x['flow_100m'] for x in funds if x['flow_100m']<0)
    subscribe=sum(x['flow_100m'] for x in funds if x['flow_100m']>0)
    top=sorted(reductions.values(),key=lambda x:-x['value'])[:5]
    for x in top:x['value_100m']=round(x.pop('value')/1e8,6)
    return {'date':day,'observed_at':observed_at,'n':n,'expected':len(COHORT),'state':'complete' if n==len(COHORT) else 'partial',
            'redeem_100m':round(redeem,6),'subscribe_100m':round(subscribe,6),'net_100m':round(subscribe-redeem,6),
            'funds':sorted(funds,key=lambda x:x['flow_100m']),'top_reduced':top,'cash_available':False,
            'missing':sorted(set(COHORT)-{x['code'] for x in funds}),'research_only':True}


def stock_monitor(day,prev,snaps,live,record,observed_at,cohort=COHORT):
    """Public same-day holdings proxy, separate from AEP research and official flow."""
    reference={}
    ambiguous=set()
    for sector in record.get('sectors',{}).values():
        if sector.get('type')!='official':continue
        for m in sector.get('members',[]):
            c=m['code']
            if c in reference:ambiguous.add(c)
            reference[c]={'industry':sector['name'],'name':m.get('name',c),'market':m.get('market')}
    for c in ambiguous:reference.pop(c,None)
    rows={}
    paired=[]
    for fund in cohort:
        aa,bb=snaps.get((fund,prev)),snaps.get((fund,day))
        if not aa or not bb:continue
        try:
            a,b=aa['data'],bb['data']
            pair(a,b,prev,day)
            h,j=holdings(a),holdings(b)
        except (ValueError,TypeError,KeyError,ArithmeticError):continue
        paired.append(fund)
        names={x.get('code'):x.get('name') for x in a['holdings']+b['holdings']}
        for c in sorted(h.keys()|j.keys()):
            old,new=h.get(c,0),j.get(c,0)
            if not old and not new:continue
            r=rows.setdefault(c,{'code':c,'name':reference.get(c,{}).get('name') or names.get(c) or c,
              'industry':reference.get(c,{}).get('industry','未分類'),'shares':0,'increase_shares':0,
              'decrease_shares':0,'hold_etfs':[],'previous_hold_etfs':[],'up_etfs':[],'down_etfs':[]})
            r['shares']+=new
            if new:r['hold_etfs'].append(fund)
            if old:r['previous_hold_etfs'].append(fund)
            if new>old:r['increase_shares']+=new-old;r['up_etfs'].append(fund)
            if new<old:r['decrease_shares']+=old-new;r['down_etfs'].append(fund)
    groups={}
    sources=Counter()
    for c,r in rows.items():
        q=record.get('aep_stock_quotes',{}).get(reference.get(c,{}).get('market'),{}).get(c,{})
        price=q.get('close') if record.get('date')==day else None
        price_source='official' if positive(price) else None
        if not price_source:
            q=live.get('stocks',{}).get(c,{})
            if q.get('quote_date')==day and positive(q.get('close')):
                price=q['close'];price_source='upstream_same_day'
        sources[price_source or 'missing']+=1
        r['price_source']=price_source
        r['close']=price if price_source else None
        r['net_shares']=r['increase_shares']-r['decrease_shares']
        for field,shares in [('market_value_100m',r['shares']),('increase_100m',r['increase_shares']),
                             ('decrease_100m',r['decrease_shares']),('net_100m',r['net_shares'])]:
            r[field]=round(shares*price/1e8,6) if price_source else None
        g=groups.setdefault(r['industry'],{'industry':r['industry'],'stocks':0,'changed_stocks':0,
           'unpriced_changes':0,'increase_100m':0.,'decrease_100m':0.,'net_100m':0.})
        g['stocks']+=int(r['shares']>0)
        changed=bool(r['up_etfs'] or r['down_etfs'])
        g['changed_stocks']+=int(changed)
        if changed and not price_source:g['unpriced_changes']+=1
        if price_source:
            for k in ('increase_100m','decrease_100m','net_100m'):g[k]+=r[k]
    for g in groups.values():
        for k in ('increase_100m','decrease_100m','net_100m'):
            g[k]=round(g[k],6) if g['changed_stocks']==0 or g['changed_stocks']>g['unpriced_changes'] else None
    return {'version':'AEP-STOCK-v2','date':day,'previous_date':prev,'observed_at':observed_at,
      'n':len(paired),'expected':len(cohort),'state':'complete' if len(paired)==len(cohort) else 'partial',
      'missing':sorted(set(cohort)-set(paired)),'price_sources':dict(sources),'research_only':True,
      'stocks':sorted(rows.values(),key=lambda r:r['code']),
      'sectors':sorted(groups.values(),key=lambda g:g['industry'])}


def historical_quotes(day, record, data_dir):
    """Bounded official date-scoped backfill; never substitute the latest quote."""
    existing=record.get('aep_stock_quotes',{})
    if len(existing.get('TWSE',{}))>=800 and len(existing.get('TPEx',{}))>=600:
        return existing
    path=data_dir/'aep_stock_quotes_history'/(day+'.json')
    cached=read(path,{}) or {}
    quotes=dict(cached.get('quotes',{})) if cached.get('date')==day else {}
    quotes.update({m:v for m,v in existing.items() if v})
    def get(m):
        if len(quotes.get(m,{}))>=(800 if m=='TWSE' else 600):return m,quotes[m]
        try:
            from urllib.parse import urlencode
            if m=='TWSE':
                from update import fetch_twse_mi_index, num
                raw=fetch_twse_mi_index(day)
                v={x['Code']:{'close':num(x['ClosingPrice'])} for x in raw if positive(num(x.get('ClosingPrice')))}
            else:
                from update import iso_date, num
                url='https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?'+urlencode({'date':day.replace('-','/'),'id':'','response':'json'})
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=15) as res:
                    raw=json.loads(res.read(12_000_000).decode('utf-8-sig'))
                if not isinstance(raw,dict) or iso_date(raw.get('date',''))!=day:raise ValueError('TPEx historical date mismatch')
                v={}
                for t in raw.get('tables',[]):
                    fields=[str(x).strip() for x in t.get('fields',[])]
                    c=next((i for i,x in enumerate(fields) if x in ('代號','證券代號','股票代號')),None)
                    p=next((i for i,x in enumerate(fields) if x in ('收盤','收盤價')),None)
                    if c is None or p is None:continue
                    for x in t.get('data',[]):
                        if len(x)<=max(c,p):continue
                        code=str(x[c]).strip()
                        price=num(x[p])
                        if re.fullmatch(r'[1-9]\d{3}',code) and positive(price):
                            if code in v:raise ValueError('duplicate TPEx historical code')
                            v[code]={'close':price}
            if len(v)<(800 if m=='TWSE' else 600):raise ValueError('historical quote coverage insufficient')
            return m,v
        except Exception as e:
            print('AEP historical price WAIT',day,m,str(e)[:100])
            return m,quotes.get(m,{})
    with ThreadPoolExecutor(max_workers=2) as pool:
        quotes=dict(pool.map(get,('TWSE','TPEx')))
    if any(quotes.values()):save(path,{'date':day,'observed_at':now(),'quotes':quotes})
    return quotes


def stock_window(days, records, period, cohort=COHORT):
    """Aggregate consecutive fully paired daily observations, not a selected subset."""
    dates=list(days[-period:])
    selected=[records.get(d) for d in dates]
    valid=sum(bool(x and x.get('state')=='complete' and x.get('n')==len(cohort) and x.get('expected')==len(cohort)
                   and x.get('version')=='AEP-STOCK-v2' and x.get('date')==d)
              for d,x in zip(dates,selected))
    result={'period':period,'date':dates[-1] if dates else None,'dates':dates,'valid_days':valid,
            'expected_days':period,'n':len(cohort),'expected':len(cohort),'state':'waiting','stocks':[],'sectors':[]}
    if len(dates)!=period or valid!=period or any(b['previous_date']!=a['date'] for a,b in zip(selected,selected[1:])):
        return result
    result.update({'state':'complete','previous_date':selected[0]['previous_date'],'observed_at':max(x['observed_at'] for x in selected)})
    allrows={}
    final={r['code']:r for r in selected[-1]['stocks']}
    first={r['code']:r for r in selected[0]['stocks']}
    source_counts=Counter()
    for x in selected:
        source_counts.update(x.get('price_sources',{}))
        for r in x['stocks']:
            c=r['code']
            a=allrows.setdefault(c,{'code':c,'name':r['name'],'industry':r['industry'],
                 'shares':0,'hold_etfs':[],'up_etfs':set(),'down_etfs':set(),'increase_shares':0,
                 'decrease_shares':0,'net_shares':0,'increase_100m':0.,'decrease_100m':0.,
                 'net_100m':0.,'up_days':0,'down_days':0,'missing_price_days':0})
            a['name']=r['name'];a['industry']=r['industry']
            a['up_etfs'].update(r['up_etfs']);a['down_etfs'].update(r['down_etfs'])
            for key in ('increase_shares','decrease_shares','net_shares'):a[key]+=r[key]
            a['up_days']+=int(r['net_shares']>0);a['down_days']+=int(r['net_shares']<0)
            if r['up_etfs'] or r['down_etfs']:
                if r['close'] is None:a['missing_price_days']+=1
                else:
                    for k in ('increase_100m','decrease_100m','net_100m'):a[k]+=r[k]
    groups={}
    for c,a in allrows.items():
        end=final.get(c,{})
        a.update({'shares':end.get('shares',0),'hold_etfs':end.get('hold_etfs',[]),
            'market_value_100m':end.get('market_value_100m') if end else 0,
            'previous_hold_count':len(first.get(c,{}).get('previous_hold_etfs',[]))})
        a['hold_count_change']=len(a['hold_etfs'])-a['previous_hold_count']
        a['up_etfs']=sorted(a['up_etfs']);a['down_etfs']=sorted(a['down_etfs'])
        g=groups.setdefault(a['industry'],{'industry':a['industry'],'stocks':0,'changed_stocks':0,
            'unpriced_changes':0,'increase_100m':0.,'decrease_100m':0.,'net_100m':0.})
        g['stocks']+=int(a['shares']>0)
        g['changed_stocks']+=int(bool(a['up_etfs'] or a['down_etfs']))
        g['unpriced_changes']+=int(a['missing_price_days']>0)
        for k in ('increase_100m','decrease_100m','net_100m'):
            # Sector totals are partial priced sums, explicitly identified by missing count.
            g[k]+=a[k]
            a[k]=None if a['missing_price_days'] else round(a[k],6)
    for g in groups.values():
        for k in ('increase_100m','decrease_100m','net_100m'):
            g[k]=round(g[k],6) if not g['changed_stocks'] or g['changed_stocks']>g['unpriced_changes'] else None
    result.update({'price_sources':dict(source_counts),'stocks':sorted(allrows.values(),key=lambda a:a['code']),
                   'sectors':sorted(groups.values(),key=lambda a:a['industry'])})
    return result


def run(data_dir):
    data_dir=Path(data_dir)
    outfile=data_dir/'aep.json'
    previous=read(outfile,{}) or {}
    try:
        # Market date is obtained from our own verified two-market records, not the ETF batch label.
        days=[]
        for p in sorted((data_dir/'daily').glob('????-??-??.json'))[-10:]:
            d=read(p,{}) or {}
            cov=d.get('coverage',{})
            if d.get('date')==p.stem and cov.get('TWSE',0)>=800 and cov.get('TPEx',0)>=600:
                days.append(p.stem)
        if len(days)<2:
            raise ValueError('等待本站完整上市櫃交易日')
        official=collect_official_flow(data_dir,days[-1])
        # Keep actual dated observations even after the MIS feed rolls to the next day.
        archive=read(data_dir/'aep_official_history'/(days[-1]+'.json'),[]) or []
        valid=[x for x in archive if x.get('date')==days[-1] and x.get('n',0)>0]
        prior=previous.get('official_flow',{})
        if prior.get('date')==days[-1] and prior.get('n',0)>0:valid.append(prior)
        if valid:
            best=max(valid,key=lambda x:(x.get('n',0),x.get('observed_at','')))
            if best.get('n',0)>official.get('n',0):
                official={**best,'checked_at':now(),'latest_attempt_n':official.get('n',0),'latest_attempt_state':official.get('state')}
        previous['official_flow']=official
        cal,_=fetch('data/trading_calendar.json')
        if cal.get('schema_version')!=1:
            raise ValueError('來源交易日曆格式改變')
        live,_=fetch('active.json')
        if live.get('schema_version')!=3 or not isinstance(live.get('etfs'),dict):
            raise ValueError('來源API格式改變')
        dates=set(days)
        batch_day=daystr(live.get('updated'))
        if batch_day<=datetime.now(TWN).date().isoformat():
            dates.add(batch_day)
        # Collect source batches by batch label, then index by each fund's actual holding date.
        def get_batch(d):
            try:
                o,h=fetch('data/history/'+d+'.json')
                if o.get('date')!=d or not isinstance(o.get('etfs'),dict):
                    raise ValueError('快照批次日期或格式不符')
                return d,o,h,None
            except Exception as exc:
                return d,None,None,str(exc)[:100]
        with ThreadPoolExecutor(max_workers=4) as pool:
            batches=list(pool.map(get_batch,sorted(dates)[-9:]))
        observed_at=now()
        snaps={}
        errors=[]
        current_cohort=source_cohort(live)
        extras=set(current_cohort)-set(COHORT)
        for batch,obj,h,error in batches:
            if error:
                errors.append(batch+': '+error)
                continue
            for code,e in obj['etfs'].items():
                if code not in COHORT and code not in current_cohort:
                    continue
                if isinstance(e,dict) and e.get('status')=='ok':
                    try:
                        d=daystr(e.get('data_date'))
                        if d<=batch:
                            snaps[(code,d)]={'data':e,'batch':batch,'hash':h}
                    except ValueError:
                        continue
        if not snaps:
            raise ValueError('無有效持股歷史快照')
        # Supplemental description, not a rewrite of the locked research series.
        latest=days[-1]
        prev=adjacent(latest,-1,cal)
        nxt=adjacent(latest,1,cal)
        supplemental=dict(snaps)
        # Reuse previously observed exact-date issuer snapshots; never fabricate acquisition time.
        for d in days[-8:]:
            for record in read(data_dir/'aep_issuer_snapshots'/(d+'.json'),[]) or []:
                for code,v in record.get('snapshots',{}).items():
                    if code in ISSUER_CODES and v.get('data',{}).get('data_date')==d and v.get('hash'):
                        supplemental.setdefault((code,d),v)
        issuer_errors={}
        for d,next_d in ((latest,nxt),(prev,latest)):
            gaps=[c for c in ISSUER_CODES if (c,d) not in supplemental]
            if not gaps:continue
            got,err=issuer_snapshots(d,next_d,gaps)
            supplemental.update({(c,d):v for c,v in got.items()})
            issuer_errors.update({d+' '+k:v for k,v in err.items()})
            if got:
                p=data_dir/'aep_issuer_snapshots'/(d+'.json')
                records=read(p,[]) or []
                sig={c:v['hash'] for c,v in got.items()}
                if not records or records[-1].get('hashes')!=sig:
                    records.append({'observed_at':now(),'hashes':sig,'snapshots':got})
                    save(p,records)
        for day in days[-7:]:
            try:
                p=adjacent(day,-1,cal)
                nxt=adjacent(day,1,cal)
                if p not in days:
                    continue
                row=summarize(day,p,nxt,supplemental,now(),set(days),live)
                # Never let an unavailable fallback erase an already recorded complete observation.
                versions=read(data_dir/'aep_history'/(day+'.json'),[]) or []
                if versions and versions[-1].get('state')=='complete' and row['state']!='complete':
                    errors.append(day+': 本次來源未齊，保留前次完整觀察')
                else:
                    append_version(data_dir,row)
            except ValueError as exc:
                errors.append(day+': '+str(exc)[:100])
        result=assemble(data_dir,days[-7:],cal,now(),errors,sorted(extras))
        result['official_flow']=previous['official_flow']
        result['descriptive']=descriptive_snapshot(latest,prev,supplemental,live,now())
        result['descriptive']['issuer_errors']=issuer_errors
        result['current_scope']=current_scope(data_dir,days,cal,supplemental,live,current_cohort,now())
        try:
            target_days=[latest]
            for _ in range(4):target_days.insert(0,adjacent(target_days[0],-1,cal))
            archive={}
            for d in target_days:
                p=adjacent(d,-1,cal)
                path=data_dir/'aep_stock_history'/(d+'.json')
                old=read(path,{}) or {}
                rec=read(data_dir/'daily'/(d+'.json'),{}) or {}
                if rec.get('date')!=d:
                    if old:archive[d]=old
                    continue
                # Already complete and fully priced historical snapshots are not re-fetched.
                if d!=latest and old.get('version')=='AEP-STOCK-v2' and old.get('state')=='complete' and not old.get('price_sources',{}).get('missing',0):
                    archive[d]=old
                    continue
                rec={**rec,'aep_stock_quotes':historical_quotes(d,rec,data_dir)}
                monitor=stock_monitor(d,p,supplemental,live,rec,now())
                old_quality=(old.get('n',0),-old.get('price_sources',{}).get('missing',0),int(old.get('version')=='AEP-STOCK-v2'))
                new_quality=(monitor['n'],-monitor['price_sources'].get('missing',0),1)
                if old and old_quality>new_quality:
                    archive[d]=old
                else:
                    save(path,monitor)
                    archive[d]=monitor
            result['stock_monitor']=archive.get(latest,{})
            result['stock_windows']={str(period):stock_window(target_days,archive,period) for period in (3,5)}
            print('AEP STOCK WINDOWS',[(k,v['valid_days'],v['state'],v.get('price_sources')) for k,v in result['stock_windows'].items()])
        except Exception as exc:
            result['stock_monitor']={**previous.get('stock_monitor',{}),'error':str(exc)[:150]}
            result['stock_windows']=previous.get('stock_windows',{})
        save(outfile,result)
        print('AEP observation:',result['market_date'],[(r['date'],r['n'],r['state']) for r in result['rows']])
    except Exception as exc:
        # Preserve verified earlier history and show failure; never relabel old data as today's.
        previous.update({'version':VERSION,'state':'error','checked_at':now(),'last_error':str(exc)[:200]})
        save(outfile,previous)
        print('AEP WAIT DATA: '+str(exc)[:200])
