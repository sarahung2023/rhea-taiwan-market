"""Deterministic ETF stock-monitor aggregation tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from aep_collect import stock_monitor, stock_window

DAY='2026-11-26'
PREV='2026-11-25'
F1='00981A'
F2='00991A'
def snap(day, shares):
    return {'data':{'status':'ok','data_date':day,'meta':{'units':10000,'nav_per_unit':10,'scale':100000},
                    'holdings':[{'code':k,'name':k,'shares':v} for k,v in shares.items()]}}
def fixtures():
    return {
        (F1,PREV):snap(PREV,{'2330':1000000,'2408':2000000,'2454':1000000,'2881':1000000}),
        (F1,DAY):snap(DAY,{'2330':2000000,'2408':1000000,'2454':2000000,'2881':1000000}),
        (F2,PREV):snap(PREV,{'2330':2000000,'2408':1000000,'2454':1000000,'2881':1000000}),
        (F2,DAY):snap(DAY,{'2330':1000000,'2408':2000000,'2454':1000000,'2881':1000000})
    }
def record():
    return {'date':DAY,'sectors':{
      'official-24':{'type':'official','name':'半導體','members':[{'code':c,'market':'TWSE','name':c} for c in ('2330','2408','2454')]},
      'official-17':{'type':'official','name':'金融保險','members':[{'code':'2881','market':'TWSE','name':'2881'}]},
      'theme-1':{'type':'custom','name':'重複題材','members':[{'code':'2330','market':'TWSE'}]}},
      'aep_stock_quotes':{'TWSE':{'2330':{'close':100},'2408':{'close':50},'2881':{'close':20}}}}
class StockMonitorTests(unittest.TestCase):
    def test_gross_net_price_and_sector(self):
        x=stock_monitor(DAY,PREV,fixtures(),{'stocks':{'2330':{'close':999,'quote_date':DAY},'2454':{'close':999,'quote_date':PREV}}},record(),'now',cohort=(F1,F2))
        self.assertEqual(x['state'],'complete')
        self.assertEqual(x['n'],2)
        rows={r['code']:r for r in x['stocks']}
        r=rows['2330']
        self.assertEqual(r['hold_etfs'],[F1,F2])
        self.assertEqual(r['up_etfs'],[F1])
        self.assertEqual(r['down_etfs'],[F2])
        self.assertEqual(r['market_value_100m'],3)
        self.assertEqual(r['increase_100m'],1)
        self.assertEqual(r['decrease_100m'],1)
        self.assertEqual(r['net_100m'],0)
        self.assertEqual(r['price_source'],'official')
        self.assertIsNone(rows['2454']['net_100m'])
        self.assertEqual(x['price_sources'],{'official':3,'missing':1})
        sectors={g['industry']:g for g in x['sectors']}
        self.assertEqual(set(sectors),{'半導體','金融保險'})
        self.assertEqual(sectors['半導體']['increase_100m'],1.5)
        self.assertEqual(sectors['半導體']['decrease_100m'],1.5)
        self.assertEqual(sectors['半導體']['unpriced_changes'],1)
        self.assertEqual(sectors['金融保險']['net_100m'],0)
    def test_missing_and_stale_pairs(self):
        s=fixtures();s[(F2,DAY)]=snap(PREV,{'2330':1000000})
        x=stock_monitor(DAY,PREV,s,{},record(),'now',cohort=(F1,F2))
        self.assertEqual(x['state'],'partial')
        self.assertEqual(x['missing'],[F2])
        self.assertEqual(next(r for r in x['stocks'] if r['code']=='2330')['hold_etfs'],[F1])
    def test_exact_date_fallback(self):
        x=stock_monitor(DAY,PREV,fixtures(),{'stocks':{'2454':{'close':60,'quote_date':DAY}}},record(),'now',cohort=(F1,F2))
        r=next(r for r in x['stocks'] if r['code']=='2454')
        self.assertEqual(r['price_source'],'upstream_same_day')
        self.assertEqual(r['net_100m'],0.6)
class StockWindowTests(unittest.TestCase):
    def daily(self, day, prev, delta, price=100, before=True, after=True):
        h=['00981A'] if after else []
        old=['00981A'] if before else []
        up=max(delta,0);down=max(-delta,0)
        return {'version':'AEP-STOCK-v2','date':day,'previous_date':prev,'observed_at':day+'T22:00:00',
          'n':1,'expected':1,'state':'complete','price_sources':{'official':1} if price else {'missing':1},
          'stocks':[{'code':'2330','name':'台積電','industry':'半導體','shares':1000000 if after else 0,
            'hold_etfs':h,'previous_hold_etfs':old,'up_etfs':['00981A'] if up else [],
            'down_etfs':['00981A'] if down else [],'net_shares':delta,'increase_shares':up,'decrease_shares':down,
            'close':price,'market_value_100m':price/100 if price and after else (0 if not after else None),
            'increase_100m':up*price/1e8 if price else None,'decrease_100m':down*price/1e8 if price else None,
            'net_100m':delta*price/1e8 if price else None}]}
    def test_window_price_and_days(self):
        dates=['2026-11-24','2026-11-25','2026-11-26']
        records={dates[0]:self.daily(dates[0],'2026-11-23',1000000,100,False),
                 dates[1]:self.daily(dates[1],dates[0],-1000000,200,True,False),
                 dates[2]:self.daily(dates[2],dates[1],1000000,300,False)}
        w=stock_window(dates,records,3,cohort=(F1,))
        self.assertEqual(w['state'],'complete')
        r=w['stocks'][0]
        self.assertEqual(r['increase_100m'],4)
        self.assertEqual(r['decrease_100m'],2)
        self.assertEqual(r['net_100m'],2)
        self.assertEqual((r['up_days'],r['down_days']),(2,1))
        self.assertEqual(r['up_etfs'],[F1])
        self.assertEqual((r['previous_hold_count'],r['hold_count_change']),(0,1))
        self.assertEqual(w['sectors'][0]['net_100m'],2)
        self.assertEqual(stock_window(dates,records,5,cohort=(F1,))['state'],'waiting')
        records[dates[1]]['previous_date']='2026-11-23'
        self.assertEqual(stock_window(dates,records,3,cohort=(F1,))['state'],'waiting')
    def test_missing_price_and_partial_pair(self):
        dates=['2026-11-24','2026-11-25','2026-11-26']
        records={dates[0]:self.daily(dates[0],'2026-11-23',1000000,100),
                 dates[1]:self.daily(dates[1],dates[0],-1000000,None),
                 dates[2]:self.daily(dates[2],dates[1],1000000,300)}
        w=stock_window(dates,records,3,cohort=(F1,))
        self.assertEqual(w['state'],'complete')
        self.assertIsNone(w['stocks'][0]['net_100m'])
        self.assertEqual(w['stocks'][0]['missing_price_days'],1)
        self.assertEqual(w['sectors'][0]['unpriced_changes'],1)
        records[dates[1]]['state']='partial'
        self.assertEqual(stock_window(dates,records,3,cohort=(F1,))['valid_days'],2)

if __name__=='__main__':
    unittest.main()
