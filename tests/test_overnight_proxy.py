import sys, unittest, tempfile, json
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from overnight_proxy import active_pool, make_pair, build_overview, VERSION

class HighTurnoverTests(unittest.TestCase):
 def build(self):
  quotes={'TWSE':{},'TPEx':{}}
  companies={'TWSE':{},'TPEx':{}}
  for market in ('TWSE','TPEx'):
   for i in range(250):
    code=str((1000 if market=='TWSE' else 2000)+i)
    companies[market][code]={'issued_shares':1000000}
    quotes[market][code]={'code':code,'close':100,'open':101,'pct':3,
                           'volume':60000 if i<100 else 1000}
  return quotes,companies
 def test_select_all_high_turnover_and_denominator(self):
  q,c=self.build(); p=active_pool(q,c)
  self.assertEqual(p['status'],'ok')
  self.assertEqual(p['universe_count'],500)
  self.assertEqual(p['high_turnover_count'],200)
  self.assertEqual(p['very_high_count'],0)
  self.assertTrue(all(s['turnover_pct']==6 for s in p['candidates']))
 def test_missing_shares_fail_closed(self):
  q,c=self.build()
  for m in c:
   for row in c[m].values(): row['issued_shares']=None
  p=active_pool(q,c)
  self.assertEqual(p['status'],'insufficient')
  self.assertFalse(p['candidates'])
 def test_pair(self):
  q,c=self.build(); pool=active_pool(q,c)
  prev={'date':'2026-10-29','turnover_study':pool}
  for m in q:
   for row in q[m].values():
    row['open']=102; row['close']=100
  p=make_pair(prev,'2026-10-30',q)
  self.assertEqual(p['status'],'ok')
  self.assertEqual(p['matched'],200)
  self.assertEqual(p['fades'],200)
  self.assertEqual(p['events'],200)
  self.assertEqual(p['continuations'],0)
 def test_missing_open_disallows_pair(self):
  q,c=self.build(); prev={'date':'2026-10-29','turnover_study':active_pool(q,c)}
  for m in q:
   for row in q[m].values(): row['open']=None
  self.assertEqual(make_pair(prev,'2026-10-30',q)['status'],'insufficient')
 def test_5_day_no_backfill_and_version_lock(self):
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp); first=date(2026,9,1)
   for i in range(25):
    dt=(first+timedelta(days=i)).isoformat()
    pair={'model_version':VERSION,'date':dt,'status':'ok',
          'universe_count':500,'cohort_count':200,'very_high_count':5,
          'matched':180,'eligible':80,'events':10,'fades':30,'continuations':10}
    (d/(dt+'.json')).write_text(json.dumps({'date':dt,'overnight_pair':pair}))
   o=build_overview(d)
   self.assertEqual(o['status'],'ok')
   self.assertEqual(o['high_density_pct'],40.0)
   self.assertEqual(o['fade_pct'],16.67)
   self.assertTrue(o['baseline_ready'])
   last=(first+timedelta(days=24)).isoformat()
   (d/(last+'.json')).write_text(json.dumps({'date':last,'overnight_pair':{'model_version':'old'}}))
   self.assertEqual(build_overview(d)['status'],'collecting')

if __name__=='__main__': unittest.main()
