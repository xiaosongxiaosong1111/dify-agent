"""Prove local readiness precedes one-shot consumption; no production Store or HTTP."""
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[1];FROZEN=PROJECT/'work/c1-resume360'
sys.path[:0]=[str(FROZEN),str(PROJECT/'backend')]
import execute
from local_readiness import NotReady

with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='admission360-') as folder:
 project=Path(folder);root=project/'work/c1-resume360';root.mkdir(parents=True)
 plan={'batch_id':'c1-resume360','playwright_path':str(project)}
 for name in ('plan.json','manifest.json','approval.json'):(root/name).write_text('{"synthetic_only":true}','utf-8')
 events=[]
 def unavailable(*a):events.append('readiness');raise NotReady('local_docker_engine_unavailable')
 def forbidden(*a):raise AssertionError('Not-ready stack consumed an attempt')
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',project),patch.object(execute,'validated',lambda _:plan),patch.object(execute,'approved',lambda *a:None),patch.object(execute,'current',lambda *a:events.append('data')),patch.object(execute,'runtime_check',unavailable),patch.object(execute,'claim',forbidden),patch.object(sys,'argv',['execute.py','live','--playwright',str(project)]):
  try:execute.main()
  except NotReady as exc:assert exc.code=='local_docker_engine_unavailable'
  else:raise AssertionError('Not-ready stack passed')
 assert events==['data','readiness'] and not (root/'attempt.json').exists()
 class StopAfterClaim(RuntimeError):pass
 events=[]
 def ready(*a):events.append('readiness');return {'local_dify_readiness':{'ready':True}}
 def claim(*a):events.append('claim');raise StopAfterClaim()
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',project),patch.object(execute,'validated',lambda _:plan),patch.object(execute,'approved',lambda *a:None),patch.object(execute,'current',lambda *a:events.append('data')),patch.object(execute,'runtime_check',ready),patch.object(execute,'claim',claim),patch.object(sys,'argv',['execute.py','live','--playwright',str(project)]):
  try:execute.main()
  except StopAfterClaim:pass
  else:raise AssertionError('Unexpected worker launch')
 assert events==['data','readiness','claim']
 print(json.dumps({'state':'passed','admission_order_checks':2,'not_ready_consumes_attempt':False,'readiness_precedes_claim':True,'physical_http':0,'production_store_constructed':False}))
