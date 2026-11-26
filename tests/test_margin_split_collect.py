import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from margin_split_collect import valuation,otc_amounts,number,unique
class MarginSplitTests(unittest.TestCase):
    def test_reference_and_missing(self):
        v=valuation({'A':2,'B':1},{'A':('20',None),'B':('---','10')},number(25000))
        self.assertEqual(v['maintenance_pct'],200)
        self.assertEqual(v['valuation_status'],'reference_estimate')
        self.assertEqual(v['reference_prices'][0]['code'],'B')
        v=valuation({'A':2,'B':1},{'A':('20',None)},number(25000))
        self.assertIsNone(v['maintenance_pct'])
        self.assertEqual(v['missing_prices'][0]['code'],'B')
    def test_amount(self):
        d,rows=otc_amounts({'dataDate':'1151125','marginPurchaseValue10Days':[{'date':'11-25','amt':1278.78,'dif':-9.69}],'marginPurchaseValue':{'mbal':1278.78,'mdif':-9.69}})
        self.assertEqual(d,'2026-11-25')
        self.assertEqual(rows[d]['balance_yuan'],127878000000)
        self.assertEqual(rows[d]['previous_balance_yuan'],128847000000)
    def test_duplicate(self):
        with self.assertRaises(ValueError):unique([('A',1),('A',2)])
