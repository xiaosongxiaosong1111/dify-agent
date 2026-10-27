"""Dispatch guard: one new App/publish/Key/run; never expose credentials in receipts."""
import hashlib,json,time,uuid
from urllib.parse import urlsplit,parse_qs

def require(condition,message):
 if not condition:raise RuntimeError(message)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

class Boundary:
 def __init__(self,base,workspace,graph_digest,fixture,record,old_apps=(),clock=time.monotonic):
  self.base=base.rstrip('/');self.workspace=workspace;self.graph_digest=graph_digest;self.fixture=fixture;self.record=record;self.old_apps=set(old_apps);self.clock=clock;self.started=clock();self.halted=False;self.workspace_verified=False;self.unpublished=False;self.app=None;self.published=None;self.key=None;self.executed=None;self.login_tokens=None
  self.counts={k:0 for k in ('reads','login','import','publish','key','run')};record['dispatch_counts']=self.counts;record['dispatches']=[];self.persist=lambda:None
 def admit(self,request):
  if self.halted:
   self.record['blocked_after_stop']=self.record.get('blocked_after_stop',0)+1;raise RuntimeError('Batch already stopped; no subsequent dispatch')
  require(self.clock()-self.started<600,'Batch wall boundary exceeded')
  parts=urlsplit(str(request.url));origin=urlsplit(self.base);require((parts.scheme,parts.netloc)==(origin.scheme,origin.netloc),'Unexpected outbound origin')
  method=request.method;path=parts.path;query=parse_qs(parts.query,keep_blank_values=True);body=json.loads(request.content) if request.content else None;kind=None
  if method=='POST' and path=='/console/api/login':
   require(isinstance(body,dict) and set(body)=={'email','password','remember_me'} and isinstance(body['email'],str) and isinstance(body['password'],str) and body['remember_me'] is False,'Unexpected login shape');kind='login'
  elif method=='GET':
   allowed=path in ('/console/api/apps','/console/api/workspaces/current/summary') or bool(self.app and path in [f'/console/api/apps/{self.app}'+suffix for suffix in ('','/workflows/draft','/workflows/publish','/api-keys')])
   require(allowed,'Unexpected Console read')
   require(query=={'page':['1'],'limit':['1']} if path=='/console/api/apps' else not query,'Unexpected Console query');kind='reads'
  elif method=='POST' and path=='/console/api/apps/imports':
   from app.dsl_roundtrip import parse
   from app.workflow_publication import core
   require(isinstance(body,dict) and set(body)=={'mode','yaml_content','name'} and body['mode']=='yaml-content' and body['name']==self.fixture['task_name'],'Unexpected import body')
   native=parse(body['yaml_content'],'workflow');require(native['app']['name']==self.fixture['task_name'] and not native.get('dependencies') and digest(core(native['workflow']))==self.graph_digest,'Imported graph differs from frozen public graph');kind='import'
  elif method=='POST' and self.app and path==f'/console/api/apps/{self.app}/workflows/publish':
   require(isinstance(body,dict) and set(body)=={'marked_name','marked_comment'} and all(isinstance(v,str) for v in body.values()) and self.unpublished,'Unexpected publish body');kind='publish'
  elif method=='POST' and self.app and path==f'/console/api/apps/{self.app}/api-keys':require(body=={} and self.published is not None,'Key needs this newly published App');kind='key'
  elif method=='POST' and path=='/v1/workflows/run':
   require(self.key is not None and self.published is not None and isinstance(body,dict) and set(body)=={'inputs','response_mode','user'} and canonical(body['inputs'])==canonical(self.fixture['input']) and body['response_mode']=='blocking' and body['user']=='flowcraft-local','Unexpected Service input/scope')
   require(request.headers.get('authorization')=='Bearer '+self.key,'Service credential not created for this new App');kind='run'
  require(kind is not None,'Unapproved outbound method/path')
  caps={'reads':16,'login':1,'import':1,'publish':1,'key':1,'run':1};require(self.counts[kind]<caps[kind],'Dispatch count boundary exceeded')
  if kind=='import':require(self.app is None and self.workspace_verified and self.counts['login']==1,'Import requires explicit saved reconnect')
  self.counts[kind]+=1;entry={'method':method,'path':path,'kind':kind,'status':None};self.record['dispatches'].append(entry)
  return entry
 def observed(self,entry,response):
  entry['status']=response.status_code;kind=entry['kind']
  expected404=entry['method']=='GET' and self.app and entry['path']==f'/console/api/apps/{self.app}/workflows/publish' and self.counts['publish']==0 and response.status_code==404
  if expected404:self.unpublished=True
  if response.status_code not in (200,201) and not expected404:
   from app.dify import DifyError
   self.halted=True;raise DifyError('本批返回非成功状态，已停止且不自动登录或重试。',http_status=response.status_code,code='login_service_error' if kind=='login' and response.status_code>=500 else None)
  if response.is_success:
   value=response.json()
   if kind=='login':
    cookies={c.name:c.value for c in response.cookies.jar};prefix='__Host-' if '__Host-access_token' in cookies else '';self.login_tokens={'console_token':cookies.get(prefix+'access_token'),'csrf_token':cookies.get(prefix+'csrf_token')}
   elif kind=='import':
    ident=value.get('app_id');require(isinstance(ident,str) and str(uuid.UUID(ident))==ident and ident not in self.old_apps and self.app is None,'New App identity not proven');self.app=ident;self.record['new_app_id']=ident
   elif kind=='publish':require(value.get('result')=='success','Publication response not accepted')
   elif kind=='key':
    require(isinstance(value.get('token'),str) and value['token'].startswith('app-') and isinstance(value.get('id'),str),'Created Key response missing');self.key=value['token'];self.record['new_key_id']=value['id']
   elif kind=='reads' and entry['path']=='/console/api/workspaces/current/summary':
    if value.get('id')!=self.workspace:
     from app.dify import DifyError
     raise DifyError('本批工作空间不匹配，已停止。',code='workspace_mismatch')
    self.workspace_verified=True
   elif kind=='reads' and self.app and entry['path']==f'/console/api/apps/{self.app}/workflows/publish' and value is not None:
    from app.workflow_publication import core
    require(digest(core(value))==self.graph_digest and isinstance(value.get('id'),str) and str(uuid.UUID(value['id']))==value['id'],'Published graph differs from frozen source');self.published=value['id'];self.record['published_workflow_id']=self.published
   elif kind=='run':
    data=value.get('data',{});require(data.get('workflow_id')==self.published and value.get('workflow_run_id')==data.get('id') and isinstance(data.get('id'),str) and str(uuid.UUID(data['id']))==data['id'],'Execution is not bound to this published Workflow');self.executed=data.get('id');self.record['workflow_run_id']=self.executed
  return response
