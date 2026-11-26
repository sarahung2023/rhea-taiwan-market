"""TWSE dashboard all-market credit statistics; no private data, no trade signal."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json, math, re, urllib.request, urllib.parse
TWN=timezone(timedelta(hours=8))
BASE='https://www.twse.com.tw/rwd/zh/marginTrading/BFIJ3U_TREND'
VERSION='TWSE-credit-all-v1'
FIELDS=('crdAmt','keepRate','belowAccNum','callAccNum','callAmt','exeAccNum','exeAmt','marginAccNum','marginAccRate')
INT_FIELDS=set(FIELDS)-{'keepRate','marginAccRate'}
START='2026-11-19'
def stamp(): return datetime.now(TWN).isoformat(timespec='seconds')
def iso(s):
    if not isinstance(s,str) or not re.fullmatch(r'\d{8}',s): raise ValueError('invalid source date')
    return datetime.strptime(s,'%Y%m%d').date().isoformat()
def url_for(day):
    return BASE+'?'+urllib.parse.urlencode({'response':'json','days':5,'date':day.replace('-','')})
def parse(payload, requested):
    if not isinstance(payload,dict) or payload.get('stat')!='OK' or iso(payload.get('date'))!=requested or payload.get('days')!=5:
        raise ValueError('unexpected response date, status or window')
    rows=payload.get('data')
    if not isinstance(rows,list) or not 1<=len(rows)<=5: raise ValueError('invalid row count')
    out={}
    for r in rows:
        if not isinstance(r,dict): raise ValueError('invalid row')
        d=iso(r.get('date'))
        if d>requested or d in out or date.fromisoformat(d).weekday()>=5: raise ValueError('future, duplicate or weekend row')
        vals={}
        for k in FIELDS:
            v=r.get(k)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0: raise ValueError('invalid '+k)
            if k in INT_FIELDS and not isinstance(v,int): raise ValueError('invalid integer '+k)
            if k=='keepRate' and v<=0: raise ValueError('invalid keepRate')
            if k=='marginAccRate' and v>100: raise ValueError('invalid marginAccRate')
            vals[k]=v
        out[d]=vals
    return out
def fetch(day):
    url=url_for(day)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json','Referer':'https://www.twse.com.tw/dashboard/zh/credit/margin.html','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=20) as r:
        if r.status!=200: raise ValueError('HTTP '+str(r.status))
        raw=r.read(1_000_001)
    if len(raw)>1_000_000: raise ValueError('oversize')
    return parse(json.loads(raw.decode('utf-8-sig')),day)
def read(p):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(p)
def append(folder,day,raw,observed,source):
    p=folder/(day+'.json')
    versions=read(p)
    if not isinstance(versions,list): raise ValueError('invalid history')
    if not versions or versions[-1]['raw']!=raw:
        versions.append({'date':day,'observed_at':observed,'source':source,'raw':raw})
        save(p,versions)
    return versions[-1]
def change(cur,prev):
    return None if prev is None or prev==0 else 100*(cur/prev-1)
def overview(data,market_day,errors,checked,success):
    folder=data/'credit_history'
    hist={}
    for p in sorted(folder.glob('????-??-??.json')):
        v=read(p)
        if v: hist[p.stem]=(v[-1],len(v))
    # Only calculate daily change across a verified adjacent trading day.
    market_dates=sorted(p.stem for p in (data/'daily').glob('????-??-??.json'))
    # Official source's five-day window provides adjacency even before local market archive starts.
    # A pair must have appeared adjacent in a successful official response.
    adjacency=read(data/'credit_adjacency.json')
    if not isinstance(adjacency,dict): adjacency={}
    rows=[]
    for d,(v,n) in sorted(hist.items()):
        raw=v['raw']
        prev=adjacency.get(d)
        if d in market_dates:
            i=market_dates.index(d)
            if i>0 and prev!=market_dates[i-1]: prev=None
        p=hist.get(prev)
        pr=p[0]['raw'] if p else {}
        rows.append({'date':d,'observed_at':v['observed_at'],'source':v['source'],'revision_count':n,**raw,
            'previous_date':prev,'marginAccChangePct':change(raw['marginAccNum'],pr.get('marginAccNum')),
            'belowAccChangePct':change(raw['belowAccNum'],pr.get('belowAccNum')),
            'callAccChangePct':change(raw['callAccNum'],pr.get('callAccNum')),
            'threshold_pct':120 if d>='2026-11-24' else 130})
    latest=rows[-1]['date'] if rows else None
    state='ok' if success and latest==market_day else ('stale' if success and latest else 'error')
    return {'version':VERSION,'checked_at':checked,'market_date':market_day,'latest_date':latest,'state':state,'errors':errors,'history_count':len(rows),'rows':rows[-5:]}
def run(data):
    data=Path(data); folder=data/'credit_history'
    days=sorted(p.stem for p in (data/'daily').glob('????-??-??.json'))
    market_day=days[-1] if days else None
    checked=stamp(); errors=[]; success=False
    if not market_day:
        errors.append('No verified market trading date')
    else:
        # Latest trading date first, then at most 12 missing trading dates per run.
        targets=[market_day]+[d for d in reversed(days) if START<=d<market_day and not (folder/(d+'.json')).exists()][:12]
        adj=read(data/'credit_adjacency.json')
        if not isinstance(adj,dict): adj={}
        for target in targets:
            if target!=market_day and (folder/(target+'.json')).exists(): continue
            try:
                records=fetch(target); observed=stamp()
                for d,raw in sorted(records.items()):
                    if d>=START: append(folder,d,raw,observed,url_for(target))
                ordered=sorted(records)
                for prev,d in zip(ordered,ordered[1:]):
                    if d>=START: adj[d]=prev
                if target==market_day:
                    success=True
                    if target not in records: errors.append('Latest market date not yet published: '+target)
            except Exception as exc:
                errors.append(target+': '+str(exc)[:180])
        save(data/'credit_adjacency.json',adj)
    result=overview(data,market_day,errors,checked,success)
    save(data/'credit.json',result)
    print('Credit:',result['state'],result['latest_date'],result['history_count'],errors)
    return result
if __name__=='__main__':
    import sys
    # Explicit read-only live probe, never writes repository data.
    print(json.dumps(fetch(sys.argv[1]),ensure_ascii=False,indent=2))
