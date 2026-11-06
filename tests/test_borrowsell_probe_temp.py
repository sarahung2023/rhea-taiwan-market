import unittest, urllib.request, urllib.error, json, concurrent.futures
URLS={
 "twse_twt93u":"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=20261105&selectType=ALL&response=json",
 "twse_twt93u_alt":"https://www.twse.com.tw/rwd/zh/trading/margin/TWT93U?date=20261105&selectType=ALL&response=json",
 "twse_openapi":"https://openapi.twse.com.tw/v1/exchangeReport/TWT93U",
 "tpex_sbl_hist":"https://www.tpex.org.tw/www/zh-tw/mainboard/trading/margin-trading/sbl?date=2026/11/05&response=json",
 "tpex_sbl_hist2":"https://www.tpex.org.tw/zh-tw/mainboard/trading/margin-trading/sbl.html?date=2026/11/05&response=json",
 "tpex_sbl_legacy":"https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl.php?l=zh-tw&d=115/11/05",
 "tpex_openapi":"https://www.tpex.org.tw/openapi/v1/tpex_margin_sbl",
 "tpex_2nd":"https://www.tpex.org.tw/www/zh-tw/mainboard/trading/margin-trading/sbl?date=115/11/05&response=json"
}
def one(a):
 name,url=a
 try:
  r=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'}),timeout=23)
  b=r.read(15_000_000);txt=b.decode('utf-8-sig',errors='replace')
  try:
   j=json.loads(txt)
   keys=list(j) if isinstance(j,dict) else []
   arr=j.get('data',j.get('tables',[])) if isinstance(j,dict) else j
   typ=type(j).__name__;count=len(arr) if arr else 0
   sample=str(arr[0] if arr else '')[:240]
   fields=str(j.get('fields',''))[:240] if isinstance(j,dict) else ''
   return name,'OK',r.status,typ,keys[:18],count,sample,fields
  except ValueError:return name,'HTML',r.status,len(txt),txt[:230]
 except Exception as e:return name,'ERR',str(e)[:180]
class Probe(unittest.TestCase):
 def test_urls(self):
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as p:
   for r in p.map(one,URLS.items()): print('RHEA_SBL_PROBE',json.dumps(r,ensure_ascii=False),flush=True)
