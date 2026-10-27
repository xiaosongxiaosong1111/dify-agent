"""Isolated admission/transport/protection checks; no real approval or attempt."""
import asyncio,copy,hashlib,json,os,shutil,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path[:0]=[str(ROOT),str(PROJECT/'backend'),str(PROJECT/'work/branch-mainline289')]
import httpx
from execute import approved,validated_plan,claim_attempt,dispatch,sha,FROZEN
from boundary import Boundary,require,digest
from data_guard import capture,guarded_store,verify
from freeze_bundle import ReadOnly
from support import snapshot
production_before=capture(ReadOnly())
before=snapshot();require(not (ROOT/'approval.json').exists() and not (ROOT/'attempt.json').exists(),'Actual batch already authorized/consumed')
checks=[]
def denied(name,action):
 try:action()
 except (RuntimeError,FileExistsError,FileNotFoundError,KeyError,ValueError):checks.append(name);return
 raise AssertionError('Unexpected admission: '+name)
with tempfile.TemporaryDirectory(dir=ROOT,prefix='gates-') as folder:
 temp=Path(folder);bundle=temp/'bundle';bundle.mkdir()
 for name in FROZEN:shutil.copyfile(ROOT/name,bundle/name)
 shutil.copyfile(ROOT/'manifest.json',bundle/'manifest.json');plan=validated_plan(bundle);checks.append('matching_frozen_package')
 denied('missing_human_reply',lambda:approved(bundle,plan))
 approval={'authorization_source':'direct_human_reply','decision':'approve','batch_id':plan['batch_id'],'plan_sha256':sha(bundle/'plan.json'),'manifest_sha256':sha(bundle/'manifest.json'),'question_ref':'SYNTHETIC_SCHEMA_TEST_NOT_AUTHORIZATION','reply':'PUBLIC_SYNTHETIC_SCHEMA_TEST'}
 for field,value in [('authorization_source','agent_delegated'),('decision','reject'),('batch_id','wrong'),('plan_sha256','wrong'),('manifest_sha256','wrong'),('question_ref',''),('reply','')]:
  (bundle/'approval.json').write_text(json.dumps(approval|{field:value}),'utf-8');denied('approval_'+field,lambda:approved(bundle,plan))
 (bundle/'approval.json').write_text(json.dumps(approval),'utf-8');approved(bundle,plan);checks.append('matching_schema_only_in_temporary_fixture')
 claim_attempt(bundle,{'synthetic':True});denied('exclusive_attempt_no_replay',lambda:claim_attempt(bundle,{'synthetic':True}))
 path=bundle/'fixture.json';original=path.read_bytes();path.write_bytes(original+b' ');denied('frozen_hash_change',lambda:validated_plan(bundle));path.write_bytes(original)
 manifest=json.loads((bundle/'manifest.json').read_text('utf-8'));(bundle/'manifest.json').write_text(json.dumps(manifest|{'files':{k:v for k,v in manifest['files'].items() if k!='boundary.py'}}),'utf-8');denied('missing_manifest_file',lambda:validated_plan(bundle))
 (bundle/'manifest.json').write_text(json.dumps(manifest|{'files':manifest['files']|{'../outside':sha(bundle/'fixture.json')}}),'utf-8');denied('manifest_extra_or_outside',lambda:validated_plan(bundle))
 fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));graph=plan['graph_digest'];newapp=str(uuid.uuid4());published=str(uuid.uuid4())
 def boundary():return Boundary('https://public-dify.invalid',str(uuid.uuid4()),graph,fixture,{},[newapp])
 async def blocked(name,b,request):
  forwards=[]
  async def physical(req):forwards.append(req);return httpx.Response(200,json={},request=req)
  try:await dispatch(b,physical,request)
  except Exception:pass
  else:raise AssertionError('Unexpected transport admission: '+name)
  require(not forwards and b.halted,'Disallowed request reached transport');checks.append(name)
  try:await dispatch(b,physical,httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1'))
  except RuntimeError:pass
  require(not forwards,'Request dispatched after batch stopped')
 async def outbound_checks():
  for name,method,url,body in [('wrong_origin','GET','https://other.invalid/console/api/apps',None),('unlisted_endpoint','GET','https://public-dify.invalid/console/api/providers',None),('old_app_read','GET','https://public-dify.invalid/console/api/apps/'+newapp,None),('import_overwrite','POST','https://public-dify.invalid/console/api/apps/imports',{'mode':'yaml-content','name':fixture['task_name'],'yaml_content':(ROOT/'candidate.yml').read_text('utf-8'),'app_id':newapp}),('unapproved_model','POST','https://public-dify.invalid/v1/chat/completions',{}),('login_shape','POST','https://public-dify.invalid/console/api/login',{'email':'public@example.invalid','password':'public','remember_me':True})]:
   await blocked(name,boundary(),httpx.Request(method,url,json=body) if body is not None else httpx.Request(method,url))
  b=boundary();b.started-=601;await blocked('wall_before_dispatch',b,httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1'))
  b=boundary();b.counts['reads']=16;await blocked('reads_cap',b,httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1'))
  b=boundary();b.counts['login']=1;await blocked('second_login',b,httpx.Request('POST','https://public-dify.invalid/console/api/login',json={'email':'public@example.invalid','password':'public','remember_me':False}))
  for which in ('key','run'):
   b=boundary();b.app=newapp;b.published=published;b.key='app-PUBLIC';b.counts[which]=1
   request=httpx.Request('POST','https://public-dify.invalid/console/api/apps/'+newapp+'/api-keys',json={}) if which=='key' else httpx.Request('POST','https://public-dify.invalid/v1/workflows/run',json={'inputs':fixture['input'],'response_mode':'blocking','user':'flowcraft-local'},headers={'authorization':'Bearer app-PUBLIC'})
   await blocked('second_'+which,b,request)
  for name,inputs,token in [('changed_inputs',{'items_json':'[]'},'app-PUBLIC'),('wrong_runtime_key',fixture['input'],'app-OTHER')]:
   b=boundary();b.app=newapp;b.published=published;b.key='app-PUBLIC';await blocked(name,b,httpx.Request('POST','https://public-dify.invalid/v1/workflows/run',json={'inputs':inputs,'response_mode':'blocking','user':'flowcraft-local'},headers={'authorization':'Bearer '+token}))
 asyncio.run(outbound_checks())
 from app.storage import Store
 source=Store(temp/'data');env=str(uuid.uuid4());source.put('environment',env,{'id':env,'name':'public','base_url':'https://public-dify.invalid','capabilities':{}});source.put('task','original',{'id':'original'});source.set_secret('unrelated','api_key','PUBLIC_FIXTURE_ONLY')
 (source.root/'public-original.txt').write_text('public original task asset','utf-8')
 old=capture(source);b=boundary();Guard=guarded_store(Store,old,env,b,source.get('environment',env),fixture['task_name']);guard=Guard(temp/'data')
 denied('original_task_write',lambda:guard.put('task','original',{'id':'original','changed':True}))
 denied('unrelated_secret_decryption',lambda:guard.secret('unrelated','api_key'))
 denied('original_login_cipher_write',lambda:guard.set_secret(env,'console_login_password','PUBLIC_NEW'))
 denied('unapproved_object',lambda:guard.put('provider','extra',{}))
 guard.owner='owned';denied('new_model_reservation',lambda:guard.put('task_budget','owned',{'entries':[{'status':'reserved'}]}))
 denied('other_task_budget',lambda:guard.put('execution_limits','other',{}))
 denied('new_task_gate_bypass',lambda:guard.put('task','owned',{'intake_required':False,'plan_review_required':True}))
 denied('other_connection_write',lambda:guard.put('environment','other',{}))
 require(capture(guard)==old,'Rejected mutation affected fixture data')
 for name in ('.credential-key','public-original.txt'):
  file=guard.root/name;original=file.read_bytes();file.write_bytes(b'PUBLIC_MUTATION_TEST');denied('protected_file_'+name,lambda:verify(guard,old,env));file.write_bytes(original)
require(capture(ReadOnly())==production_before==plan['protected_data'],'Frozen production data changed after runtime preflight')
checks.append('exact_production_baseline_after_local_runtime_read')
require(snapshot()==before and not (ROOT/'approval.json').exists() and not (ROOT/'attempt.json').exists(),'Actual batch/source was modified by gate tests')
proof={'state':'passed','checks':checks,'count':len(checks),'synthetic_authorization_fixture_only':True,'actual_approval_created':False,'actual_attempt_created':False,'production16_snapshot_kept':True,'real_model_dify_http':0,'program_sha256':{f.name:sha(f) for f in ROOT.glob('*.py')}}
(ROOT/'gates-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({k:v for k,v in proof.items() if k not in ('checks','program_sha256')}))
