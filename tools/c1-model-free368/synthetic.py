"""Native-shaped unread SDK responses; public synthetic inputs only."""
import copy,json,uuid
import httpx
class Stream(httpx.AsyncByteStream):
 def __init__(self,raw):self.raw=raw
 async def __aiter__(self):
  for i in range(0,len(self.raw),23):yield self.raw[i:i+23]
def response(value,status=200,headers=None):return httpx.Response(status,headers=[('content-type','application/json')]+(headers or []),stream=Stream(json.dumps(value,ensure_ascii=False).encode()))
class Synthetic:
 def __init__(self,h,b,fixture,mode='success'):self.h=h;self.b=b;self.f=fixture;self.mode=mode;self.apps={};self.runs={}
 async def __call__(self,request):
  method,path=request.method,request.url.path;phase=self.b.record.get('phase')
  if path=='/console/api/login':return response({'result':'success'},503 if self.mode=='fail_login' else 200,[('set-cookie','access_token=PUBLICCONSOLETOKEN123456789; Path=/'),('set-cookie','csrf_token=PUBLICCSRFTOKEN123456789; Path=/')])
  if path=='/console/api/apps':return response({'data':[]})
  if path=='/console/api/workspaces/current/summary':return response({'id':self.b.env['console_workspace_id'] if self.mode!='wrong_workspace' else 'wrong-workspace'},401 if self.mode=='expired_session' else 200)
  if path=='/console/api/apps/imports':
   if self.mode=='fail_import':return response({'error':'SYNTHETIC_IMPORT_FAILURE'},503)
   if self.mode=='old_app_import':return response({'status':'completed','app_id':self.b.env['service_app_id']})
   from app.dsl_roundtrip import parse
   body=json.loads(request.content);app=str(uuid.uuid4());self.apps[app]={'draft':parse(body['yaml_content'],'workflow')['workflow']|{'hash':'public-native-'+app},'published':None,'keys':[]};return response({'status':'completed','app_id':app})
  app=path.split('/')[4] if path.startswith('/console/api/apps/') else self.b.current
  if path.endswith('/workflows/draft'):return response(copy.deepcopy(self.apps[app]['draft']))
  if path.endswith('/workflows/publish'):
   row=self.apps[app]
   if method=='POST':
    if self.mode=='fail_publish':return response({'error':'SYNTHETIC_PUBLICATION_FAILURE'},502)
    row['published']=copy.deepcopy(row['draft'])|{'id':str(uuid.uuid4())};return response({'result':'success','created_at':1700000000})
   return response(copy.deepcopy(row['published']))
  if path.endswith('/api-keys'):
   row=self.apps[app]
   if method=='POST' and self.mode=='fail_key':return response({'error':'SYNTHETIC_KEY_FAILURE'},503)
   if method=='POST':row['keys']=[{'id':str(uuid.uuid4()),'token':'app-PUBLICFIXTURE-'+str(uuid.uuid4())}];return response(row['keys'][0])
   return response({'data':row['keys']})
  if path=='/console/api/apps/'+str(app):return response({'id':app,'mode':'workflow'})
  if path=='/v1/workflows/run':
   row=self.apps[app];t=self.h.get_task(self.b.owner);inputs=json.loads(request.content)['inputs'];case=next(c for c in t['test_cases'] if c['input']==inputs);hit=case['expectation']['mode']=='contains';v=case['expectation']['expected'];v=' '.join(v) if isinstance(v,list) else v;rid=str(uuid.uuid4());nodes=[]
   for n in row['published']['graph']['nodes']:
    kind=n['data']['type'];selector=(n['data'].get('outputs') or [{}])[0].get('value_selector',[])
    source_type=next((x['data']['type'] for x in row['published']['graph']['nodes'] if selector and x['id']==selector[0]),None)
    executed=kind in ('start','knowledge-retrieval','if-else') or hit and (kind=='llm' or kind=='end' and source_type=='llm') or not hit and (kind=='template-transform' or kind=='end' and source_type=='template-transform')
    if executed:nodes.append({'id':str(uuid.uuid4()),'node_id':n['id'],'node_type':kind,'title':n['data'].get('title',''),'status':'succeeded','error':None})
   self.runs[rid]={'detail':{'id':rid,'workflow_id':row['published']['id'],'status':'succeeded','graph':copy.deepcopy(row['published']['graph'])},'trace':{'data':nodes}}
   return response({'workflow_run_id':rid,'data':{'id':rid,'workflow_id':row['published']['id'],'status':'failed' if self.mode=='fail_run' else 'succeeded','outputs':{'result':v},'total_tokens':0}})
  for rid,items in self.runs.items():
   if path.endswith('/'+rid):
    detail=copy.deepcopy(items['detail'])
    if self.mode=='wrong_trace':detail['graph']['nodes'][0]['data']['title']='SYNTHETIC_DIFFERENT_GRAPH'
    return response(detail)
   if path.endswith('/'+rid+'/node-executions'):return response(items['trace'])
  raise RuntimeError('Unsupported synthetic request')
