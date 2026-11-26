import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from foreign_collect import parse_tw,parse_ot,parse_detail,direction,append
from credit_collect import read
class ForeignTests(unittest.TestCase):
    def test_tw(self):
        x={'stat':'OK','date':'20261125','fields':['單位名稱','買進金額','賣出金額','買賣差額'],'data':[['外資及陸資(不含外資自營商)','100','200','-100']]}
        self.assertEqual(parse_tw(x,'2026-11-25')['net_yuan'],-100)
        with self.assertRaises(ValueError):parse_tw(x,'2026-11-24')
        x['data'][0][3]='100'
        with self.assertRaises(ValueError):parse_tw(x,'2026-11-25')
    def test_ot(self):
        x={'dataDate':1151125,'big3':{'fn':-65.72},'foreignBSN':[{'date':'11-25','b':628.87,'s':694.59,'n':-65.72}]}
        self.assertEqual(parse_ot(x)[1]['2026-11-25']['net_yuan'],-6572000000)
        x['foreignBSN']*=2
        with self.assertRaises(ValueError):parse_ot(x)
    def test_detail(self):
        x={'stat':'ok','date':'20261125','tables':[{'fields':['單位名稱','買進金額(元)','賣出金額(元)','買賣超(元)'],'data':[['　外資及陸資(不含自營商)','100','200','-100']]}]}
        self.assertEqual(parse_detail(x,'2026-11-25')['net_yuan'],-100)
    def test_direction(self):
        self.assertEqual(direction(-1,1),'TSE賣／OTC買')
        self.assertEqual(direction(0,1),'含零值')
        self.assertIsNone(direction(None,1))
    def test_history(self):
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);d='2026-11-25';r={'buy_yuan':1,'sell_yuan':2,'net_yuan':-1,'precision_yuan':1,'source':'test'}
            append(p,d,'TSE',r);append(p,d,'TSE',r);append(p,d,'OTC',r)
            self.assertEqual(len(read(p/(d+'.json'))),2)
