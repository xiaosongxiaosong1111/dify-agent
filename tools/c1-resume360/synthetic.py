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
 def model(self):
  from app.intake import topics
  t=self.h.get_task(self.b.owner);phase=self.b.record['phase'];req=copy.deepcopy(self.f['requirements'])
  if phase in ('changed_interview','changed_plan'):req['output']=req['output'].replace(self.f['before_literal'],self.f['changed_fallback'])
  if phase in ('first_plan','changed_plan'):
   v=copy.deepcopy(self.f['plan'])
   if phase=='changed_plan':
    for n in v['nodes']:
     if n['type']=='template-transform':n['config']['template']=self.f['changed_fallback']
   return v
  users=[(i,m) for i,m in enumerate(t['messages']) if m.get('role')=='user' and m.get('purpose')!='discussion'];index,user=users[-1]
  if phase=='vague_interview':
   checks=[{'topic':r['id'],'status':'needs_input','detail':'公开合成需求尚待明确。','evidence':[]} for r in topics(t)]
   questions=[{'topic':key,'question':'请明确'+key+'。','recommendation':'按公开说明确认，不默认采纳。','reason':'防止提前构建。','experience':'回答后继续。','cost':'仅合成替身，不证明费用。','manual_work':'需要明确回答。'} for key in ('goal','input','output')]
   return {'message':'请先明确目标、输入和输出，未搭建。','requirements_patch':{},'intake_review':{'schema_version':1,'checks':checks,'questions':questions}}
  checks=[{'topic':r['id'],'status':'complete','detail':'固定合成明确说明，仍需另行确认。','evidence':[{'kind':'message','id':str(index),'quote':req.get(r['id'],req['rules'])}]} for r in topics({**t,'requirements':req})]
  return {'message':'已整理公开需求草案，仍须确认，不是业务通过。','requirements_patch':req,'intake_review':{'schema_version':1,'checks':checks,'questions':[]}}
 async def __call__(self,request):
  method,path=request.method,request.url.path;phase=self.b.record.get('phase')
  if str(request.url)==self.b.provider['base_url'].rstrip('/')+'/chat/completions':
   if self.mode=='fail_model' and phase=='complete_interview':return response({'error':'SYNTHETIC_FAILURE'},502)
   value=json.dumps(self.model(),ensure_ascii=False)
   if self.mode=='invalid_plan' and phase=='first_plan':value='{}'
   return response({'choices':[{'message':{'role':'assistant','content':value},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':100}})
  if path=='/console/api/login':return response({'result':'success'},503 if self.mode=='fail_login' else 200,[('set-cookie','access_token=PUBLICCONSOLETOKEN123456789; Path=/'),('set-cookie','csrf_token=PUBLICCSRFTOKEN123456789; Path=/')])
  if path=='/console/api/apps':return response({'data':[]})
  if path=='/console/api/workspaces/current/summary':return response({'id':self.b.env['console_workspace_id'] if self.mode!='wrong_workspace' else 'wrong-workspace'})
  if path=='/console/api/apps/imports':
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
   if method=='POST':row['keys']=[{'id':str(uuid.uuid4()),'token':'app-PUBLICFIXTURE-'+str(uuid.uuid4())}];return response(row['keys'][0])
   return response({'data':row['keys']})
  if path=='/console/api/apps/'+str(app):return response({'id':app,'mode':'workflow'})
  if path=='/v1/workflows/run':
   row=self.apps[app];t=self.h.get_task(self.b.owner);inputs=json.loads(request.content)['inputs'];case=next(c for c in t['test_cases'] if c['input']==inputs);hit=case['expectation']['mode']=='contains';v=case['expectation']['expected'];v=' '.join(v) if isinstance(v,list) else v;rid=str(uuid.uuid4());nodes=[]
   for n in row['published']['graph']['nodes']:
    kind=n['data']['type'];executed=kind in ('start','knowledge-retrieval','if-else') or hit and (kind=='llm' or n['id']=='hit_end') or not hit and (kind=='template-transform' or n['id']=='no_hit_end')
    if executed:nodes.append({'id':str(uuid.uuid4()),'node_id':n['id'],'node_type':kind,'title':n['data'].get('title',''),'status':'succeeded','error':None})
   self.runs[rid]={'detail':{'id':rid,'workflow_id':row['published']['id'],'status':'succeeded','graph':copy.deepcopy(row['published']['graph'])},'trace':{'data':nodes}}
   return response({'workflow_run_id':rid,'data':{'id':rid,'workflow_id':row['published']['id'],'status':'failed' if self.mode=='fail_run' else 'succeeded','outputs':{'result':v},'total_tokens':0}})
  for rid,items in self.runs.items():
   if path.endswith('/'+rid):return response(items['detail'])
   if path.endswith('/'+rid+'/node-executions'):return response(items['trace'])
  raise RuntimeError('Unsupported synthetic request')
