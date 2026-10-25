import http.client
import json
import pathlib
import pickle
import ssl
import sys
from urllib.parse import parse_qs, urlsplit

root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
from arnproxy import Client, ArnproxyError, verify_webhook

fixture = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
resources = json.loads((root / "resources.json").read_text())["resources"]
checks = 0
def ck(value):
    global checks
    assert value
    checks += 1
def error(call, code):
    try:
        call()
        assert False
    except ArnproxyError as e:
        ck(e.code == code)
        ck(fixture['key'] not in str(e))
        return e

class MockClient(Client):
    def __init__(self, **options):
        super().__init__(fixture['key'], **options)
        self.calls = []
        self.status, self.response_headers, self.raw = 200, {}, json.dumps(fixture['body']).encode()
        self.failure = None
    def _send(self, method, path, headers, body):
        self.calls.append((method, path, headers, body))
        if self.failure:
            raise OSError('sensitive transport detail ' + fixture['key'])
        return self.status, self.response_headers, self.raw

client = MockClient(allow_writes=True, allow_provider_reads=True)
for name, spec in resources.items():
    params = {'id': 123} if '{id}' in spec['path'] else {}
    params['q'] = 'ü & = ? /'
    key = fixture['operation_key'] if spec['idempotency'] else None
    count = len(client.calls)
    if spec['disabled']:
        error(lambda: client.request(name, params, operation_key=key), 'DISABLED_RESOURCE')
        ck(len(client.calls) == count)
        continue
    ck(client.request(name, params, operation_key=key)['data']['id'] == 2)
    method, path, headers, body = client.calls[-1]
    ck(method == spec['method'])
    ck(urlsplit(path).path == '/account/api/v1/' + spec['path'].replace('{id}', '123'))
    ck(fixture['key'] not in path)
    ck(headers['Authorization'] == 'Bearer ' + fixture['key'])
    ck(headers.get('Idempotency-Key') == key)
    if method == 'GET':
        ck(parse_qs(urlsplit(path).query)['q'] == [params['q']])
        ck(body is None)
    else:
        ck(json.loads(body) == params)
    ck(len(client.calls) == count + 1)
    guarded = MockClient()
    if spec['write'] or spec['provider_read']:
        error(lambda: guarded.request(name, params, operation_key=key), 'WRITES_DISABLED' if spec['write'] else 'PROVIDER_READS_DISABLED')
        ck(not guarded.calls)
    if spec['idempotency']:
        error(lambda: client.request(name, params), 'OPERATION_KEY_REQUIRED')
        ck(len(client.calls) == count + 1)

for key in ['', fixture['key']+'\n', ' ' + fixture['key'], 'x'*31]:
    error(lambda: Client(key), 'INVALID_KEY_FORMAT')
error(lambda: client.request('account', {'resource': 'purchase'}), 'INVALID_PARAMETERS')
error(lambda: client.request('proxy', {'id':'1/../../secret'}), 'INVALID_ROUTE_ID')
error(lambda: client.request('orders', {'id': [1,2]}), 'INVALID_QUERY_VALUE')
error(lambda: client.request('quote', {'bad':float('nan')}), 'INVALID_JSON_BODY')
error(lambda: client.request('quote', {'x':'a'*(2*1024*1024)}), 'REQUEST_TOO_LARGE')
client.status,client.raw=302,b''
count=len(client.calls)
ck(error(lambda:client.account(),'REDIRECT_BLOCKED').uncertain is False)
ck(len(client.calls)==count+1)
client.status,client.raw=429,json.dumps({'ok':False,'error':{'code':'RATE_LIMITED'},'meta':{'request_id':fixture['request_id']}}).encode()
client.response_headers={'retry-after':'12'}
e=error(lambda:client.account(),'RATE_LIMITED');ck(e.http_status==429 and e.retry_after==12 and e.request_id==fixture['request_id'])
client.status,client.raw=500,b'<html>not json</html>'
ck(error(lambda:client.request('purchase',{},operation_key=fixture['operation_key']),'INVALID_API_RESPONSE').uncertain is True)
client.failure=True
count=len(client.calls)
ck(error(lambda:client.request('purchase',{},operation_key=fixture['operation_key']),'TRANSPORT_ERROR').uncertain is True)
ck(len(client.calls)==count+1)
client.failure=False;client.status=200;client.raw=json.dumps({'ok':True,'data':{'state':'unknown'},'meta':{'request_id':fixture['request_id']}}).encode()
ck(client.request('purchase',{},operation_key=fixture['operation_key'])['data']['state']=='unknown')
ck(fixture['key'] not in repr(client))
error(lambda:pickle.dumps(client),'SERIALIZATION_DISABLED')
for v in fixture['vectors']:
    call=lambda:verify_webhook(v['body'].encode(),v['headers'],v['secret'],now=v['now'])
    if v['valid']:
        ck(call()['id'].startswith('evt_'))
    else:
        error(call,'WEBHOOK_VERIFICATION_FAILED')

# Native transport contract is exercised with a fake HTTPSConnection, never a socket.
connections=[]
class Socket:
    def settimeout(self,n): ck(n>0)
class Response:
    status=200
    def __init__(self):self.raw=json.dumps(fixture['body']).encode()
    def read1(self,n): value=self.raw[:n];self.raw=self.raw[n:];return value
    def getheader(self,k,d):return '2'
class Connection:
    def __init__(self,host,port,timeout,context):
        ck(host=='www.arnproxy.com' and port==443 and timeout==20)
        ck(context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname)
        self.sock=Socket();self.closed=False;connections.append(self)
    def request(self,*args,**kw):self.sent=(args,kw)
    def getresponse(self):return Response()
    def close(self):self.closed=True
http.client.HTTPSConnection=Connection
ck(Client(fixture['key']).account()['data']['id']==2)
ck(len(connections)==1 and connections[0].closed)
ck(connections[0].sent[0][1]=='/account/api/v1/account')
print(json.dumps({'status':'PASS','checks':checks,'resources':len(resources),'webhook_vectors':len(fixture['vectors']),'external_requests':0}))
