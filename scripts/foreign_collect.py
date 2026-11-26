"""Official foreign net flows, separate OTC overview and detail scopes."""
from pathlib import Path
from datetime import date
from credit_collect import read,save,stamp
from margin_split_collect import get,number,iso_roc
from concurrent.futures import ThreadPoolExecutor
TW='https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&type=day&dayDate='
OT='https://www.tpex.org.tw/data/home/dayChart.json'
DETAIL='https://www.tpex.org.tw/www/zh-tw/insti/summary?date='
def integer(x):
    n=number(x)
    if n!=n.to_integral_value():raise ValueError('noninteger')
    return int(n)
def amounts(r):
    b,s,n=map(integer,r[1:4])
    if min(b,s)<0 or b-s!=n:raise ValueError('amount mismatch')
    return dict(buy_yuan=b,sell_yuan=s,net_yuan=n,precision_yuan=1)
def parse_tw(x,d):
    if x.get('stat')!='OK' or x.get('date')!=d.replace('-','') or x.get('fields')!=['單位名稱','買進金額','賣出金額','買賣差額']:raise ValueError('TW schema/date')
    r=[r for r in x['data'] if r[0]=='外資及陸資(不含外資自營商)']
    if len(r)!=1:raise ValueError('TW row')
    return amounts(r[0])
def parse_detail(x,d):
    if str(x.get('stat')).lower()!='ok' or x.get('date')!=d.replace('-',''):raise ValueError('OTC detail date')
    r=[r for t in x['tables'] if t.get('fields')==['單位名稱','買進金額(元)','賣出金額(元)','買賣超(元)'] for r in t['data'] if r[0].strip()=='外資及陸資(不含自營商)']
    if len(r)!=1:raise ValueError('OTC detail row')
    return amounts(r[0])
def parse_ot(x):
    anchor=iso_roc(x['dataDate']);a=date.fromisoformat(anchor);out={}
    for r in x['foreignBSN']:
        m,d=map(int,r['date'].split('-'));day=date(a.year,m,d)
        if day>a:day=date(a.year-1,m,d)
        k=day.isoformat()
        if k in out or day.weekday()>=5 or (a-day).days>40:raise ValueError('OTC date')
        b,s,n=[integer(number(r[f])*100000000) for f in ('b','s','n')]
        if min(b,s)<0 or abs(b-s-n)>1000000:raise ValueError('OTC amount mismatch')
        out[k]=dict(buy_yuan=b,sell_yuan=s,net_yuan=n,precision_yuan=1000000)
    if anchor not in out or out[anchor]['net_yuan']!=integer(number(x['big3']['fn'])*100000000):raise ValueError('OTC anchor mismatch')
    return anchor,out
def direction(a,b):
    if a is None or b is None:return None
    if a==0 or b==0:return '含零值'
    if a>0 and b>0:return '雙買'
    if a<0 and b<0:return '雙賣'
    return 'TSE買／OTC賣' if a>0 else 'TSE賣／OTC買'
def append(folder,d,k,r):
    p=folder/(d+'.json');v=read(p);old=v[-1]['markets'] if v else {};prior=old.get(k,{})
    if all(prior.get(z)==r.get(z) for z in ('buy_yuan','sell_yuan','net_yuan','source','precision_yuan')):return
    v.append(dict(date=d,observed_at=stamp(),markets={**old,k:{**r,'observed_at':stamp()}}));save(p,v)
def run(data):
    data=Path(data);folder=data/'foreign_history';errors=[];days=[]
    for p in sorted((data/'daily').glob('????-??-??.json')):
        try:
            x=read(p);c=x.get('coverage',{})
            if x.get('date')==p.stem and c.get('TWSE',0)>=800 and c.get('TPEx',0)>=600:days.append(p.stem)
        except Exception:continue
    latest=days[-1] if days else None
    targets=[d for d in days[-10:] if d>='2026-11-19']
    if not targets:errors.append('no verified trading dates')
    try:
        x,h=get(OT);anchor,records=parse_ot(x)
        if not latest or anchor>latest:raise ValueError('OTC ahead of verified market')
        for d in targets:
            if d in records:append(folder,d,'OTC',{**records[d],'source':OT,'source_hash':h,'scope':'TPEx overview foreignBSN'})
            elif not (read(folder/(d+'.json')) or [{'markets':{}}])[-1]['markets'].get('OTC'):errors.append(d+' OTC overview unavailable')
    except Exception as e:errors.append('OTC overview: '+str(e)[:150])
    def pair(d):
        out=[]
        for k,u,parser in [('TSE',TW+d.replace('-',''),parse_tw),('OTC_detail',DETAIL+d.replace('-','/')+'&response=json',parse_detail)]:
            try:
                x,h=get(u);out.append((k,{**parser(x,d),'source':u,'source_hash':h},None))
            except Exception as e:out.append((k,None,str(e)[:150]))
        return d,out
    todo=[d for d in targets if d==latest or not {'TSE','OTC_detail'}.issubset((read(folder/(d+'.json')) or [{'markets':{}}])[-1]['markets'])]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for d,out in pool.map(pair,todo):
            for k,r,e in out:
                if e:errors.append(d+' '+k+': '+e)
                else:append(folder,d,k,r)
    rows=[]
    for p in sorted(folder.glob('????-??-??.json')):
        v=read(p)
        if not v:continue
        r=v[-1];m=r['markets'];a=m.get('TSE',{}).get('net_yuan');b=m.get('OTC',{}).get('net_yuan');c=m.get('OTC_detail',{}).get('net_yuan')
        rows.append({**r,'revision_count':len(v),'tse_net_yuan':a,'otc_net_yuan':b,'otc_detail_net_yuan':c,'difference_yuan':a-b if a is not None and b is not None else None,'direction':direction(a,b)})
    last=rows[-1] if rows else {}
    state='ok' if latest and last.get('date')==latest and last.get('direction') is not None and not any(e.startswith(latest+' TSE:') or e.startswith(latest+' OTC overview') or e.startswith('OTC overview:') for e in errors) else 'partial'
    result=dict(version='foreign-flow-v1',state=state,market_date=latest,latest_date=last.get('date'),checked_at=stamp(),history_count=len(rows),errors=errors,rows=rows[-5:])
    save(data/'foreign.json',result);print('Foreign flow:',state,[(r['date'],r['tse_net_yuan'],r['otc_net_yuan'],r['direction']) for r in rows[-5:]],errors);return result
