"""Only synthetic HTTP responses. No physical transport or customer data."""
import copy,json,uuid
import httpx
from boundary import require
class SyntheticStream(httpx.AsyncByteStream):
 def __init__(self,raw):self.raw=raw
 async def __aiter__(self):
  for offset in range(0,len(self.raw),17):yield self.raw[offset:offset+17]

def _response(status,value,headers=None):
 raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
 return httpx.Response(status,headers=[('content-type','application/json'),('content-length',str(len(raw)))]+(headers or []),stream=SyntheticStream(raw))

class SyntheticDify:
 def __init__(self,boundary,mode='success'):self.boundary=boundary;self.mode=mode;self.draft=None;self.published=None;self.app=None;self.keys=[];self.count=0
 async def __call__(self,request):
  self.count+=1;method=request.method;path=request.url.path;value={};status=200;headers=None
  if path=='/console/api/login':value={'result':'success'};status=503 if self.mode=='fail_login' else 200;headers=[('set-cookie','access_token=PUBLICCONSOLEFIXTURE1234567890; Path=/'),('set-cookie','csrf_token=PUBLICCSRFFIXTURE1234567890; Path=/')]
  elif path=='/console/api/apps':value={'data':[]}
  elif path=='/console/api/workspaces/current/summary':value={'id':self.boundary.workspace if self.mode!='wrong_workspace' else 'wrong-workspace'}
  elif path=='/console/api/apps/imports':
   from app.dsl_roundtrip import parse
   if self.mode=='import_401':return _response(401,{'error':'PUBLIC_UNAUTHORIZED'})
   body=json.loads(request.content);self.app=str(uuid.uuid4());self.draft=parse(body['yaml_content'],'workflow')['workflow']|{'hash':'public-native-draft'};value={'status':'completed','app_id':self.app}
  elif path==f'/console/api/apps/{self.app}':value={'id':self.app,'mode':'workflow'}
  elif path.endswith('/workflows/draft'):value=copy.deepcopy(self.draft)
  elif path.endswith('/workflows/publish'):
   if method=='POST':
    if self.mode=='fail_publish':status=502;value={'error':'PUBLIC_FIXTURE_ERROR'}
    else:self.published=copy.deepcopy(self.draft)|{'id':str(uuid.uuid4())};value={'result':'success'}
   else:value=copy.deepcopy(self.published) if self.published else {};status=200 if self.published else 404
  elif path.endswith('/api-keys'):
   if method=='POST' and self.mode=='fail_key':return _response(502,{'error':'PUBLIC_KEY_FAILURE'})
   if method=='POST':self.keys=[{'id':str(uuid.uuid4()),'token':'app-PUBLICFIXTURE-'+str(uuid.uuid4())}];value=self.keys[0]
   else:value={'data':self.keys}
  elif path=='/v1/workflows/run':
   from local_pipeline import ROWS
   rid=str(uuid.uuid4());rows=copy.deepcopy(ROWS);outputs={'results':rows,'successes':[r for r in rows if r['ok']],'failures':[r for r in rows if not r['ok']],'total':4,'succeeded':3,'failed':1}
   if self.mode=='bad_output':outputs['results'][1]['index']=99
   value={'workflow_run_id':rid,'data':{'id':rid,'workflow_id':self.published['id'],'status':'failed' if self.mode=='fail_run' else 'succeeded','outputs':outputs,'elapsed_time':.2,'total_tokens':0}}
  else:raise RuntimeError('Unsupported synthetic path')
  return _response(status,value,headers)
