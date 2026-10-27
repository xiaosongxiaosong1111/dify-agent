"""Read-only freeze of the new existing-App batch. Never creates approval, attempt or production state."""
import copy,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from execute import FROZEN,LIMITS,runtime_check,validated_plan
from support import ReadOnly,sha,sha_value,current,check_consumed
from data_guard import capture
from boundary import require
ENV='202bfb35-2f92-47c1-bc1b-eac32082181d';TASK='db13bc92-3b25-4249-abfc-4c4b384a1d17';APP='1cb02319-d42f-46b5-a1dd-34be136f83d6';WORKSPACE='c3306c18-ceb2-4bee-b2d1-796ce2048f17';BUILD='0.346.0-7335a462f131de075e28'

def freeze():
 require(ROOT==PROJECT/'work/batch-platform353','Freeze only the new canonical work directory')
 require(not any((ROOT/name).exists() for name in ('plan.json','manifest.json','approval.json','attempt.json')),'Never refreeze an existing package')
 readonly=ReadOnly(PROJECT/'data');before=capture(readonly)
 from cryptography.fernet import Fernet
 readonly.cipher=Fernet((readonly.root/'.credential-key').read_bytes())
 with tempfile.TemporaryDirectory(dir=ROOT,prefix='readonly-module-') as folder:
  os.environ['FLOWCRAFT_DATA_DIR']=folder
  from app import main as h
  from app.publication_recovery import matching_evidence
  from app.publication_dispatch_receipt import validate
  from app.dsl_roundtrip import parse
  from app.workflow_publication import core
  h.store=readonly;h.DATA_ROOT=readonly.root
  task=readonly.get('task',TASK);env=readonly.get('environment',ENV)
  require(task['revision']==6 and task['status']=='imported' and task['dify_app_id']==APP and task['environment_id']==ENV and task.get('intake_required') is True and task.get('plan_review_required') is True,'Original Task source/gates changed')
  require(env['console_workspace_id']==WORKSPACE and env['version']=='1.17.1' and env.get('console_login_binding')=={'base_url':env['base_url'],'version':env['version'],'workspace_id':WORKSPACE},'Original workspace binding changed')
  for t in readonly.list('task'):h.require_idle(t)
  require(not any(r.get('kind')=='run' for r in task['runs']) and h.execution_limits.preflight(task,1)['limits_allow_requested_runs'],'Existing Task already run or capacity unavailable')
  proofs=[r for r in readonly.list('publication_dispatch_evidence') if r.get('task_id')==TASK];require(len(proofs)==1,'Expected one independently registered evidence record')
  evidence=matching_evidence(h,task,proofs[0]['id'])
  source=validate(PROJECT,PROJECT/'work/batch-platform350',evidence['source']['source_commit'],evidence['source']['report_path']);require(source==evidence['source'],'Original committed source changed')
  require(evidence['binding']['graph_digest']==sha_value(core(parse((ROOT/'candidate.yml').read_text('utf-8'),'workflow')['workflow'])),'Frozen public graph mismatch')
  require(task['test_cases'][0]['id']=='public-four-items' and len(task['test_cases'])==1 and task['test_cases'][0]['input']==json.loads((ROOT/'fixture.json').read_text('utf-8'))['input'],'Existing saved public case differs')
  plan350=json.loads((PROJECT/'work/batch-platform350/plan.json').read_text('utf-8'));manifest350=json.loads((PROJECT/'work/batch-platform350/manifest.json').read_text('utf-8'))
  consumed={folder:copy.deepcopy(plan350[field]) for folder,field in [('branch-mainline289','consumed124_files'),('batch-platform342','consumed180_files'),('batch-platform348','consumed348_files')]}
  consumed['batch-platform350']=copy.deepcopy(manifest350['files'])|{name:sha(PROJECT/'work/batch-platform350'/name) for name in ('manifest.json','approval.json','attempt.json')}
  plan={'schema_version':1,'batch_id':'existing-batch-platform353','state':'frozen_unapproved','limits':LIMITS,'wall_seconds':600,'task_id':TASK,'revision':6,'app_id':APP,'environment_id':ENV,'workspace_id':WORKSPACE,'evidence_id':evidence['id'],'old_publication_id':evidence['publication_id'],'evidence_sha256':sha_value(evidence),'task_sha256':sha_value(task),'environment_sha256':sha_value(env),'graph_digest':source['graph_digest'],'artifact_sha256':task['artifact']['sha256'],'runtime_build':BUILD,'runtime_process_sha256':sha(PROJECT/'runtime-process.ps1'),'runtime_manifest_sha256':sha(PROJECT/'.runtime/snapshots'/BUILD/'runtime-manifest.json'),'protected_data':before,'consumed_files':consumed,'proposed_transfer':{'from_batch':'public-batch-platform350','only_zero_dispatch':{'publish':1,'key':1,'run':1},'old_batch_not_replayed':True,'old_unknown_kept':True},'proposed_cumulative':{'actual_apps_before':9,'actual_apps_after_max':9,'actual_publications_before':8,'actual_publications_after_max':9,'actual_keys_before':8,'actual_keys_after_max':9,'actual_runs_before':16,'actual_runs_after_max':17,'conservative_resource_each':10,'conservative_runs':18,'management_reserved_before':461,'management_reserved_after':477,'login_reserved_before':31,'login_reserved_after':32,'model_actual':20,'model_conservative':24},'cost':{'new_dify_estimate_usd':'0.01','hard_billing_cap':False,'host_sandbox_cost':'unknown','old_unknown_and_reservations_kept':True},'external_scope_approved':False,'automatic_retry':False,'automatic_cleanup':False,'business_acceptance_complete':False}
  current(plan,readonly);check_consumed(PROJECT,plan);runtime=runtime_check(plan)
  require(capture(readonly)==before,'Production changed during read-only freeze')
 (ROOT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),'utf-8')
 manifest={'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(ROOT/name) for name in sorted(FROZEN)}};(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2),'utf-8');validated_plan(ROOT)
 proof={'state':'frozen_unapproved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'runtime':runtime,'production_unchanged':capture(readonly)==before,'physical_model_dify_http':0,'new_tasks_apps':0,'approval_created':False,'attempt_created':False}
 (ROOT/'freeze-proof.json').write_text(json.dumps(proof,indent=2),'utf-8');print(json.dumps(proof))
if __name__=='__main__':freeze()
