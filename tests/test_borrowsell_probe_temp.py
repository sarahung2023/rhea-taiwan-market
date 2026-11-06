import unittest, urllib.request, urllib.error, json, concurrent.futures, datetime, time, re
DATES='20260921 20260922 20260923 20260924 20260929 20260930 20261001 20261002 20261005 20261006 20261007 20261008 20261012 20261013 20261014 20261015 20261016 20261019 20261020 20261021 20261022 20261027 20261028 20261029 20261030 20261102 20261103 20261104 20261105'.split()
def get_json(url):
 last=None
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
   with urllib.request.urlopen(req,timeout=32) as res:
    raw=res.read(20_000_000)
   return json.loads(raw.decode('utf-8-sig'))
  except Exception as e:
   last=e
   time.sleep(.5*(attempt+1))
 raise last
def num(x):
 try:return int(str(x).replace(',','').strip())
 except:return None
def iscode(c):
 return bool(re.fullmatch(r'[1-9][0-9]{3}',str(c).strip()))
def get_day(task):
 date,market=task
 if market=='TSE':
  url=f'https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={date}&selectType=ALL&response=json'
 else:
  d=f'{int(date[:4])-1911}/{date[4:6]}/{date[6:8]}'
  url=f'https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&d={d}&s=0,asc,0&o=json'
 try:
  data=get_json(url)
  if market=='TSE':
   rows=data.get('data',[]);field=data.get('fields',[])
   date_api=str(data.get('date'))
  else:
   t=data.get('tables',[])
   rows=t[0]['data'] if t else [];field=t[0]['fields'] if t else []
   date_api=str(data.get('date'))
  # TSE and OTC both have short sale balance in zero-based fields 8,9,10,11,12.
  qualified=[r for r in rows if len(r)>=13 and iscode(r[0])]
  processed=[r for r in qualified if all(num(r[k]) is not None for k in (8,9,10,11,12))]
  if len(processed)<400:raise ValueError(f'Unreliable regular-stock row count: {len(processed)} of {len(rows)}')
  sums=[sum(num(r[k]) for r in processed) for k in (8,9,10,11,12)]
  prev,sell,returned,adjust,bal=sums
  delta=bal-prev
  integrity=delta-(sell-returned+adjust)
  result={'d':date,'m':market,'source_date':date_api,'rows':len(rows),'stocks':len(processed),'bal_shares':bal,
   'delta_shares':delta,'sold_shares':sell,'returned_shares':returned,'adjust_shares':adjust,'net_identity_error':integrity}
  return result
 except Exception as e:
  return {'d':date,'m':market,'error':type(e).__name__+': '+str(e)[:100]}
class OfficialBorrowSellResearch(unittest.TestCase):
 def test_29_date_history(self):
  jobs=[(d,m) for d in DATES for m in ('TSE','OTC')]
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
   items=list(pool.map(get_day,jobs))
  for item in items:print('RHEA_BS_RESULT',json.dumps(item,ensure_ascii=False,separators=(',',':')),flush=True)
  print('RHEA_BS_SUMMARY',json.dumps({'requested':len(jobs),'completed':sum('bal_shares' in x for x in items),'errors':[x for x in items if 'error' in x]},ensure_ascii=False),flush=True)
