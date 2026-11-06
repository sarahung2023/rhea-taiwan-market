import unittest, json, urllib.request
class TPExSchemaProbe(unittest.TestCase):
    def test_public_source_field_diagnostics(self):
        sources={
            'otc_companies':'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O',
            'otc_quotes':'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
        }
        for name,url in sources.items():
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
                with urllib.request.urlopen(req,timeout=22) as stream:
                    data=json.loads(stream.read(18000000).decode('utf-8-sig'))
                print('RHEA_SCHEMA_'+name, 'rows',len(data),'fields', list(data[0]) if data else [], flush=True)
                for row in data[:3]:
                    interesting={k:v for k,v in row.items() if any(s in k.lower() for s in ('share','volume','common','issued','stock','open','trade','capital'))}
                    print('RHEA_SAMPLE_'+name,interesting,flush=True)
            except Exception as e:
                print('RHEA_PROBE_ERROR_'+name,type(e).__name__,str(e)[:180],flush=True)
