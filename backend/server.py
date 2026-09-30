"""Local-only contract demo. No real authentication, hardware or model inference."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json, sqlite3, uuid
from contextlib import contextmanager
from dataclasses import asdict
from .domain import Monitor, SearchEvent

DB = Path(__file__).parent / 'demo.sqlite3'

@contextmanager
def connect():
    conn = sqlite3.connect(DB)
    conn.execute('CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

class Handler(BaseHTTPRequestHandler):
    def respond(self, code, body):
        data=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health': return self.respond(200,{'mode':'mock','model_loaded':False})
        if self.path == '/v1/devices': return self.respond(200,{'items':[{'id':'demo-shoe-001','status':'mock_online','battery':86}]})
        if self.path == '/v1/events':
            with connect() as c: rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM events')]
            return self.respond(200,{'items':rows})
        self.respond(404,{'error':'not_found'})

    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 65536: return self.respond(413,{'error':'invalid_body_size'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('JSON object required')
            if self.path == '/v1/demo/events':
                # Explicit fixture endpoint. Does not accept GPS and pretend to run LSTM.
                event={'id':str(uuid.uuid4()),'subject_id':'demo-elder-001','mode':'mock',
                       'created_at':datetime.now(timezone.utc).isoformat(),**asdict(SearchEvent())}
                with connect() as c: c.execute('INSERT INTO events VALUES (?,?)',(event['id'],json.dumps(event)))
                return self.respond(201,event)
            if self.path.startswith('/v1/events/') and self.path.endswith('/actions'):
                event_id=self.path.split('/')[3]
                with connect() as c:
                    row=c.execute('SELECT payload FROM events WHERE id=?',(event_id,)).fetchone()
                    if not row:return self.respond(404,{'error':'event_not_found'})
                    event=json.loads(row[0]);machine=SearchEvent(event['state'],event['search_level'])
                    event.update(machine.act(body.get('action')))
                    c.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(event),event_id))
                return self.respond(200,event)
            if self.path == '/v1/telemetry':
                return self.respond(501,{'error':'hardware_adapter_not_implemented','mode':'mock'})
            return self.respond(404,{'error':'not_found'})
        except (ValueError,TypeError,KeyError) as e: self.respond(400,{'error':str(e)})

if __name__=='__main__':
    print('Mock API http://127.0.0.1:8787 · no model loaded')
    HTTPServer(('127.0.0.1',8787),Handler).serve_forever()
