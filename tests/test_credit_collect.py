import sys, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import credit_collect as c
def fixture():
    return {'stat':'OK','date':'20261125','days':5,'data':[
    {'date':'20261124','crdAmt':60706772260,'keepRate':172.39,'belowAccNum':192,'callAccNum':32,'callAmt':11929000,'exeAccNum':2,'exeAmt':10390550,'marginAccNum':41526,'marginAccRate':0.15},
    {'date':'20261125','crdAmt':117662671580,'keepRate':161.96,'belowAccNum':201,'callAccNum':87,'callAmt':44046000,'exeAccNum':7,'exeAmt':2112700,'marginAccNum':61976,'marginAccRate':0.23}]}
class TestCredit(unittest.TestCase):
    def test_parse(self):
        r=c.parse(fixture(),'2026-11-25')['2026-11-25']
        self.assertEqual((r['keepRate'],r['marginAccNum'],r['belowAccNum'],r['callAccNum']),(161.96,61976,201,87))
    def test_missing(self):
        f=fixture(); del f['data'][0]['belowAccNum']
        with self.assertRaises(ValueError):c.parse(f,'2026-11-25')
    def test_wrong_date(self):
        with self.assertRaises(ValueError):c.parse(fixture(),'2026-11-24')
    def test_duplicate(self):
        f=fixture();f['data'].append(f['data'][0])
        with self.assertRaises(ValueError):c.parse(f,'2026-11-25')
    def test_future(self):
        f=fixture();f['data'][0]['date']='20261126'
        with self.assertRaises(ValueError):c.parse(f,'2026-11-25')
    def test_history_revision_and_failure(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);(d/'daily').mkdir()
            for day in ('2026-11-24','2026-11-25'):(d/'daily'/(day+'.json')).write_text('{}')
            records=c.parse(fixture(),'2026-11-25')
            with patch.object(c,'fetch',return_value=records): x=c.run(d);c.run(d)
            self.assertEqual(x['state'],'ok');self.assertEqual(x['history_count'],2)
            self.assertAlmostEqual(x['rows'][-1]['belowAccChangePct'],4.6875)
            self.assertAlmostEqual(x['rows'][-1]['marginAccChangePct'],100*(61976/41526-1))
            self.assertEqual(x['rows'][-1]['threshold_pct'],120)
            p=d/'credit_history'/'2026-11-25.json';self.assertEqual(len(c.read(p)),1)
            records['2026-11-25']['callAccNum']=88
            with patch.object(c,'fetch',return_value=records):c.run(d)
            self.assertEqual(len(c.read(p)),2)
            with patch.object(c,'fetch',side_effect=ValueError('unavailable')):y=c.run(d)
            self.assertEqual(y['state'],'error');self.assertEqual(y['history_count'],2)
            self.assertEqual(y['rows'][-1]['callAccNum'],88)
    def test_zero_denominator(self): self.assertIsNone(c.change(2,0))
