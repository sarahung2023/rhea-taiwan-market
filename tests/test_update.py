import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update as u

class UnitChecks(unittest.TestCase):
    def test_roc_dates(self):
        self.assertEqual(u.iso_date('1151028'),'2026-10-28')
        self.assertEqual(u.iso_date('115/10/28'),'2026-10-28')
        self.assertRaises(ValueError,u.iso_date,'1151332')
    def test_numeric_and_corporate_actions(self):
        self.assertEqual(u.num('1,234.5'),1234.5)
        self.assertEqual(u.num('－2.5'),-2.5)
        self.assertIsNone(u.num('X0.50'))
        self.assertIsNone(u.num('—'))
        self.assertIsNone(u.num('1e100'))
    def test_market_schemas_distinct(self):
        a=u.companies([{'公司代號':f'{1000+i}', '產業別':'24'} for i in range(350)],'TWSE')
        b=u.companies([{'SecuritiesCompanyCode':f'{2000+i}','SecuritiesIndustryCode':'25'} for i in range(350)],'TPEx')
        self.assertEqual(a['1000']['industry'],'24')
        self.assertEqual(b['2000']['industry'],'25')
    def test_exclude_etf_and_bad_changes(self):
        rows=[{'Code':'2340','Name':'台亞','ClosingPrice':'11','Change':'1','TradeValue':'100000000'},
              {'Code':'0050','Name':'ETF','ClosingPrice':'200','Change':'2'},
              {'Code':'1234','ClosingPrice':'100','Change':'X1'}]
        d=u.normalize(rows,'TWSE')
        self.assertEqual(list(d),['2340'])
        self.assertAlmostEqual(d['2340']['pct'],10.0)
    def test_group_equal_weight_industry(self):
        stocks={str(i):{'code':str(i),'name':str(i),'market':'TWSE','pct':pct,'amount':100}
                for i,pct in [(1234,1),(1235,2),(1236,3),(1237,-6),(1238,0)]}
        catalog={k:{'industry':'24'} for k in stocks}
        result=u.daily_result('2026-10-29',{'TWSE':stocks,'TPEx':{}},{'TWSE':catalog,'TPEx':{}},
            [{'id':'custom','name':'樣本','min_n':3,'members':['1234','1235','1236']}])
        self.assertEqual(result['sectors']['custom']['avg'],2)
        self.assertEqual(result['sectors']['custom']['up'],3)
        self.assertEqual(result['sectors']['official-24']['avg'],0)
    def test_official_includes_small_industries(self):
        stocks={'1234':{'code':'1234','name':'測試','market':'TWSE','pct':-3.5,'amount':100}}
        catalog={'1234':{'industry':'38'}}
        result=u.daily_result('2026-10-29',{'TWSE':stocks,'TPEx':{}},
                              {'TWSE':catalog,'TPEx':{}},[])
        sector=result['sectors']['official-38']
        self.assertEqual(sector['name'],'居家生活')
        self.assertEqual(sector['n'],1)
        self.assertAlmostEqual(sector['avg'],-3.5)

    def test_stale_mismatch_and_fail_safe(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); (d/'daily').mkdir()
            dashboard=d/'dashboard.json'; dashboard.write_text('{"status":"ok","protected":true}',encoding='utf-8')
            fake={'TWSE_daily':[{'Date':'1151029'}]*101,'TPEx_daily':[{'Date':'1151028'}]*101}
            def fetch(url,**kw):
                if 'STOCK_DAY_ALL' in url:return fake['TWSE_daily']
                if 'daily_close_quotes' in url:return fake['TPEx_daily']
                return []
            with patch.object(u,'DATA',d), patch.object(u,'DAILY',d/'daily'),patch.object(u,'fetch_json',side_effect=fetch), patch.object(u,'fetch_twse_mi_index',side_effect=RuntimeError('synthetic unavailable')):
                self.assertEqual(u.update(),1)
                self.assertEqual(json.loads(dashboard.read_text())['protected'],True)
                self.assertFalse(json.loads((d/'status.json').read_text())['ok'])
    def test_twse_mi_index_official_backup_validation(self):
        fields=['證券代號','證券名稱','收盤價','漲跌(+/-)','漲跌價差','成交金額']
        table={'fields':fields,'data':[['2330','台積電','105','<p style=color:red>+</p>','5','1,000,000'],
                                        ['2317','鴻海','98','<p style=color:green>-</p>','2','2,000,000'],
                                        ['2303','聯電','50','<p> </p>','0','500,000'],
                                        ['2340','台亞','49','<p>X</p>','0','10,000']]}
        table['data'] += [[str(1000+i),'測試','100','+','1','10,000'] for i in range(800)]
        data={'stat':'OK','date':'20261029','tables':[table]}
        out=u.parse_twse_mi_index(data,'2026-10-29')
        rows=u.normalize(out,'TWSE')
        self.assertEqual(rows['2330']['pct'],5)
        self.assertEqual(rows['2317']['pct'],-2)
        self.assertEqual(rows['2303']['pct'],0)
        self.assertNotIn('2340',rows)
        self.assertRaises(ValueError,u.parse_twse_mi_index,data,'2026-10-28')
    def test_twse_mi_index_rejects_wrong_table(self):
        data={'stat':'OK','date':'20261029','tables':[{'fields':['證券代號','收盤價'],'data':[['2330','100']]}]}
        self.assertRaises(ValueError,u.parse_twse_mi_index,data,'2026-10-29')
    def test_full_fake_coverage_pipeline(self):
        # Fully synthetic records, only test artifacts within temporary directory.
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); (d/'daily').mkdir()
            (d/'themes.json').write_text(json.dumps({'version':'test','groups':
                [{'id':'test-sector','name':'測試類股','members':['2000','2001','1000'], 'min_n':2}]}),encoding='utf-8')
            tw_quotes=[{'Date':'1151029','Code':str(1000+i),'Name':f'TSE{i}',
                        'ClosingPrice':'101','Change':'1','TradeValue':'1000000'} for i in range(900)]
            ot_quotes=[{'Date':'1151029','SecuritiesCompanyCode':str(2000+i),'CompanyName':f'TPEx{i}',
                        'Close':'99','Change':'-1','TransactionAmount':'1000000'} for i in range(700)]
            tw_companies=[{'公司代號':str(1000+i),'產業別':str(i%22+1).zfill(2)} for i in range(900)]
            ot_companies=[{'SecuritiesCompanyCode':str(2000+i),'SecuritiesIndustryCode':str(i%22+1).zfill(2)} for i in range(700)]
            def fetch(url,**kw):
                if 'STOCK_DAY_ALL' in url:return tw_quotes
                if 'daily_close_quotes' in url:return ot_quotes
                if 't187ap03_L' in url:return tw_companies
                if 't187ap03_O' in url:return ot_companies
                return [{'證券代號':'2340','證券名稱':'台亞','公告日期':'1151029'}]
            with patch.object(u,'DATA',d),patch.object(u,'DAILY',d/'daily'),patch.object(u,'THEMES',d/'themes.json'),\
                 patch.object(u,'fetch_json',side_effect=fetch),patch.object(u,'now_iso',return_value='2026-10-29T16:17:00+08:00'):
                self.assertEqual(u.update(),0)
                page=json.loads((d/'dashboard.json').read_text())
                self.assertEqual(page['dates'],['2026-10-29'])
                self.assertEqual(page['coverage'],{'TWSE':900,'TPEx':700})
                self.assertEqual(page['days'][0]['sectors']['test-sector']['n'],3)
                self.assertGreaterEqual(len(page['days'][0]['sectors']),16)
                alerts=json.loads((d/'alerts.json').read_text())
                self.assertEqual(alerts['items']['TWSE_notice']['rows'][0]['code'],'2340')

if __name__=='__main__': unittest.main()
