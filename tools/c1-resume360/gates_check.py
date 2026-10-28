"""Targeted admission/review/resource negatives in disposable fixtures. No production Store or HTTP."""
import copy,json,sys,tempfile,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
import execute
from support import sha
from guard import Boundary,require,digest,resource_graph
from reviews import Reviews
from submit_review import submit
from fastapi import HTTPException
import httpx
checks=[]
def rejected(name,fn):
 try:fn()
 except (RuntimeError,ValueError,OSError,KeyError,HTTPException):checks.append(name);return
 raise AssertionError('Accepted '+name)
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),'utf-8')
with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='c1-gates-') as folder:
 root=Path(folder)/'work/c1-resume360';root.mkdir(parents=True)
 for name in execute.FROZEN-{'plan.json'}:(root/name).write_bytes((ROOT/name).read_bytes())
 plan={'schema_version':1,'batch_id':'c1-resume360','target_task_id':'aa827c91-b683-4a34-9e7f-fa0789f5c252','explicit_regrant':{'from_batch':'c1-existing357','model':5,'reads':48,'import':2,'publish':2,'key':2,'run':4,'new_model_slots':0,'new_reads':0,'new_login':1},'limits':execute.LIMITS,'wall_seconds':1800,'max_each_model_estimate_usd':'0.055','max_new_model_estimate_usd':'0.275'};write(root/'plan.json',plan)
 def manifest():write(root/'manifest.json',{'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(root/name) for name in execute.FROZEN}})
 manifest();assert execute.validated(root)==plan;checks.append('complete exact frozen scope')
 rejected('missing direct approval',lambda:execute.approved(root,plan))
 approval={'authorization_source':'direct_human_reply','decision':'approve','batch_id':plan['batch_id'],'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'limits':execute.LIMITS,'new_independent_scope':True,'old_reservations_preserved':True,'model_estimate_book_upper_usd':'0.755473652','target_task_id':plan['target_task_id'],'explicit_regrant':plan['explicit_regrant'],'question_ref':'SYNTHETIC_ONLY','reply':'synthetic scope schema only'}
 for key,value in [('authorization_source','agent_delegated'),('decision','deny'),('batch_id','old353'),('plan_sha256','0'*64),('manifest_sha256','0'*64),('limits',execute.LIMITS|{'model':6}),('new_independent_scope',False),('old_reservations_preserved',False),('model_estimate_book_upper_usd','0.5'),('question_ref',' '),('reply',' '),('target_task_id','other'),('explicit_regrant',{})]:
  write(root/'approval.json',approval|{key:value});rejected('approval '+key,lambda:execute.approved(root,plan))
 write(root/'approval.json',approval);assert execute.approved(root,plan)==approval
 for key,value in [('limits',execute.LIMITS|{'model':6}),('limits',execute.LIMITS|{'new_tasks':True}),('limits',execute.LIMITS|{'reads':49}),('wall_seconds',1801),('max_new_model_estimate_usd','0.30'),('target_task_id','other'),('explicit_regrant',{})]:
  write(root/'plan.json',plan|{key:value});manifest();rejected('scope '+key+str(value),lambda:execute.validated(root))
 write(root/'plan.json',plan);manifest();write(root/'approval.json',approval|{'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json')})
 (root/'guard.py').write_bytes(b'tampered');rejected('tampered code',lambda:execute.validated(root));(root/'guard.py').write_bytes((ROOT/'guard.py').read_bytes());manifest();write(root/'approval.json',approval|{'manifest_sha256':sha(root/'manifest.json')})
 record={'batch_id':plan['batch_id'],'state':'admission_started','phase':'preflight','plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'approval_sha256':sha(root/'approval.json')};execute.claim(root,record);rejected('attempt exclusive',lambda:execute.claim(root,record));saved=(root/'attempt.json').read_bytes()
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',Path(folder)),patch.object(execute,'current',lambda *a:None):
  execute.authorize_worker(plan,record|{'model_requests':[]});assert (root/'worker-started.json').exists();checks.append('worker admission survives normal transient record initialization')
  rejected('worker starts once',lambda:execute.authorize_worker(plan,record|{'model_requests':[]}));assert (root/'attempt.json').read_bytes()==saved
 rejected('source cannot execute live',execute.main)
 # A separate minimal current-source record tests the review handshake without claiming semantic review.
 reviewdir=Path(folder)/'review';reviewdir.mkdir();task={'id':'synthetic-task','revision':2,'messages':[],'requirements':{'goal':'public'},'workflow_plan':None};h=SimpleNamespace(get_task=lambda _:copy.deepcopy(task));record={'task_id':task['id']};reviews=Reviews(reviewdir,h,record,False,lambda:None)
 value=reviews.prepare('vague_interview');r=reviews.poll('vague_interview');assert r['ready'] and r['semantic_reviewed'] is False;checks.append('synthetic review never labelled semantic')
 rejected('consumed review',lambda:reviews.poll('vague_interview'));rejected('repeat prepare',lambda:reviews.prepare('vague_interview'))
 for change in ('task','source_file','source_hash','actor','note'):
  out=Path(folder)/('review-'+change);out.mkdir();t=copy.deepcopy(task);host=SimpleNamespace(get_task=lambda _,t=t:copy.deepcopy(t));r=Reviews(out,host,{'task_id':t['id']},False,lambda:None);v=r.prepare('complete_interview');file=out/'review-complete_interview.json';ack=json.loads(file.read_text('utf-8'))
  if change=='task':t['revision']+=1
  elif change=='source_file':source=json.loads((out/'review-source-complete_interview.json').read_text('utf-8'));source['verification']='tampered';write(out/'review-source-complete_interview.json',source)
  elif change=='source_hash':ack['source_sha256']='0'*64
  elif change=='actor':ack['actor']='user'
  else:ack['note']='password=PUBLIC_SYNTHETIC_ONLY'
  write(file,ack);rejected('review '+change,lambda:r.poll('complete_interview'));assert not r.record.get('reviews')
 # The actual submit helper writes an explicit agent decision atomically, without interpreting it as resource authority.
 out=Path(folder)/'submit';out.mkdir();source={'stage':'vague_interview','task':task};write(out/'review-source-vague_interview.json',source)
 rejected('submit wrong source',lambda:submit(out,'vague_interview','0'*64,'公开隔离核对。'));rejected('submit credential note',lambda:submit(out,'vague_interview',digest(source),'password=PUBLIC_SYNTHETIC_ONLY'))
 assert submit(out,'vague_interview',digest(source),'仅测试显式本机登记，不是实际语义或资源批准。')['network_requested'] is False;rejected('submit once',lambda:submit(out,'vague_interview',digest(source),'再次'))
 fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));env={'base_url':'https://public-dify.invalid','console_workspace_id':'workspace'};provider={'base_url':'https://api.deepseek.com','model':'deepseek-flash'}
 def boundary():return Boundary(env,provider,fixture,{'phase':'reconnect'},[])
 for method,url,label in [('GET','https://wrong.invalid/console/api/apps','foreign origin'),('GET','https://public-dify.invalid/console/api/apps/foreign','foreign App'),('DELETE','https://public-dify.invalid/console/api/apps','no deletion')]:
  b=boundary();rejected(label,lambda:b.admit(httpx.Request(method,url)));assert sum(b.counts.values())==0
 b=boundary();b.stop_requested=lambda:True;rejected('explicit root stop marker',lambda:b.admit(httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1')))
 b=boundary();b.halted=True;rejected('halted request',lambda:b.admit(httpx.Request('POST','https://api.deepseek.com/chat/completions',json={})))
 # Independent small native resource metadata fixture; graph validity remains the product compiler's job.
 def node(ident,kind,**data):return {'id':ident,'data':{'type':kind,**data}}
 nodes=[node('s','start',variables=[{'variable':'query','type':'text-input','required':True}]),node('r','knowledge-retrieval',dataset_ids=fixture['configuration']['dataset_ids'],query_variable_selector=['s','query'],retrieval_mode='multiple',multiple_retrieval_config={'top_k':3,'reranking_enable':False,'score_threshold':None}),node('c','if-else'),node('l','llm',model={'provider':fixture['configuration']['dify_model_provider'],'name':'deepseek-flash','mode':'chat','completion_params':{'temperature':.2,'max_tokens':512,'thinking':False}},context={'enabled':True,'variable_selector':['r','result']}),node('n','template-transform',template=fixture['before_literal']),node('e','end',outputs=[{'variable':'result'}])]
 native={'dependencies':[],'workflow':{'graph':{'nodes':nodes,'edges':[]},'environment_variables':[],'conversation_variables':[]}}
 resource_graph(native,fixture,'original');checks.append('fixed resource metadata accepted')
 for change in ('node','input','dataset','topk','rerank','threshold','model','tokens','thinking','context','literal','outputs','dependencies','variables'):
  value=copy.deepcopy(native);n=value['workflow']['graph']['nodes']
  if change=='node':n.append(node('http','http-request'))
  elif change=='input':n[0]['data']['variables'][0]['required']=False
  elif change=='dataset':n[1]['data']['dataset_ids']=['unapproved']
  elif change=='topk':n[1]['data']['multiple_retrieval_config']['top_k']=4
  elif change=='rerank':n[1]['data']['multiple_retrieval_config']['reranking_enable']=True
  elif change=='threshold':n[1]['data']['multiple_retrieval_config']['score_threshold']=.5
  elif change=='model':n[3]['data']['model']['name']='other'
  elif change=='tokens':n[3]['data']['model']['completion_params']['max_tokens']=513
  elif change=='thinking':n[3]['data']['model']['completion_params']['thinking']=True
  elif change=='context':n[3]['data']['context']['variable_selector']=['s','query']
  elif change=='literal':n[4]['data']['template']='other'
  elif change=='outputs':n[5]['data']['outputs'].append({'variable':'private'})
  elif change=='dependencies':value['dependencies']=[{'type':'plugin'}]
  else:value['workflow']['environment_variables']=[{'name':'secret'}]
  rejected('resource '+change,lambda:resource_graph(value,fixture,'original'))
 b=boundary()
 for _ in range(48):b.admit(httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1'))
 rejected('48 reads is final cap',lambda:b.admit(httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1')));assert b.counts['reads']==48
 b=boundary();b.counts['login']=1;rejected('one login cap',lambda:b.admit(httpx.Request('POST','https://public-dify.invalid/console/api/login',json={'email':'public@example.invalid','password':'PUBLIC_ONLY','remember_me':False})))
 for change in ('truncated','tool_call','missing_role'):
  b=boundary();value={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}}
  if change=='truncated':value['choices'][0]['finish_reason']='length'
  elif change=='tool_call':value['choices'][0]['message']['tool_calls']=[{}]
  else:value['choices'][0]['message'].pop('role')
  rejected('model final '+change,lambda:b.observed({'kind':'model','path':'/chat/completions','phase':'vague_interview'},httpx.Response(200,json=value)))
 # Retired-App IDs from earlier revisions must remain forbidden for new imports.
 from guard import known_apps
 ids=[str(uuid.uuid4()) for _ in range(4)]
 class Old:
  def list(self,kind):return {'task':[{'dify_app_id':ids[0],'runs':[{'kind':'import','result':{'app_id':ids[1]}}]}],'environment':[{'service_app_id':ids[2]}],'app_runtime_credential':[{'app_id':ids[3]}]}.get(kind,[])
 assert known_apps(Old())==set(ids);checks.append('all current/retired App identities retained')
 b=boundary();b.old_apps=known_apps(Old());b.record['approved_graph_digest']='a'*64;rejected('retired App cannot masquerade as new import',lambda:b.observed({'kind':'import','path':'/console/api/apps/imports'},httpx.Response(200,json={'app_id':ids[1]})))
 out=Path(folder)/'reject';out.mkdir();source={'stage':'vague_interview','task':task};write(out/'review-source-vague_interview.json',source);result=submit(out,'vague_interview',digest(source),'隔离测试的明确拒绝，不是实际语义结论。','reject');assert result['state']=='rejected_stopped' and (out/'stop.json').exists();checks.append('root rejection writes stop marker without external work')
 print(json.dumps({'state':'passed','gates':len(checks),'checks':checks,'physical_http':0,'production_store_constructed':False},ensure_ascii=False))
