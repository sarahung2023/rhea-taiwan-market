import unittest, urllib.request, json, concurrent.futures, time
DATES='20260921 20260922 20260923 20260924 20260929 20260930 20261001 20261002 20261005 20261006 20261007 20261008 20261012 20261013 20261014 20261015 20261016 20261019 20261020 20261021 20261022 20261027 20261028 20261029 20261030 20261102 20261103 20261104 20261105'.split()
def get(url):
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
   with urllib.request.urlopen(req,timeout=30) as resp: return json.loads(resp.read(20_000_000).decode('utf-8-sig'))
  except Exception as e:
   if attempt==2:raise
   time.sleep(1+attempt)
def n(x):
 try:return int(str(x).strip().replace(',',''))
 except:return None
def one(arg):
 date,market=arg
 try:
  if market=='TSE':
   j=get(f'https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={date}&selectType=ALL&response=json')
   rows=j.get('data',[])
   totals=[x for x in rows if len(x)>12 and str(x[1]).strip()=='合計' and all(n(x[k]) is not None for k in (8,9,10,11,12))]
   if len(totals)!=1:raise ValueError('no unique official total')
   a=totals[0]
   vals=[n(a[k]) for k in (8,9,10,11,12)]
   source=j.get('date')
   count=len(rows)
  else:
   d=f'{int(date[:4])-1911}/{date[4:6]}/{date[6:8]}'
   j=get(f'https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&d={d}&s=0,asc,0&o=json')
   t=j.get('tables',[])
   if len(t)!=1:raise ValueError('unexpected OTC tables')
   rows=t[0]['data']
   a=[x for x in rows if len(x)>12 and all(n(x[k]) is not None for k in (8,9,10,11,12))]
   if len(a)<750:raise ValueError('OTC rows incomplete: '+str(len(a)))
   vals=[sum(n(r[k]) for r in a) for k in (8,9,10,11,12)]
   source=j.get('date')
   count=len(a)
  prev,sell,buy,adjust,balance=vals
  err=balance-prev-(sell-buy+adjust)
  return {'d':date,'m':market,'asof':source,'n':count,'prev':prev,'sell':sell,'buy':buy,'adjust':adjust,'bal':balance,'delta':balance-prev,'err':err}
 except Exception as e:
  return {'d':date,'m':market,'error':str(e)[:160]}
class Check(unittest.TestCase):
 def test_extract_full_market(self):
  jobs=[(date,market) for date in DATES for market in ('TSE','OTC')]
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
   data=list(pool.map(one,jobs))
  for item in data:print('RHEA_FULL_SBL',json.dumps(item,ensure_ascii=False,separators=(',',':')),flush=True)
  print('RHEA_FULL_SBL_SUMMARY',json.dumps({'success':sum('bal' in x for x in data),'n':len(data),'errs':[x for x in data if x.get('error') or x.get('err')]},ensure_ascii=False),flush=True)
