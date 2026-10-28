"""Protect all existing state; only one newly created workflow and its approved new resources."""
import copy,hashlib,json,time,uuid
from urllib.parse import urlsplit,parse_qs

def require(v,m):
 if not v:raise RuntimeError(m)
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def capture(store):
 from pathlib import Path
 with store.connect() as db:
  objects={k+':'+i:digest(json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')};secrets={i:hashlib.sha256(bytes(v)).hexdigest() for i,v in db.execute('SELECT id,value FROM secrets')}
 files={}
 for p in store.root.rglob('*'):
  if not p.is_file() or p.parent==store.root and p.name in ('flowcraft.sqlite3','flowcraft.sqlite3-wal','flowcraft.sqlite3-shm','server.out.log','server.err.log'):continue
  require(p.resolve().is_relative_to(store.root.resolve()),'Data link outside scope');files[str(p.relative_to(store.root))]=hashlib.sha256(p.read_bytes()).hexdigest()
 return {'objects':objects,'secrets':secrets,'files':files}

def known_apps(store):
 apps=set()
 def add(value):
  try:
   if isinstance(value,str) and str(uuid.UUID(value))==value:apps.add(value)
  except ValueError:pass
 for kind in ('environment','task','app_runtime_credential','workflow_publication','app_runtime_key_creation','runtime_key_previous_binding'):
  for value in store.list(kind):
   add(value.get('app_id'));add(value.get('dify_app_id'));add(value.get('service_app_id'))
   if kind=='task':
    for r in value.get('runs',[]):add(r.get('app_id'));add((r.get('result') or {}).get('app_id') if isinstance(r.get('result'),dict) else None)
 return apps

def resource_graph(native,fixture,version):
 from app.workflow_publication import core
 graph=core(native['workflow']);nodes=graph['nodes'];types=[n['data']['type'] for n in nodes]
 require(not native.get('dependencies') and not native['workflow'].get('environment_variables') and not native['workflow'].get('conversation_variables'),'No new dependencies/secret variables')
 require(set(types)<={'start','knowledge-retrieval','if-else','llm','template-transform','end','variable-aggregator'} and all(types.count(k)==1 for k in ('start','knowledge-retrieval','if-else','llm','template-transform')) and 1<=types.count('end')<=2 and types.count('variable-aggregator')<=1,'Unsupported resources or extra nodes')
 by={n['data']['type']:n for n in nodes};start=by['start'];variables=start['data'].get('variables');require(isinstance(variables,list) and len(variables)==1 and variables[0].get('variable')=='query' and variables[0].get('required') is True and variables[0].get('type') in ('text-input','paragraph'),'Fixed query input required')
 kb=by['knowledge-retrieval'];data=kb['data'];cfg=data.get('multiple_retrieval_config',{});require(data.get('dataset_ids')==fixture['configuration']['dataset_ids'] and data.get('query_variable_selector')==[start['id'],'query'] and data.get('retrieval_mode')=='multiple' and cfg.get('top_k')==3 and cfg.get('reranking_enable') is False and cfg.get('score_threshold') is None and cfg.get('score_threshold_enabled') in (None,False),'Retrieval resources differ')
 llm=by['llm']['data'];model=llm.get('model',{});c=fixture['configuration'];require(model.get('provider')==c['dify_model_provider'] and model.get('name')==c['dify_model'] and model.get('mode')=='chat' and model.get('completion_params')=={'temperature':.2,'max_tokens':512,'thinking':False} and llm.get('context')=={'enabled':True,'variable_selector':[kb['id'],'result']},'Answer model/context differs')
 require(by['template-transform']['data'].get('template')==fixture['before_literal' if version=='original' else 'changed_fallback'],'No-hit literal differs')
 for n in nodes:
  if n['data']['type']=='end':require(len(n['data'].get('outputs',[]))==1 and n['data']['outputs'][0].get('variable')=='result','Exactly result output required')
 return graph

class Boundary:
 def __init__(self,env,provider,fixture,record,old_apps):
  self.env=env;self.provider=provider;self.fixture=fixture;self.record=record;self.old_apps=set(old_apps);self.started=time.monotonic();self.halted=False;self.owner=None;self.owner_configured=False;self.store=None;self.apps={};self.runs={};self.current=None;self.model_pending=None;self.workspace_verified=False;self.login_tokens=None;self.counts={k:0 for k in ('model','reads','login','import','publish','key','run')};record['dispatch_counts']=self.counts;record['dispatches']=[];self.persist=lambda:None;self.stop_requested=lambda:False
 def admit(self,request):
  require(not self.halted and not self.stop_requested() and time.monotonic()-self.started<1800,'Batch halted or expired')
  url=str(request.url);parts=urlsplit(url);body=json.loads(request.content) if request.content else None;method=request.method;path=parts.path;kind=None;phase=self.record.get('phase')
  if url==self.provider['base_url'].rstrip('/')+'/chat/completions':
   require(method=='POST' and self.model_pending is not None and body.get('model')==self.provider['model'] and body.get('max_tokens')==6000 and body.get('stream') is False and digest(body.get('messages'))==self.model_pending['messages_sha256'] and len(request.content)<=300000 and set(body)<={'model','messages','max_tokens','stream','thinking','response_format'} and body.get('thinking')=={'type':'disabled'},'Unexpected model request')
   require(self.counts['model']<len(self.record.get('model_requests',[]))<=2,'Model invocation/dispatch count');self.model_pending=None;kind='model'
  else:
   target=urlsplit(self.env['base_url']);require((parts.scheme,parts.netloc)==(target.scheme,target.netloc),'Unexpected outbound origin')
   if method=='POST' and path=='/console/api/login':require(phase=='reconnect' and isinstance(body,dict) and set(body)=={'email','password','remember_me'} and body['remember_me'] is False,'Unexpected login');kind='login'
   elif method=='GET':
    allowed=path in ('/console/api/apps','/console/api/workspaces/current/summary') or any(path==f'/console/api/apps/{app}'+tail for app in self.apps for tail in ('','/workflows/draft','/workflows/publish','/api-keys')) or any(path in (f'/console/api/apps/{app}/workflow-runs/{rid}',f'/console/api/apps/{app}/workflow-runs/{rid}/node-executions') for rid,app in self.runs.items())
    require(allowed,'Unexpected management read');query=parse_qs(parts.query,keep_blank_values=True);require(query=={'page':['1'],'limit':['1']} if path=='/console/api/apps' else not query,'Unexpected management query');kind='reads'
   elif method=='POST' and path=='/console/api/apps/imports':
    require(self.workspace_verified and phase in ('original_import','modified_import') and isinstance(body,dict) and set(body)=={'mode','yaml_content','name'} and body['mode']=='yaml-content' and body['name']==self.fixture['task_name'],'Unexpected import')
    from app.dsl_roundtrip import parse
    from app.workflow_publication import core
    graph=resource_graph(parse(body['yaml_content'],'workflow'),self.fixture,'original' if phase=='original_import' else 'modified');require(digest(graph)==self.record.get('approved_graph_digest'),'Imported graph lacks current content review');kind='import'
   elif method=='POST' and any(path==f'/console/api/apps/{app}/workflows/publish' for app in self.apps):
    app=path.split('/')[4];require(app==self.current and phase.endswith('_publish') and self.apps[app]['unpublished'] and not self.apps[app]['published'] and isinstance(body,dict) and set(body)=={'marked_name','marked_comment'},'Unexpected publication');kind='publish'
   elif method=='POST' and any(path==f'/console/api/apps/{app}/api-keys' for app in self.apps):
    app=path.split('/')[4];require(app==self.current and phase.endswith('_key') and self.apps[app]['published'] and self.apps[app]['key'] is None and body=={},'Unexpected key creation');kind='key'
   elif method=='POST' and path=='/v1/workflows/run':
    app=self.current;case_index=0 if phase.endswith('_hit') else 1 if phase.endswith('_miss') else None
    require(app in self.apps and case_index is not None and self.apps[app]['key'] is not None and request.headers.get('authorization')=='Bearer '+self.apps[app]['key'] and isinstance(body,dict) and set(body)=={'inputs','response_mode','user'} and body['inputs']==self.fixture['cases'][case_index]['input'] and body['response_mode']=='blocking' and body['user']=='flowcraft-local','Unexpected run/input/key');kind='run'
  require(kind is not None,'Unapproved method/path');caps={'model':2,'reads':45,'login':0,'import':2,'publish':2,'key':2,'run':4};require(self.counts[kind]<caps[kind],'Dispatch limit reached')
  if kind in ('publish','key','run'):
   app=self.current;per=self.apps[app]['counts']
   if kind=='run':
    seen=self.apps[app]['cases_seen'];require(case_index==len(seen),'Duplicate or out-of-order case');seen.append(case_index)
   require(per[kind]<(2 if kind=='run' else 1),'Per-App duplicate dispatch');per[kind]+=1
  self.counts[kind]+=1;entry={'method':method,'path':path,'kind':kind,'status':None,'phase':phase};self.record['dispatches'].append(entry);return entry
 def observed(self,entry,response):
  kind,path=entry['kind'],entry['path'];expected404=entry['method']=='GET' and any(path==f'/console/api/apps/{a}/workflows/publish' and not v['published'] and not v['counts']['publish'] for a,v in self.apps.items()) and response.status_code==404
  if expected404:self.apps[path.split('/')[4]]['unpublished']=True;return response
  if response.status_code not in (200,201):
   self.halted=True;self.record['failed_http']={'phase':entry.get('phase'),'kind':kind,'http_status':response.status_code};return response
  value=response.json()
  if kind=='model':
   from app.providers import usage_summary
   choice=value.get('choices',[None])[0] if isinstance(value,dict) and isinstance(value.get('choices'),list) and value['choices'] else None
   self.record.setdefault('model_response_metadata',[]).append({'phase':entry['phase'],'usage':usage_summary(value.get('usage')) if isinstance(value,dict) else {},'finish_reason':choice.get('finish_reason') if isinstance(choice,dict) else None})
   require(isinstance(choice,dict) and choice.get('finish_reason')=='stop' and isinstance(choice.get('message'),dict) and choice['message'].get('role')=='assistant' and isinstance(choice['message'].get('content'),str) and not choice['message'].get('tool_calls'),'Model did not return a complete final text')
  elif kind=='login':
   cookies={c.name:c.value for c in response.cookies.jar};prefix='__Host-' if '__Host-access_token' in cookies else '';self.login_tokens={'console_token':cookies.get(prefix+'access_token'),'csrf_token':cookies.get(prefix+'csrf_token')}
  elif path=='/console/api/workspaces/current/summary':require(value.get('id')==self.env['console_workspace_id'],'Workspace mismatch');self.workspace_verified=True
  elif kind=='import':
   app=value.get('app_id');require(isinstance(app,str) and str(uuid.UUID(app))==app and app not in self.old_apps and app not in self.apps,'Imported App not new');self.current=app;self.apps[app]={'graph_digest':self.record['approved_graph_digest'],'published':None,'key':None,'unpublished':False,'cases_seen':[],'counts':{'publish':0,'key':0,'run':0}};self.record['app_ids']=list(self.apps)
  elif kind=='reads' and path.endswith('/workflows/publish'):
   app=path.split('/')[4];v=self.apps[app]
   if value is None:require(not v['published'] and not v['counts']['publish'],'Published workflow disappeared');v['unpublished']=True
   else:
    from app.workflow_publication import core
    require(digest(core(value))==v['graph_digest'] and isinstance(value.get('id'),str) and str(uuid.UUID(value['id']))==value['id'],'Published graph mismatch');v.update(published=value['id'],unpublished=False)
  elif kind=='publish':require(value.get('result')=='success','Bad publication result')
  elif kind=='key':require(isinstance(value.get('token'),str) and value['token'].startswith('app-') and value.get('id'),'Bad key result');self.apps[self.current]['key']=value['token']
  elif kind=='run':
   data=value.get('data',{});rid=data.get('id');require(rid==value.get('workflow_run_id') and isinstance(rid,str) and str(uuid.UUID(rid))==rid and data.get('workflow_id')==self.apps[self.current]['published'],'Run identity mismatch');self.runs[rid]=self.current
  return response

def guarded_store(base,old,environment,provider,boundary,fixture,initial_task,initial_budget):
 from reuse_policy import preserve_task,preserve_budget
 class Guarded(base):
  new_ids=set();interviews=set();message_requests=set();key_proposals=set();publications=set();previous_keys={};service_writes=0
  def object_check(self,kind,item,value):
   ident=kind+':'+item
   if kind=='environment':
    require(item==environment['id'],'Other environment write');mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','connection_revision','service_app_id','capabilities'}
    require(canonical({k:v for k,v in value.items() if k not in mutable})==canonical({k:v for k,v in environment.items() if k not in mutable}),'Connection source changed');require(value.get('service_app_id') in {environment.get('service_app_id'),*boundary.apps},'Unexpected App binding');require({k:v for k,v in value.get('capabilities',{}).items() if k not in ('console','runtime')}=={k:v for k,v in environment.get('capabilities',{}).items() if k not in ('console','runtime')},'Other capability changed')
   else:
    require(ident not in old['objects'] or kind in ('task','task_budget') and item==boundary.owner,'Existing object write forbidden')
    if kind=='task':
     require(ident in old['objects'] and item==boundary.owner,'New Task creation forbidden');preserve_task(initial_task,value)
     require(item==boundary.owner and value.get('app_type')=='workflow' and (value.get('environment_id')==environment['id'] or value.get('environment_id') is None and not boundary.owner_configured and boundary.record.get('phase')=='reconnect') and value.get('intake_required') is True and value.get('plan_review_required') is True,'Task identity or admission bypass')
     if value.get('environment_id')==environment['id']:boundary.owner_configured=True
     require(all(sum(r.get('kind')==k for r in value.get('runs',[]))<=n for k,n in [('import',2),('publish',2),('run',4)]),'Task resource record count')
    elif kind in ('task_budget','execution_limits','plan_draft'):require(item==boundary.owner,'Other Task controls');preserve_budget(initial_budget,value) if kind=='task_budget' else None
    elif kind in ('interview_operation','message_request'):
     require(value.get('task_id')==boundary.owner,'Other Task interview/request metadata');items=self.interviews if kind=='interview_operation' else self.message_requests;items.add(item);require(len(items)<=3,'Too many interview/request records')
    elif kind in ('saved_console_reconnect','console_saved_reconnect','console_connection_failure'):require(value.get('environment_id')==environment['id'],'Other authentication record')
    elif kind in ('workflow_publication','app_runtime_key_creation'):
     require(value.get('task_id')==boundary.owner and value.get('environment_id')==environment['id'] and value.get('app_id') in boundary.apps,'Unbound resource receipt');collection=self.publications if kind=='workflow_publication' else self.key_proposals;collection.add(item);require(len(collection)<=2,'Too many resource proposals')
    elif kind=='app_runtime_credential':require(value.get('environment_id')==environment['id'] and value.get('app_id') in boundary.apps,'Unexpected runtime archive')
    elif kind=='runtime_key_previous_binding':require(value.get('environment_id')==environment['id'] and value.get('source') in self.key_proposals and value.get('app_id') in {environment.get('service_app_id'),*boundary.apps},'Wrong previous binding')
    else:require(False,'Unexpected new object kind')
  def _put_object(self,conn,states,kind,item,value):
   self.object_check(kind,item,value);return super()._put_object(conn,states,kind,item,value)
  def secret(self,item,key):
   allowed=item==provider['id'] and key=='api_key' or item==environment['id'] and key in ('console_token','csrf_token','service_api_key','dataset_api_key') or any(item==environment['id']+':app-runtime:'+app and key=='service_api_key' for app in boundary.apps) or item.endswith(':previous-runtime-key') and item.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key'
   require(allowed,'Unrelated credential decryption forbidden');return super().secret(item,key)
  def secret_check(self,sets):
   for owner,values in sets.items():
    for key,value in values.items():
     require(isinstance(value,str) and bool(value),'Invalid secret write')
     if owner==environment['id']:
      require(key in ('console_token','csrf_token','service_api_key'),'Saved login mutation forbidden')
      if key in ('console_token','csrf_token'):require(boundary.workspace_verified and boundary.login_tokens and value==boundary.login_tokens[key],'Authentication must prove original workspace before commit')
      if key=='service_api_key':require(boundary.current in boundary.apps and value==boundary.apps[boundary.current]['key'] and self.service_writes<2,'Wrong new runtime key');self.service_writes+=1
     elif any(owner==environment['id']+':app-runtime:'+app for app in boundary.apps):require(key=='service_api_key' and value==boundary.apps[owner.rsplit(':',1)[1]]['key'] and owner+':'+key not in old['secrets'],'Wrong new App key archive')
     else:
      require(owner.endswith(':previous-runtime-key') and owner.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key' and value==self.secret(environment['id'],'service_api_key'),'Wrong old key archive');self.previous_keys[owner]=hashlib.sha256(value.encode()).hexdigest()
  def set_secret(self,item,key,value):self.secret_check({item:{key:value}});return super().set_secret(item,key,value)
  def put_with_secrets(self,kind,item,value,secrets):self.secret_check({item:secrets});return super().put_with_secrets(kind,item,value,secrets)
  def put_many_with_secrets(self,rows,item,secrets):self.secret_check({item:secrets});return super().put_many_with_secrets(rows,item,secrets)
  def put_many_with_secret_sets(self,rows,sets):self.secret_check(sets);return super().put_many_with_secret_sets(rows,sets)
  def delete(self,*a):raise RuntimeError('Deletion forbidden')
 return Guarded

def verify(store,old,environment,boundary):
 now=capture(store);eid=environment['id']
 store.object_check('task',boundary.owner,store.get('task',boundary.owner));store.object_check('task_budget',boundary.owner,store.get('task_budget',boundary.owner))
 require(all(now['objects'].get(k)==v for k,v in old['objects'].items() if k not in {'environment:'+eid,'task:'+boundary.owner,'task_budget:'+boundary.owner}),'Original object changed')
 allowed={eid+':'+k for k in ('service_api_key',)};require(all(now['secrets'].get(k)==v for k,v in old['secrets'].items() if k not in allowed),'Original ciphertext changed')
 require(all(now['files'].get(k)==v for k,v in old['files'].items()),'Original asset/masterkey changed')
 require(len(store.list('task'))==sum(k.startswith('task:') for k in old['objects']),'Task count changed')
 with store.connect() as db:
  for kind,item,raw in db.execute('SELECT kind,id,value FROM objects'):
   if kind+':'+item not in old['objects']:store.object_check(kind,item,json.loads(raw))
 for key in set(now['secrets'])-set(old['secrets']):
  owner,name=key.rsplit(':',1);allowed=owner==eid and name in ('console_token','csrf_token','service_api_key') or owner in {eid+':app-runtime:'+app for app in boundary.apps} and name=='service_api_key' or owner in store.previous_keys and name=='service_api_key';require(allowed,'Unowned new ciphertext')
 from pathlib import Path
 for name in set(now['files'])-set(old['files']):require(boundary.owner is not None and Path(name).parts[0]==boundary.owner,'Unowned new asset')
 for owner,value in store.previous_keys.items():require(hashlib.sha256(store.secret(owner,'service_api_key').encode()).hexdigest()==value,'Old key archive mismatch')
 if boundary.login_tokens and boundary.workspace_verified:
  require(all(store.secret(eid,k)==v for k,v in boundary.login_tokens.items()),'Authentication commit mismatch')
 return {'other_original_tasks_objects_and_ledgers_kept':True,'old_ciphertexts_kept_except_approved_auth_runtime':True,'original_assets_masterkey_kept':True,'old_runtime_keys_archived':True,'new_tasks':0,'existing_failed_history_and_ledger_kept':True}
