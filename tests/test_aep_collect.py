import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import aep_collect as a

def snap(d, units, shares, status='ok'):
    return {'status':status,'data_date':d,'meta':{'units':units,'nav_per_unit':10,'scale':units*10},'holdings':[{'code':'2330','shares':shares},{'code':'2317','shares':1000}]}

class AEPTests(unittest.TestCase):
    def test_pair_and_same_day(self):
        x=a.pair(snap('2026-11-23',1000,100),snap('2026-11-24',1100,90),'2026-11-23','2026-11-24')
        self.assertEqual(x['unit_delta'],100)
        self.assertEqual(x['estimate'],1000)
        self.assertEqual(x['down'],1)
        with self.assertRaises(ValueError):
            a.pair(snap('2026-11-23',1000,100),snap('2026-11-23',1100,90),'2026-11-23','2026-11-24')
        with self.assertRaises(ValueError):
            a.pair(snap('2026-11-23',1000,100),snap('2026-11-24',1100,90,'stale'),'2026-11-23','2026-11-24')
    def test_coverage_clock_and_revisions(self):
        p,d,n='2026-11-23','2026-11-24','2026-11-25'
        s={(k,x):{'data':snap(x,1000+(x==d)*100,100),'batch':x,'hash':'example'} for k in a.COHORT for x in (p,d)}
        row=a.summarize(d,p,n,s,'2026-11-25T08:29:00+08:00',{p,d})
        self.assertEqual(row['aep1'],100)
        self.assertTrue(row['timely'])
        late=a.summarize(d,p,n,s,'2026-11-25T08:31:00+08:00',{p,d})
        self.assertFalse(late['timely'])
        s.pop((a.COHORT[0],d))
        missing=a.summarize(d,p,n,s,'2026-11-25T08:29:00+08:00',{p,d})
        self.assertIsNone(missing['aep1'])
        self.assertFalse(missing['timely'])
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(len(a.append_version(Path(t),row)),1)
            self.assertEqual(len(a.append_version(Path(t),late)),1)
            self.assertEqual(len(a.append_version(Path(t),missing)),2)
    def test_calendar(self):
        c={'coverage_start':'2026-11-01','coverage_end':'2026-12-31','closed_dates':[]}
        self.assertEqual(a.adjacent('2026-11-23',-1,c),'2026-11-20')
        self.assertEqual(a.adjacent('2026-11-20',1,c),'2026-11-23')
        self.assertRaises(ValueError,a.adjacent,'2026-12-31',1,c)
    def test_same_source_revision_and_missing_metadata(self):
        p,d,n='2026-11-23','2026-11-24','2026-11-25'
        k=a.COHORT[0]
        s={(k,p):{'data':snap(p,1000,100),'batch':p,'hash':'a'},(k,d):{'data':snap(d,1100,100),'batch':d,'hash':'b'}}
        r=a.summarize(d,p,n,s,'2026-11-25T08:00:00+08:00',{p,d},{'etfs':{k:snap(d,1100,999)}})
        self.assertEqual(r['n'],0)
        self.assertIn('修訂差異',r['missing'][k])
        bad=snap(d,1100,100);bad['meta']['units']=None
        self.assertRaises(ValueError,a.pair,snap(p,1000,100),bad,p,d)
