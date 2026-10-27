"""Isolate the real frozen entry, including approval claim and Store wiring; only runtime/PID inspection is stubbed."""
import argparse,copy,json,os,runpy,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT/'work/batch-platform353'
p=argparse.ArgumentParser(description='Full frozen entry in a disposable synthetic project; never real live scope.');p.add_argument('--output',required=True);args=p.parse_args();OUT=Path(args.output).resolve();assert OUT.is_relative_to(PROJECT/'work');OUT.mkdir(exist_ok=False,parents=True)
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
import platform_pipeline
from execute import validated_plan
validated_plan(ROOT)
from support import sha,sha_value,ReadOnly
from data_guard import capture
before=capture(ReadOnly(PROJECT/'data'))
original=platform_pipeline.run

def entry(api,small,outer_record):
 from app import main as h
 import execute,httpx
 from boundary import Boundary
 from synthetic_transport import SyntheticDify
 source=h.store.root;assert source.resolve().is_relative_to(OUT/'fixture'),'Only disposable synthetic fixtures may be copied';task=h.store.get('task',small['task_id']);env=h.store.get('environment',small['environment_id']);evidence=h.store.get('publication_dispatch_evidence',small['evidence_id'])
 # Copy only disposable synthetic fixtures, never production SQLite or credentials.
 project=OUT/'project';project.mkdir();data=project/'data';shutil.copytree(source,data)
 root=project/'work/batch-platform353';root.mkdir(parents=True)
 for name in execute.FROZEN-{'plan.json'}:shutil.copyfile(ROOT/name,root/name)
 plan={'schema_version':1,'batch_id':'existing-batch-platform353','limits':execute.LIMITS,'wall_seconds':600,'task_id':task['id'],'revision':task['revision'],'app_id':task['dify_app_id'],'environment_id':env['id'],'workspace_id':env['console_workspace_id'],'evidence_id':evidence['id'],'old_publication_id':evidence['publication_id'],'evidence_sha256':sha_value(evidence),'task_sha256':sha_value(task),'environment_sha256':sha_value(env),'graph_digest':evidence['source']['graph_digest'],'protected_data':capture(ReadOnly(data)),'consumed_files':{}}
 (root/'plan.json').write_text(json.dumps(plan),'utf-8');manifest={'schema_version':1,'batch_id':plan['batch_id'],'files':{name:sha(root/name) for name in execute.FROZEN}};(root/'manifest.json').write_text(json.dumps(manifest),'utf-8')
 approval={'authorization_source':'direct_human_reply','decision':'approve','batch_id':plan['batch_id'],'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'limits':execute.LIMITS,'explicit_zero_dispatch350_transfer_authorized':True,'old_reservations_preserved':True,'question_ref':'synthetic-only','reply':'isolated synthetic approval'};(root/'approval.json').write_text(json.dumps(approval),'utf-8')
 boundary=h.store.batch_boundary
 fake=SyntheticDify(boundary,'success')
 from app.dsl_roundtrip import parse
 fake.draft=parse(h.artifact_path(task).read_text('utf-8'),'workflow')['workflow']|{'hash':'entry-native-draft'}
 async def forward(transport,request):return await fake(request)
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',project),patch.object(execute,'runtime_check',lambda p:{'synthetic_runtime_only':True}),patch.object(sys,'argv',['execute.py','live']),patch.object(platform_pipeline,'run',original),patch.object(httpx.AsyncHTTPTransport,'handle_async_request',forward):execute.main()
 receipt=json.loads((root/'attempt.json').read_text('utf-8'));assert receipt['state']=='passed',receipt
 assert receipt['dispatch_counts']=={'reads':11,'login':1,'import':0,'publish':1,'key':1,'run':1}
 assert receipt['protection']['original_unknown_kept'] is True
 (OUT/'proof.json').write_text(json.dumps({'state':'passed','same_frozen_execute_main':True,'only_runtime_cim_stubbed':True,'synthetic_counts':receipt['dispatch_counts'],'physical_http':0,'original_unknown_kept':True,'new_tasks_apps':0},indent=2),'utf-8')
 # Avoid deleting a Store still selected by the outer synthetic TestClient.
 h.store=ReadOnly(source);h.DATA_ROOT=source
 raise SystemExit(0)
platform_pipeline.run=entry
try:
 with patch.object(sys,'argv',['rehearse.py','success','--output',str(OUT/'fixture')]):runpy.run_path(str(ROOT/'rehearse.py'),run_name='__main__')
except SystemExit as e:assert e.code==0,e
finally:assert capture(ReadOnly(PROJECT/'data'))==before
print('Full frozen execute.main isolated entry passed; production unchanged, physical HTTP0')
