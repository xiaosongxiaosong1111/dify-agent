"""Read-only local freeze. Never authorize or consume the proposed real batch."""
import json,sqlite3,contextlib,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path[:0]=[str(ROOT),str(PROJECT/'backend'),str(PROJECT/'work/branch-mainline289')]
from execute import sha,require,FROZEN,runtime_check
from boundary import digest
from data_guard import capture
from support import snapshot
ENV='202bfb35-2f92-47c1-bc1b-eac32082181d'
WORKSPACE='c3306c18-ceb2-4bee-b2d1-796ce2048f17'
BUILD='0.341.0-cf06d6388885cb69a63c'
class ReadOnly:
 root=PROJECT/'data'
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
  try:yield db
  finally:db.close()
def freeze():
 require(not (ROOT/'approval.json').exists() and not (ROOT/'attempt.json').exists(),'Cannot refreeze an approved or consumed package')
 from urllib.parse import urlsplit
 from app.dsl_roundtrip import parse
 from app.workflow_publication import core
 store=ReadOnly()
 with store.connect() as db:
  objects=[(k,i,json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')];secret_ids={r[0] for r in db.execute('SELECT id FROM secrets')}
 env=next(v for k,i,v in objects if k=='environment' and i==ENV);tasks=[v for k,i,v in objects if k=='task']
 require(len(tasks)==16 and env['console_workspace_id']==WORKSPACE and env['version']=='1.17.1','Original task/workspace baseline changed')
 require(all(ENV+':'+key in secret_ids for key in ('console_login_email','console_login_password','service_api_key')),'Encrypted dedicated login/runtime binding missing')
 require(env.get('console_login_binding')=={'base_url':env['base_url'],'version':env['version'],'workspace_id':WORKSPACE},'Saved identity not bound to original workspace')
 url=urlsplit(env['base_url']);require(url.scheme in ('http','https') and url.netloc and url.path in ('','/') and not url.query and not url.fragment and not url.username and not url.password,'Unexpected Console origin')
 legacy=snapshot();require(legacy==json.loads((PROJECT/'work/branch-mainline289/post-success-snapshot.json').read_text('utf-8')),'Original legacy state changed')
 consumed=json.loads((PROJECT/'work/tool-probe291/before.json').read_text('utf-8'))['consumed124_files'];require(all(sha(PROJECT/'work/branch-mainline289'/name)==value for name,value in consumed.items()),'Consumed124 package changed')
 apps=set()
 def add(value):
  if isinstance(value,str):
   try:
    if str(uuid.UUID(value))==value:apps.add(value)
   except ValueError:pass
 for kind,ident,value in objects:
  if kind=='environment':add(value.get('service_app_id'))
  elif kind=='task':
   add(value.get('dify_app_id'))
   for run in value.get('runs',[]):add(run.get('app_id'));add(run.get('dify_app_id'))
  elif kind=='app_runtime_credential':add(value.get('app_id'))
 binding_keys=('id','name','base_url','version','console_workspace_id','console_login_binding','connection_revision','service_app_id','capabilities','console_login_blocked')
 graph=digest(core(parse((ROOT/'candidate.yml').read_text('utf-8'),'workflow')['workflow']))
 manifest_path=PROJECT/'.runtime/snapshots'/BUILD/'runtime-manifest.json'
 plan={'schema_version':1,'batch_id':'public-batch-platform342','state':'frozen_unapproved','environment_id':ENV,'workspace_id':WORKSPACE,'runtime_build':BUILD,'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'runtime_manifest_sha256':sha(manifest_path),'graph_digest':graph,'limits':{'new_tasks':1,'reads':16,'login':1,'import':1,'publish':1,'key':1,'run':1,'model':0},'wall_seconds':600,'environment_binding':{k:env.get(k) for k in binding_keys},'original_app_ids':sorted(apps),'protected_data':capture(store),'legacy_snapshot':legacy,'consumed124_files':consumed,'approval_reply':'允许这批公开批量计算平台新范围','proposed_cumulative':{'real_runs_before':16,'real_runs_after_max':17,'app_publish_key_each_before':8,'app_publish_key_each_after_max':9,'management_reserved_before':413,'management_reserved_after':429,'login_reserved_before':28,'login_reserved_after':29,'model_actual':20,'model_conservative':24},'cost':{'estimate_usd':'0.01','bill_hard_cap':False,'host_sandbox_cost':'unknown','old_unknown_and_reserved_unchanged':True},'task_limits':{'max_started_runs':1,'max_total_minutes':10,'max_reported_cost_usd':'0.01'},'original_tasks':16,'model_calls':0,'retry':False,'automatic_cleanup':False,'business_acceptance_complete':False}
 proof=runtime_check(plan)
 require(capture(store)==plan['protected_data'],'Production data changed during read-only runtime check')
 (ROOT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),'utf-8')
 manifest={'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(ROOT/name) for name in sorted(FROZEN)}}
 (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
 summary={'state':'frozen_unapproved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'files':manifest['files'],'runtime':proof,'original16_kept':snapshot()==legacy,'production_mutations':0,'real_model_dify_http':0,'approval_created':False,'attempt_created':False}
 (ROOT/'freeze-proof.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({k:v for k,v in summary.items() if k not in ('files',)}))
if __name__=='__main__':freeze()
