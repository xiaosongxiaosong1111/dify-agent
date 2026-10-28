"""Read-only audit of the saved model candidate before preparing any new live scope."""
import argparse,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(Path(__file__).resolve().parent),str(PROJECT/'work/c1-planning365')]
from literal_scope import check
from support import ReadOnly,sha
from guard import capture,digest


def audit():
    store=ReadOnly(PROJECT/'data');before=capture(store)
    baseline=json.loads((PROJECT/'work/saved-plan367/post-deploy-data-snapshot.json').read_text('utf-8'))
    if before!=baseline:raise ValueError('Current saved baseline changed')
    receipt=json.loads((PROJECT/'docs/c1-planning-live-result-20261028.json').read_text('utf-8'))
    root=PROJECT/'work/c1-planning365';plan=json.loads((root/'plan.json').read_text('utf-8'))
    for name in ('plan','manifest','approval','attempt','worker-started'):
        if sha(root/(name+'.json'))!=receipt[name+'_sha256']:raise ValueError('Consumed receipt changed')
    for name,value in json.loads((root/'manifest.json').read_text('utf-8'))['files'].items():
        if sha(root/name)!=value:raise ValueError('Consumed executable changed')
    for folder,files in plan['consumed_files'].items():
        for name,value in files.items():
            if sha(PROJECT/'work'/folder/name)!=value:raise ValueError('Prior receipt changed')
    task=store.get('task',plan['target_task_id']);budget=store.get('task_budget',task['id'])
    if task['revision']!=13 or task['status']!='draft_ready' or task['plan_stale'] or not task['requirements_confirmed'] or not task['configuration_confirmed']:raise ValueError('Saved draft is no longer ready')
    original=json.loads((root/'live-output/review-source-first_plan.json').read_text('utf-8'))['task']['workflow_plan']
    retained=task['planning_runs'][-1]['last_candidate']
    if digest(original)!=receipt['first_plan_sha256'] or digest(retained)!=receipt['candidate_unchanged_sha256'] or task['workflow_plan']!=retained:raise ValueError('Original model source changed')
    fixture=json.loads((root/'fixture.json').read_text('utf-8'));comparison=check(original,retained,fixture['before_literal'],fixture['changed_fallback'])
    runs=[r for r in task['runs'] if r.get('kind')=='run']
    if len(runs)!=2 or any(r['status']!='success' or r['evaluation']['status']!='passed' or not r['diagnostics'][-1]['source_graph']['matched'] for r in runs):raise ValueError('Original observed runs changed')
    if len(budget['entries'])!=6 or len(store.list('task'))!=18 or before!=capture(store):raise ValueError('Protected state changed during local audit')
    return {'state':'saved_model_source_audited','preparation_complete':False,'task_id':task['id'],'revision':13,
            'comparison':comparison,'existing_original_runs_passed':2,'existing_model_ledger_entries':6,
            'original18_and_consumed_packages_kept':True,'credentials_decrypted':False,'network_requested':False,
            'new_model_http':0,'new_platform_actions':0,'resource_authorized':False,
            'proposed_remaining_scope_not_approved':{'model':0,'reads':28,'login':1,'import':1,'publish':1,'key':1,'run':2,'new_tasks':0,'new_libraries':0},
            'note':'仅本机核原模型完整来源和两处话术范围；完整零模型执行器、隔离验收、冻结方案及新直接批准尚未完成，不得真实执行。'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    output=Path(args.output).resolve()
    if not output.is_relative_to((PROJECT/'work').resolve()):raise SystemExit('Only a local work output is allowed')
    result=audit();output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'state':result['state'],'preparation_complete':False,'new_http':0,'resource_authorized':False}))
