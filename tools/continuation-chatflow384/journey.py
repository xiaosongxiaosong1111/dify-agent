"""Normal product API operations for frozen manual-template scope, not model planning."""
import copy
import hashlib
import io
import json
import zipfile
from uuid import uuid4
from common import digest,require


def run(api,h,b,fixture,contract,output,mode='success'):
    def call(method,path,body=None):
        require(not b.halted,'Batch stopped')
        r=api.request(method,path,json=body) if body is not None else api.request(method,path)
        require(r.status_code in (200,201),'Product API refused '+path+' status '+str(r.status_code))
        return r.json()
    def fresh():return h.get_task(b.owner)
    def post(path,**body):return call('POST',base+path,{'revision':fresh()['revision'],**body})
    def review():
        state=call('GET',base+'/intake');t=fresh()
        extra={'memory':'明确启用最近5轮上下文，新样例新会话；缺号后补号仍查询该明确单号，不跨样例复用。','dialogue':fixture['inputs']['clarify_reply']+' 缺订单号时明确追问；没有人工系统，仅固定文字指引。','retrieval':t['requirements']['knowledge']+' 空检索直接回复，有片段但不足由资料回答节点逐字回复无答案文字。','external':t['requirements']['knowledge']+' 唯一根代码节点使用已声明的合成表，不连接真实订单接口，不新增其它系统。'}
        answers={row['id']:t['requirements'][row['id']] if row['id'] in t['requirements'] else extra[row['id']] for row in state['standard']}
        return post('/intake/manual',context_token=state['context_token'],answers=answers,acknowledge_review=True,actor='agent_delegated',actor_note='按用户常规开发委托及本批直接批准的公开冻结说明逐项核对；人工模板，非模型访谈、模型规划或人类签收。')
    def capture_failed_turn(record):
        require('failure_capture' not in b.record,'Failure report already attempted')
        turns=(record.get('result') or {}).get('turns') or []
        failed=[t for t in turns if (t.get('evaluation') or {}).get('status')=='failed']
        require(not turns or len(failed)==1,'Failure turn ambiguous')
        turn=failed[0]['index'] if failed else None;result=failed[0]['result'] if failed else record['result'];before=b.counts['reads']
        b.record['failure_capture']={'state':'requested','case_id':fixture['cases'][b.case_index]['id'],'turn':turn,'reports_attempted':1,'management_reads':0};b.save()
        try:
            b.begin_failure(result.get('message_id'),result.get('conversation_id'))
            report=post('/runs/'+record['id']+'/diagnose',read_remote=True,**({'turn_index':turn} if turn else {}))
            b.record['failure_capture'].update(state='captured' if report['trace_state']=='read' and report['source_graph']['matched'] else 'unavailable',native_run_id=report.get('remote_run_id'),node_ids=sorted(n['node_id'] for n in report.get('nodes',[])),remote_status=report.get('remote_status'),source_graph_matched=report.get('source_graph',{}).get('matched',False))
        finally:
            b.record['failure_capture']['management_reads']=b.counts['reads']-before;b.halted=True;b.save()
        require(b.record['failure_capture']['management_reads']<=4,'Failure diagnostic cap exceeded')
    def assert_diagnostic(run,turn=None):
        report=post('/runs/'+run['id']+'/diagnose',read_remote=True,**({'turn_index':turn} if turn else {}))
        require(report['trace_state']=='read' and not report['truncated'] and report['source_graph']['matched'] and report['remote_status']=='succeeded','Incomplete/mismatched native trace')
        ids={n['node_id'] for n in report['nodes']};expected={'start','intent'}
        case=b.case_index
        if case==0:expected|={'retrieve','collect_docs','check_hit','grounded_answer','faq_answer'}
        elif case==1:
            expected|={'retrieve','collect_docs','check_hit'}
            require({'no_hit','no_hit_answer'}<=ids or {'grounded_answer','faq_answer'}<=ids,'No-answer branch missing')
        elif case==2:expected|={'clarify','clarify_answer'}
        elif case in (3,4) or turn==2:expected|={'extract_order','check_order','validate_order','check_order_value','order_lookup','order_answer'}
        else:expected|={'extract_order','check_order','missing_order','missing_order_answer'}
        require(expected<=ids and all(n['status']=='succeeded' for n in report['nodes']),'Required branch not executed')
        require(('order_lookup' in ids)==(case in (3,4) or turn==2),'Unexpected mock lookup')
        require(('grounded_answer' in ids)==(case==0 or case==1 and 'faq_answer' in ids),'Unexpected answer model')
        b.record.setdefault('traces',[]).append({'version':b.version,'case_id':fixture['cases'][case]['id'],'turn':turn or 1,'native_run_id':report['remote_run_id'],'node_ids':sorted(ids),'source_graph_matched':True})
        b.save()
    # Explicit encrypted reconnect once. No chat credentials or replays.
    prefix='/api/environments/'+b.env['id']+'/saved-login/'
    proposal=call('POST',prefix+'reconnect-plan',{})
    reconnect=call('POST',prefix+'reconnect',{'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True})
    require(reconnect['record']['state']=='succeeded' and b.workspace_verified,'Reconnect not proven')
    task=call('POST','/api/tasks',{'name':fixture['task_name'],'app_type':'advanced-chat','environment_id':b.env['id']});base='/api/tasks/'+task['id'];require(task['id']==b.owner,'New Task not bound')
    call('PATCH',base,{'expected_revision':task['revision'],'configuration':fixture['configuration'],'requirements':fixture['requirements']})
    call('PATCH',base+'/execution-limits',{'revision':fresh()['revision'],'policy_revision':0,'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None,'acknowledge_scope':True,'note':'仅本批12启动、两轮内部共14Service，原历史不清零；Dify费用估算不是硬封顶。'})
    before=None
    for version in ('original','modified'):
        b.version=version;cases=copy.deepcopy(fixture['cases'])
        if version=='modified':
            require(before is not None and len([r for r in fresh()['runs'] if r.get('kind')=='run'])==6,'Original six cases not complete')
            req=copy.deepcopy(fixture['requirements']);req['output']=req['output'].replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply'])
            call('PATCH',base,{'expected_revision':fresh()['revision'],'requirements':req})
            require(not fresh()['requirements_confirmed'] and not fresh()['configuration_confirmed'] and fresh()['plan_stale'],'Changes did not invalidate')
            cases[1]['expectation']['expected']=fixture['changed_no_hit_reply']
        post('/test-cases',cases=cases);review();post('/confirm',kind='requirements')
        if version=='original':
            preview=post('/after-sales-plan-preview',request_nonce=str(uuid4()),acknowledge_scope=True,**fixture['inputs'])
            require(digest(json.loads(preview['plan_text']))==digest(contract[version]['plan']),'Template source changed')
        # Explicit frozen manual plan, never claim model generation.
        post('/plan',plan=contract[version]['plan']);post('/confirm',kind='configuration');post('/build')
        require(fresh()['plan_source']=='manual' and not fresh().get('planning_runs'),'Unexpected model origin')
        b.phase=version+'_import';post('/import')
        b.phase=version+'_publish';proposal=post('/workflow-publication/prepare')
        publication=post('/workflow-publication/confirm',proposal_id=proposal['id'],review_token=proposal['review_token'],confirm_publish=True)
        require(publication['state']=='succeeded','Publication incomplete')
        b.phase=version+'_key';proposal=post('/runtime-key-creation/plan')
        key=post('/runtime-key-creation/confirm',proposal_id=proposal['id'],review_token=proposal['review_token'],confirm_create_and_bind=True)
        require(key['state']=='succeeded','Key not created')
        b.phase=version+'_cases'
        for index,case in enumerate(cases):
            b.case_index=index
            if mode=='stop_after_first' and version=='original' and index==1:raise RuntimeError('Synthetic explicit stop')
            result=post('/run',case_id=case['id']);record=result['runs'][-1]
            if record['status']=='success' and record['evaluation']['status']=='failed':capture_failed_turn(record)
            require(record['status']=='success' and record['evaluation']['status']=='passed','Business rule failed; no further dispatch')
            for turn in ((1,2) if case.get('followups') else (None,)):assert_diagnostic(record,turn)
        r=api.get(base+'/delivery-bundle',params={'revision':fresh()['revision']});require(r.status_code==200,'Delivery download failed')
        with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
            manifest=json.loads(archive.read('manifest.json'));require(manifest['task_id']==b.owner and manifest['app_id']==b.current,'Wrong delivery source')
            require(all(manifest[k] is False for k in ('business_verified','platform_checked','network_requested')),'Local flags altered')
            require(set(archive.namelist())==set(manifest['files'])|{'manifest.json'},'Unexpected bundle entries')
            for name,meta in manifest['files'].items():require(hashlib.sha256(archive.read(name)).hexdigest()==meta['sha256'],'Bundle digest mismatch')
        (output/(version+'.zip')).write_bytes(r.content)
        b.record.setdefault('deliveries',[]).append({'version':version,'task_id':b.owner,'revision':fresh()['revision'],'app_id':b.current,'sha256':hashlib.sha256(r.content).hexdigest()});b.save()
        if version=='original':before=copy.deepcopy(fresh())
    require(b.counts['run']==14 and len([r for r in fresh()['runs'] if r.get('kind')=='run'])==12 and len(b.apps)==2,'Full batch not complete')
    require(not fresh().get('planning_runs') and all(r['status']=='success' for r in fresh()['runs']),'Unfinished or model operation')
    b.record.update(state='passed',task_id=b.owner,final_revision=fresh()['revision'],business_acceptance_complete=False,model_autonomous_planning_verified=False)
