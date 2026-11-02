import sys
import unittest
import tempfile
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from overnight_proxy import active_pool, make_pair, build_overview

class OvernightPublicProxyTests(unittest.TestCase):
    def test_pool_preselected_by_prior_traded_value(self):
        q={'TWSE':{'1234':{'code':'1234','close':100,'pct':3,'amount':1000},
                   '1235':{'code':'1235','close':200,'pct':-1,'amount':200}},
           'TPEx':{'2345':{'code':'2345','close':50,'pct':4,'amount':2000}}}
        self.assertEqual([x['code'] for x in active_pool(q,2)],['2345','1234'])
    def test_path_pattern_not_actual_trader_share(self):
        previous={'date':'2026-10-29','active_candidates':[
            {'market':'TWSE','code':str(1000+i),'close':100,'pct':3,'amount':100000-i}
            for i in range(80)]}
        q={'TWSE':{str(1000+i):{'code':str(1000+i),'open':102,'close':100,'pct':0}
                   for i in range(80)},'TPEx':{}}
        p=make_pair(previous,'2026-10-30',q)
        self.assertEqual(p['matched'],80)
        self.assertEqual(p['events'],80)
        self.assertEqual(p['eligible'],80)
        self.assertEqual(p['event_pct'],100)
    def test_missing_open_is_not_guessed(self):
        prior={'date':'2026-10-29','active_candidates':[
            {'market':'TWSE','code':str(1000+i),'close':100,'pct':3}
            for i in range(80)]}
        q={'TWSE':{str(1000+i):{'code':str(1000+i),'open':None,'close':95}
                   for i in range(80)},'TPEx':{}}
        self.assertEqual(make_pair(prior,'2026-10-30',q)['status'],'insufficient')
    def test_five_days_and_twenty_day_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            from datetime import date, timedelta
            start=date(2026,8,1)
            for i in range(25):
                day=(start+timedelta(days=i)).isoformat()
                pair={'status':'ok','date':day,'matched':100,'eligible':20,'events':2,
                      'fades':3,'event_pct':2.0,'fade_pct':3.0}
                (d/(day+'.json')).write_text(json.dumps({'date':day,'overnight_pair':pair}))
            v=build_overview(d)
            self.assertEqual(v['days_observed'],5)
            self.assertEqual(v['event_pct'],2.0)
            self.assertEqual(v['previous_20day_event_pct'],2.0)

if __name__=='__main__':unittest.main()
