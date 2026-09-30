import unittest,tempfile,threading,json
from pathlib import Path
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import backend.server as server
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.temp.name)/'demo.sqlite3'
        self.http=HTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();server.DB=self.old;self.temp.cleanup()
    def request(self,path,body=None):
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urlopen(req) as r:return r.status,json.loads(r.read())
        except HTTPError as e:return e.code,json.loads(e.read())
    def test_http_event_lifecycle(self):
        code,health=self.request('/health');self.assertEqual(code,200);self.assertFalse(health['model_loaded'])
        code,event=self.request('/v1/demo/events',{});self.assertEqual(code,201)
        endpoint='/v1/events/'+event['id']+'/actions'
        code,_=self.request(endpoint,{'action':'confirm_pickup'});self.assertEqual(code,400)
        for action in ['publish','report_clue','confirm_identity','confirm_pickup']:
            code,event=self.request(endpoint,{'action':action});self.assertEqual(code,200)
        self.assertEqual(event['state'],'closed_recovered')
        _,listing=self.request('/v1/events');self.assertEqual(len(listing['items']),1)
    def test_hardware_not_faked(self):
        code,result=self.request('/v1/telemetry',{});self.assertEqual(code,501)
        self.assertEqual(result['error'],'hardware_adapter_not_implemented')
