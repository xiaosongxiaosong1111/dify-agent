"""New independent diagnostic scope; stopped375 never resumes."""
import argparse
import json
import os
import sys
from pathlib import Path
from support import PROJECT,LIMITS,ReadOnly,capture,digest,load,require,runtime_check,sha

ROOT=Path(__file__).resolve().parent
TARGET={'task_id':'62bb060f-b7fa-4397-acb0-ba931c7dbfb2','revision':5,'run_id':'f7576baa-61f4-43b2-80d9-4ad0609c897f','app_id':'aa4a052e-c7b4-4b84-b4bf-4fe741afb22f','message_id':'091f7f7e-a0b8-46e2-8abd-d7db285ed11c','conversation_id':'b4fbd90f-1b62-49f4-b90c-d55d725e1d0e','environment_id':'202bfb35-2f92-47c1-bc1b-eac32082181d','workspace_id':'c3306c18-ceb2-4bee-b2d1-796ce2048f17','dataset_id':'d12cf081-5c52-41e3-b869-e94e6f8d37b1'}
UPPER={'model':30,'reads':701,'login':39,'import':14,'publish':14,'key':14,'run':36}
REGRANT={'from_batch':'chatflow-order375','reads':10,'new_reads':0,'new_login':1}
FROZEN={'support.py','probe.py','worker.py','synthetic.py','execute.py','freeze.py','rehearse.py','local_readiness.py','README.md','target.json','plan.json'}

def validated(root):
    manifest=load(root/'manifest.json');require(manifest.get('batch_id')=='first-case-trace376' and manifest.get('schema_version')==1 and set(manifest.get('files',{}))==FROZEN,'Manifest invalid')
    for name,value in manifest['files'].items():require((root/name).resolve().parent==root.resolve() and not (root/name).is_symlink() and sha(root/name)==value,'Frozen file changed')
    plan=load(root/'plan.json');require(load(root/'target.json')==TARGET and type(load(root/'target.json')['revision']) is int,'Target changed')
    require(plan.get('batch_id')=='first-case-trace376' and plan.get('limits')==LIMITS and all(type(v) is int for v in plan['limits'].values()) and plan.get('explicit_regrant')==REGRANT and all(type(v) is int for k,v in plan['explicit_regrant'].items() if k!='from_batch') and plan.get('conservative_upper')==UPPER and plan.get('wall_seconds')==600 and plan.get('model_estimate_book_upper_usd')=='0.755473652' and plan.get('old_reservations_preserved') is True,'Scope changed')
    require(plan.get('runtime_build')=='0.356.0-5476d30269eac2811387' and plan.get('backend_path')==str(PROJECT/'.runtime/snapshots'/plan['runtime_build']/'backend'),'Wrong runtime')
    return plan

def approved(root,plan):
    value=load(root/'approval.json')
    require(value.get('authorization_source')=='direct_human_reply' and value.get('decision')=='approve' and value.get('batch_id')==plan['batch_id'] and value.get('plan_sha256')==sha(root/'plan.json') and value.get('manifest_sha256')==sha(root/'manifest.json') and value.get('limits')==LIMITS and all(type(v) is int for v in value['limits'].values()) and value.get('explicit_regrant')==REGRANT and all(type(v) is int for k,v in value['explicit_regrant'].items() if k!='from_batch') and value.get('conservative_upper')==UPPER and value.get('old_reservations_preserved') is True and all(isinstance(value.get(k),str) and value[k].strip() for k in ('question_ref','reply')),'New direct regrant/login approval required')
    return value

def current(root,plan):
    store=ReadOnly(PROJECT/'data');require(capture(store)==plan['protected_data'] and len(store.list('task'))==19,'Data/source changed')
    for name,value in plan['old_evidence'].items():require((PROJECT/name).resolve().is_relative_to(PROJECT/'work') and sha(PROJECT/name)==value,'Consumed375/old evidence changed')
    parent=load(PROJECT/'work/chatflow-order375/live-output/progress.json');require(parent['state']=='stopped' and parent['dispatch_counts']['reads']==13 and 128-parent['dispatch_counts']['reads']>=10,'Old unused-read source changed')
    task=store.get('task',TARGET['task_id']);run=next(r for r in task['runs'] if r['id']==TARGET['run_id']);value=run.get('result') or {}
    require(task['revision']==5 and task['dify_app_id']==TARGET['app_id'] and task.get('configuration',{}).get('dataset_ids')==[TARGET['dataset_id']] and task['configuration'].get('assistant_provider_id') is None and run['status']=='success' and run['evaluation']['status']=='failed' and value.get('message_id')==TARGET['message_id'] and value.get('conversation_id')==TARGET['conversation_id'],'Case source mismatch')
    env=store.get('environment',TARGET['environment_id']);require(digest(env)==plan['environment_sha256'] and env.get('console_workspace_id')==TARGET['workspace_id'],'Environment/workspace changed')
    return env

def claim(root,value):
    with (root/'attempt.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)

def authorized(root,plan):
    require(root==PROJECT/'work/first-case-trace376' and not sys.flags.optimize,'Only canonical unoptimized worker')
    require(validated(root)==plan,'Plan changed');approved(root,plan);current(root,plan);attempt=load(root/'attempt.json')
    require(attempt.get('state')=='admitted' and attempt.get('approval_sha256')==sha(root/'approval.json'),'No matching consumed admission')
    with (root/'worker-started.json').open('x',encoding='utf-8') as f:json.dump({'pid':os.getpid(),'approval_sha256':attempt['approval_sha256'],'single_worker':True},f)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['validate','live']);args=p.parse_args();require(ROOT==PROJECT/'work/first-case-trace376' and not sys.flags.optimize,'Use frozen canonical entry')
    plan=validated(ROOT)
    if args.action=='validate':print(json.dumps({'state':'validated_not_approved','plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json')}));return
    approved(ROOT,plan);require(not (ROOT/'attempt.json').exists() and not (ROOT/'worker-started.json').exists(),'Consumed;no replay')
    env=current(ROOT,plan);runtime=runtime_check(plan);from local_readiness import check
    readiness=check(env['base_url']);record={'state':'admitted','batch_id':plan['batch_id'],'plan_sha256':sha(ROOT/'plan.json'),'manifest_sha256':sha(ROOT/'manifest.json'),'approval_sha256':sha(ROOT/'approval.json'),'runtime':runtime,'readiness':readiness,'automatic_retry':False};claim(ROOT,record)
    try:
        from worker import run
        result=run('live',ROOT/'live-output',plan);record.update(state=result['state'],dispatch_counts=result['dispatch_counts'])
    except BaseException as exc:record.update(state='stopped',failure_type=type(exc).__name__)
    finally:
        temp=ROOT/'attempt-writing.tmp';temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,ROOT/'attempt.json')
    require(record['state']=='diagnostic_complete_no_retest','Consumed diagnostic stopped;no retry')

if __name__=='__main__':main()
