import os,sys,tempfile,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1]
sys.path.insert(0,str(PROJECT/'work/branch-mainline289'));from support import snapshot
before=snapshot();assert before==json.loads((PROJECT/'work/branch-mainline289/post-success-snapshot.json').read_text('utf-8'))
with tempfile.TemporaryDirectory(dir=ROOT,prefix='stage-local-') as folder:
 os.environ['FLOWCRAFT_DATA_DIR']=folder;sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
 import httpx
 from fastapi.testclient import TestClient
 from app import main
 from local_pipeline import LocalPipeline
 def forbidden(*a,**kw):raise AssertionError('Physical upstream/model forbidden')
 httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=forbidden;main.DifyClient.request=forbidden;main.call_model=forbidden
 with TestClient(main.app) as api:
  env=api.post('/api/environments',json={'name':'公开隔离环境','base_url':'https://public-dify.invalid','version':'1.17.1'}).json()
  record={};runner=LocalPipeline(api,env['id'],record)
  try:task=runner.prepare()
  except Exception:
   (ROOT/'local-rehearsal-failed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');raise
  raw=main.store.get('task',task['id']);assert raw['intake_required'] and raw['plan_review_required'] and raw['intake_review']['review_actor']=='agent_delegated'
  assert raw['requirements_confirmed'] and raw['configuration_confirmed'] and not raw['plan_stale'] and not raw.get('dify_app_id') and len(raw['runs'])==0
  assert raw['workflow_plan']==json.loads((ROOT/'candidate-plan.json').read_text('utf-8')) and not main.budgets.get(task['id'])['entries']
  record.update(state='local_gate_passed',normal_new_task_gates_kept=True,agent_review_not_human_signoff=True,physical_http=0,model_http=0,external_resources=0)
assert not Path(folder).exists() and snapshot()==before
record['production16_snapshot_kept']=True
record['program_sha256']={f.name:__import__('hashlib').sha256(f.read_bytes()).hexdigest() for f in ROOT.glob('*.py')}
(ROOT/'local-rehearsal-proof.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');print(json.dumps({'state':record['state'],'local_requests':len(record['local_requests']),'real_external':0}))
