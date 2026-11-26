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
    stable['details']={k:{a:b for a,b in v.items() if a not in ('before_hash','after_hash','before_batch','after_batch')} for k,v in row.get('details',{}).items()}
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
        prior=previous.get('official_flow',{})
        if prior.get('date')==days[-1] and prior.get('n',0)>official.get('n',0):
            official={**prior,'checked_at':now(),'latest_attempt_n':official.get('n',0)}
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
        for day in days[-7:]:
            try:
                p=adjacent(day,-1,cal)
                nxt=adjacent(day,1,cal)
                if p not in days:
                    continue
                row=summarize(day,p,nxt,snaps,observed_at,set(days),live)
                append_version(data_dir,row)
            except ValueError as exc:
                errors.append(day+': '+str(exc)[:100])
        result=assemble(data_dir,days[-7:],cal,observed_at,errors,sorted(extras))
        result['official_flow']=previous['official_flow']
        result['current_scope']=current_scope(data_dir,days,cal,snaps,live,current_cohort,observed_at)
        save(outfile,result)
        print('AEP observation:',result['market_date'],[(r['date'],r['n'],r['state']) for r in result['rows']])
    except Exception as exc:
        # Preserve verified earlier history and show failure; never relabel old data as today's.
        previous.update({'version':VERSION,'state':'error','checked_at':now(),'last_error':str(exc)[:200]})
        save(outfile,previous)
        print('AEP WAIT DATA: '+str(exc)[:200])
