"""Normal product API journey for the approved autonomous dual-version Chatflow batch.

The worker owns model/HTTP/budget gates, root-review receipts, credential reuse and dynamic
plan compilation. This module only drives normal product endpoints; it never writes a fixed
contract, edits a model graph, repairs a model response or decrypts credentials.
"""
import asyncio,copy,hashlib,io,json,zipfile
from pathlib import Path
from uuid import UUID
from common import digest,require

DOC_LIMIT=2;SEGMENT_LIMIT=20


def run(api, h, b, fixture, contract, output, mode='success'):
    output = Path(output)

    def call(method,path,body=None,allowed=(200,201),params=None):
        require(not b.halted,'Batch stopped')
        r=api.request(method,path,json=body,params=params) if body is not None else api.request(method,path,params=params)
        require(r.status_code in allowed,'Product API refused '+path+' status '+str(r.status_code));return r.json()
    def fresh():return h.get_task(b.owner)
    def post(path,**body):return call('POST',base+path,{'revision':fresh()['revision'],**body})
    def norm(value):
        try:return str(UUID(value))
        except (ValueError,TypeError,AttributeError):return None
    def begin(stage):b.phase=stage;b.begin_model(stage);stats['model_calls']+=1
    def known_models():
        entries=call('GET',base+'/budget')['entries']
        require(len(entries)<=6 and len(entries)==stats['model_calls'],'Unexpected model call count')
        require(all(e.get('status')=='settled' and e.get('cost_basis')=='reported_usage' and e.get('call_status')=='returned' and e.get('charged_usd') is not None for e in entries),'Unknown or unsettled model usage')
        return entries

    def review_intake():
        task=fresh();state=call('GET',base+'/intake')
        answers={q['id']:task['requirements'].get(q['id'],task['requirements']['rules']) for q in state['standard']}
        post('/intake/manual',context_token=state['context_token'],answers=answers,acknowledge_review=True,actor='agent_delegated',actor_note='根代理按本批委托实际核对当前需求、模型原文及完整候选后正常手工采纳；非人类签收或业务已验证。')
        post('/confirm',kind='requirements')
    def capture_failed_turn(run):
        require('failure_capture' not in b.record,'Failure report already attempted')
        turns=(run.get('result') or {}).get('turns') or [];failed=[t for t in turns if (t.get('evaluation') or {}).get('status')=='failed']
        require(not turns or len(failed)==1,'Failure turn ambiguous');turn=failed[0]['index'] if failed else None
        result=(failed[0].get('result') if failed else run.get('result')) or {};before=b.counts['reads']
        b.record['failure_capture']={'state':'requested','case_id':(run.get('test_case') or {}).get('id'),'turn':turn,'reports_attempted':1,'management_reads':0};b.save()
        try:
            b.begin_failure(result.get('message_id'),result.get('conversation_id'))
            report=post('/runs/'+run['id']+'/diagnose',read_remote=True,**({'turn_index':turn} if turn else {}))
            b.record['failure_capture'].update(state='captured' if report.get('trace_state')=='read' and (report.get('source_graph') or {}).get('matched') else 'unavailable',native_run_id=report.get('remote_run_id'),node_ids=sorted(n['node_id'] for n in report.get('nodes',[])),remote_status=report.get('remote_status'),source_graph_matched=(report.get('source_graph') or {}).get('matched',False))
        finally:
            b.record['failure_capture']['management_reads']=b.counts['reads']-before;b.halted=True;b.save()
        require(b.record['failure_capture']['management_reads']<=4,'Failure diagnostic cap exceeded')
    def assert_diagnostic(run,turn,expectations,app,revision):
        report=post('/runs/'+run['id']+'/diagnose',read_remote=True,**({'turn_index':turn} if turn else {}));stats['diagnostics']+=1
        require(report.get('trace_state')=='read' and report.get('truncated') is False and (report.get('source_graph') or {}).get('matched') is True and report.get('remote_status')=='succeeded','Incomplete/mismatched native trace')
        require(report.get('snapshot_matches_current') is True and report.get('current_source') is True and report.get('app_id')==app and report.get('source_revision')==revision and report.get('environment_id')==fresh().get('environment_id'),'Diagnostic source is not this App/revision/environment')
        if turn:
            steps=[t for t in (run.get('result') or {}).get('turns',[]) if t.get('index')==turn];require(len(steps)==1 and isinstance(steps[0].get('result'),dict),'Saved turn missing');saved=steps[0]['result']
        else:saved=run.get('result');require(isinstance(saved,dict),'Saved result missing')
        native=norm(report.get('remote_run_id'));resolution=report.get('remote_id_resolution');saved_message=norm(saved.get('message_id') or saved.get('id'))
        if resolution:require(saved_message is not None and norm(resolution.get('message_id'))==saved_message and norm(resolution.get('conversation_id'))==norm(saved.get('conversation_id')) and norm(resolution.get('workflow_run_id'))==native,'Message/conversation/native identity mismatch')
        else:require(native is not None and native==norm(saved.get('workflow_run_id')),'Native run identity missing')
        case_id=(run.get('test_case') or {}).get('id');require(case_id in expectations and str(turn or 1) in expectations[case_id],'No dynamic trace expectation')
        expected=expectations[case_id][str(turn or 1)];ids={n['node_id'] for n in report['nodes']};statuses={n['node_id']:n['status'] for n in report['nodes']}
        require(set(expected['must'])<=ids and not set(expected['must_not'])&ids,'Required/forbidden node presence mismatch')
        require(all(statuses.get(m)=='succeeded' for m in expected['must']),'Required node did not succeed')
        b.record.setdefault('traces',[]).append({'version':version,'case_id':case_id,'turn':turn or 1,'native_run_id':report['remote_run_id'],'node_ids':sorted(ids),'source_graph_matched':True});b.save()
    def run_cases(cases,expectations,app):
        require(isinstance(expectations,dict) and expectations,'Dynamic trace expectations required')
        revision=fresh()['revision']
        require(not [r for r in fresh()['runs'] if r.get('kind')=='run' and r.get('revision')==revision],'Version must start at 0/6')
        for index,case in enumerate(cases):
            b.case_index=index;result=post('/run',case_id=case['id']);run=result['runs'][-1]
            stats['starts']+=1;stats['services']+=1+len(case.get('followups') or [])
            if run.get('status')=='success' and (run.get('evaluation') or {}).get('status')=='failed':capture_failed_turn(run)
            require(run.get('status')=='success' and (run.get('evaluation') or {}).get('status')=='passed','Business rule failed; no further dispatch')
            require(run.get('app_id')==app and run.get('revision')==revision and run.get('environment_id')==fresh().get('environment_id'),'Run source mismatch')
            for turn in ((1,2) if case.get('followups') else (None,)):assert_diagnostic(run,turn,expectations,app,revision)
        passed=[r for r in fresh()['runs'] if r.get('kind')=='run' and r.get('revision')==revision and r.get('status')=='success' and (r.get('evaluation') or {}).get('status')=='passed']
        require(len(passed)==6,'Version must finish 6/6')
    def export_bundle(label,app,candidate):
        revision=fresh()['revision'];r=api.request('GET',base+'/delivery-bundle',params={'revision':revision})
        require(r.status_code==200,'Delivery download failed')
        with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            require(manifest.get('task_id')==b.owner and manifest.get('app_id')==app and manifest.get('revision')==revision and manifest.get('environment_id')==fresh().get('environment_id'),'Wrong delivery source')
            require(all(manifest.get(k) is False for k in ('business_verified','platform_checked','network_requested')),'Local flags altered')
            require(set(archive.namelist())==set(manifest['files'])|{'manifest.json'},'Unexpected bundle entries')
            for name,meta in manifest['files'].items():
                raw=archive.read(name);require(hashlib.sha256(raw).hexdigest()==meta['sha256'] and len(raw)==meta['bytes'],'Bundle digest mismatch')
        require(digest(fresh().get('workflow_plan'))==digest(candidate),'Bundle plan differs from reviewed candidate')
        (output/(label+'.zip')).write_bytes(r.content);stats['bundles']+=1
        b.record.setdefault('deliveries',[]).append({'version':label,'task_id':b.owner,'revision':revision,'app_id':app,'zip_sha256':hashlib.sha256(r.content).hexdigest(),'files':{n:m['sha256'] for n,m in manifest['files'].items()}});b.save()
    def replace_literals(value,old,new):
        if isinstance(value,dict):return {k:replace_literals(v,old,new) for k,v in value.items()}
        if isinstance(value,list):return [replace_literals(v,old,new) for v in value]
        return value.replace(old,new) if isinstance(value,str) else value
    def literal_change(original,candidate):
        require(digest(candidate)==digest(replace_literals(copy.deepcopy(original),old_reply,new_reply)),'Modified candidate differs beyond the fixed literal replacement')
        require(digest(candidate)!=digest(original),'Modified candidate must change the fixed no-answer literal')
        llm=terminal=False
        for node in original['nodes']:
            text=json.dumps(node.get('config',{}),ensure_ascii=False,sort_keys=True)
            if old_reply in text:
                llm=llm or node.get('type')=='llm';terminal=terminal or node.get('type') in {'template-transform','answer'}
        require(llm and terminal,'Both the terminal fallback and the LLM prompt must change')
    def resources(label):
        b.version=label;b.phase=label+'_import';post('/import');app=fresh().get('dify_app_id')
        require(app and app not in stats['apps'],'Unique new App required');stats['apps'].append(app)
        b.phase=label+'_publish';proposal=post('/workflow-publication/prepare')
        publication=post('/workflow-publication/confirm',proposal_id=proposal['id'],review_token=proposal['review_token'],confirm_publish=True)
        require(publication['state']=='succeeded','Publication incomplete');stats['publishes']+=1
        b.phase=label+'_key';proposal=post('/runtime-key-creation/plan')
        key=post('/runtime-key-creation/confirm',proposal_id=proposal['id'],review_token=proposal['review_token'],confirm_create_and_bind=True)
        require(key['state']=='succeeded','Key not created');stats['keys']+=1;return app
    def adopt(version,receipt,candidate):
        post('/confirm',kind='configuration');post('/build');t=fresh()
        require(digest(t['workflow_plan'])==digest(candidate),'Adopted graph changed')
        entry=b.register_plan(h,t,version,receipt);contract[version]=entry
        require(digest(entry['plan'])==digest(candidate)==digest(t['workflow_plan']),'Registered plan differs from the saved candidate')
        b.record.setdefault('plans',{})[version]={'model_candidate_sha256':digest(candidate),'saved_sha256':digest(t['workflow_plan']),'registered_sha256':digest(entry['plan']),'plan_source':t.get('plan_source')};b.save()
        return t
    def capture_history():
        t=fresh();artifact=copy.deepcopy(t['artifact']);path=h.artifact_path(t);raw=path.read_bytes()
        require(artifact.get('sha256')==hashlib.sha256(raw).hexdigest(),'Original artifact digest mismatch at capture')
        return {'runs':copy.deepcopy(t['runs']),'versions':copy.deepcopy(t['versions']),'requirements':copy.deepcopy(t['requirements']),'plan':copy.deepcopy(t['workflow_plan']),'artifact':artifact,'path':str(path),'artifact_sha256':hashlib.sha256(raw).hexdigest()}
    def verify_history(snap):
        t=fresh()
        require(t['runs'][:len(snap['runs'])]==snap['runs'],'Original runs prefix changed')
        require(t['versions'][:len(snap['versions'])]==snap['versions'],'Original versions prefix changed')
        last=t['versions'][len(snap['versions'])-1]
        require(digest(last['requirements'])==digest(snap['requirements']) and digest(last['workflow_plan'])==digest(snap['plan']),'Original requirements/graph history changed')
        require(digest(contract['original']['plan'])==digest(snap['plan']),'Registered original graph changed')
        require(hashlib.sha256(Path(snap['path']).read_bytes()).hexdigest()==snap['artifact_sha256']==snap['artifact'].get('sha256'),'Original artifact bytes changed')
        b.record.setdefault('history',{}).update(runs=len(snap['runs']),versions=len(snap['versions']),requirements_sha256=digest(snap['requirements']),plan_sha256=digest(snap['plan']),artifact_sha256=snap['artifact_sha256']);b.save()

    stats={'model_calls':0,'apps':[],'publishes':0,'keys':0,'starts':0,'services':0,'diagnostics':0,'bundles':0,'reviews':[]}
    old_reply=fixture['inputs']['no_hit_reply'];new_reply=fixture['changed_no_hit_reply']
    # One explicit encrypted reconnect; the workspace must be proven before any read.
    prefix='/api/environments/'+b.env['id']+'/saved-login/';proposal=call('POST',prefix+'reconnect-plan',{})
    reconnect=call('POST',prefix+'reconnect',{'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True})
    require(reconnect['record']['state']=='succeeded' and b.workspace_verified,'Reconnect not proven')
    # FAQ evidence read through the normal console adapter; no canned reply may stand in.
    b.phase='faq_read';env=h.store.get('environment',b.env['id']);dataset=fixture['configuration']['dataset_ids'][0]
    faq_case=next(c for c in fixture['cases'] if c['id']=='faq-hit');words=[w for w in faq_case['expectation']['expected'] if isinstance(w,str)]
    require(words,'Current faq-hit expectation missing')
    async def read_faq():
        client=h.DifyClient(env,h.store)
        meta=await client.request('GET','/console/api/datasets/'+dataset,credential='console_token')
        docs=await client.request('GET','/console/api/datasets/'+dataset+'/documents',credential='console_token',params={'page':1,'limit':DOC_LIMIT})
        require(isinstance(docs,dict) and isinstance(docs.get('data'),list) and docs['data'] and docs.get('has_more') is False,'FAQ documents truncated or empty')
        rows=[]
        for doc in docs['data'][:DOC_LIMIT]:
            page=await client.request('GET','/console/api/datasets/'+dataset+'/documents/'+str(doc['id'])+'/segments',credential='console_token',params={'page':1,'limit':SEGMENT_LIMIT})
            require(isinstance(page,dict) and isinstance(page.get('data'),list) and page['data'] and page.get('has_more') is False,'FAQ segments truncated or empty')
            for item in page['data']:
                require(isinstance(item.get('content'),str) and item['content'].strip(),'Empty FAQ segment')
                rows.append({'document_id':doc['id'],'segment_id':item.get('id'),'content':item['content']})
        return meta,rows
    meta,segments=asyncio.run(read_faq());text='\n'.join(row['content'] for row in segments)
    require(all(word in text for word in words),'FAQ segments do not contain current expectation')
    receipt=b.wait_review('faq_read',{'source':'console_api' if mode=='live' else 'synthetic_transport','dataset_id':dataset,'dataset_metadata_sha256':digest({k:meta.get(k) for k in ('id','name','indexing_technique','document_count')}),'documents':sorted({row['document_id'] for row in segments}),'documents_read':len({row['document_id'] for row in segments}),'segments_read':len(segments),'segments':segments,'expected_words':words,'expected_words_present':True,'pagination_truncated':False,'offline_fixed_reply_used':False,'verification':'actual_public_segments_for_root_review'})
    require(receipt,'FAQ root review receipt missing');stats['reviews'].append('faq_read')

    # One new empty Chatflow Task; only the assistant provider before the first interview.
    task=call('POST','/api/tasks',{'name':fixture['task_name'],'app_type':'advanced-chat','environment_id':b.env['id']})
    require(task['id']==b.owner,'New Task not bound');b.record['task_id']=task['id'];b.save();base='/api/tasks/'+task['id']
    call('PATCH',base,{'expected_revision':task['revision'],'configuration':{'assistant_provider_id':fixture['configuration']['assistant_provider_id']}})
    budget=call('PATCH',base+'/budget',{'revision':fresh()['revision'],'policy_revision':0,'limit_usd':'0.600','acknowledge_change':True,'note':'本批唯一新任务模型累计配置价估算上限0.600 USD；不含旧账本，不是供应商账单硬限。'})
    require(budget['limit_usd']=='0.600' and not budget['entries'],'Explicit fresh budget ledger required')
    begin('first_interview')
    call('POST',base+'/messages',{'revision':fresh()['revision'],'content':fixture['vague_message'],'mode':'review','stream_response':False})
    known_models();t=fresh();review=(t.get('intake_review') or {}).get('review');last=t['messages'][-1]
    require(review and any(x['status']=='needs_input' for x in review['checks']) and 1<=len(review['questions'])<=3,'First vague interview must identify missing information')
    require(not t['requirements_confirmed'] and not t.get('workflow_plan') and not t.get('artifact'),'First interview must not build or confirm anything')
    require(isinstance(last.get('content'),str) and last.get('source')=='model' and not last.get('attachments') and not last.get('images'),'Text-only interview reply required')
    receipt=b.wait_review('first_interview',{'missing_items_identified':True,'nothing_built':True,'single_review_call':True})
    require(receipt,'First interview root review receipt missing');stats['reviews'].append('first_interview')
    # Current saved cases and current configuration, then the complete explicit requirements.
    post('/test-cases',cases=copy.deepcopy(fixture['cases']))
    call('PATCH',base,{'expected_revision':fresh()['revision'],'configuration':copy.deepcopy(fixture['configuration'])})
    explicit='按下列每个字段分别明确如下公开合成需求，不猜规则；本阶段仅返回待复核的说明与规划，不自行执行Dify或创建外部资源：\n'+'\n'.join(key+'：'+value for key,value in fixture['requirements'].items())
    require(not any(word in explicit for word in ('修改版','未来','两版','费用循环协议')),'Future-version wording must not be sent')
    begin('complete_interview')
    call('POST',base+'/messages',{'revision':fresh()['revision'],'content':explicit,'mode':'review','stream_response':False})
    known_models();t=fresh();state=call('GET',base+'/intake')
    require((t.get('intake_review') or {}).get('source')=='model' and state['can_confirm'] and not state['blockers'] and not t['requirements_confirmed'] and not t.get('workflow_plan'),'Completed interview must cover all current topics; do not repeat the same statement')
    receipt=b.wait_review('complete_interview',{'all_current_topics_complete':True,'can_confirm':True,'nothing_built':True,'root_must_compare_complete_meaning':True})
    require(receipt,'Complete interview root review receipt missing');stats['reviews'].append('complete_interview')
    post('/confirm',kind='requirements')

    # Original model plan, root review, real delegated intake review, dynamic compile.
    require(fresh().get('workflow_plan') is None,'Fresh planning must not start from an old graph')
    begin('original_plan');call('POST',base+'/plan/generate',{'revision':fresh()['revision']});known_models()
    t=fresh();op=t['planning_runs'][-1]
    require(op['status']=='succeeded' and len(op['attempts'])==1 and op['attempts'][0]['status']=='valid' and op['attempts'][0]['cost_basis']=='reported_usage','One valid known-usage model plan required')
    candidate=copy.deepcopy(t['workflow_plan'])
    require(isinstance(candidate,dict) and candidate.get('nodes') and candidate.get('edges') is not None,'Complete saved model plan required')
    receipt=b.wait_review('original_plan',{'model_original_candidate':True,'candidate_sha256':digest(candidate),'template_preview_used':False,'business_verified':False},candidate)
    require(receipt,'Original plan root review receipt missing');stats['reviews'].append('original_plan')
    state=call('GET',base+'/intake')
    if state['stale'] or not state['reviewed']:review_intake()
    require(call('GET',base+'/intake')['can_confirm'],'Current intake is not confirmable after planning')
    if fresh().get('plan_stale'):post('/plan',plan=candidate)
    require(not fresh().get('plan_stale'),'Original plan still stale after same-value save')
    t=adopt('original',receipt,candidate)
    # Original resources and six cases, all diagnostics from the dynamic contract.
    version='original';app=resources('original')
    b.phase='original_cases';run_cases(copy.deepcopy(fixture['cases']),receipt.get('trace_expectations'),app)
    export_bundle('original',app,candidate);original_history=capture_history()
    # Single natural-language change: replace only the two no-hit literals.
    require('original' in contract and stats['bundles']==1,'Original version not complete')
    begin('modified_interview')
    change='仅将当前版本两处无答案回复文字由“'+old_reply+'”改为“'+new_reply+'”，其余业务规则、订单模拟、检索和样例保持原样；请按当前任务更新需求。'
    call('POST',base+'/messages',{'revision':fresh()['revision'],'content':change,'mode':'review','stream_response':False})
    known_models();t=fresh()
    require((t.get('intake_review') or {}).get('source')=='model','Modified interview must be model reviewed')
    require(old_reply not in t['requirements']['output'] and new_reply in t['requirements']['output'],'Model requirements update must apply the stated reply change')
    require(t.get('workflow_plan') is not None and digest(t['workflow_plan'])==digest(contract['original']['plan']),'Model interview must not replace the original graph')
    receipt=b.wait_review('modified_interview',{'model_requirements_update':True,'changed_no_hit_reply':new_reply,'other_business_unchanged':True,'business_verified':False})
    require(receipt,'Modified interview root review receipt missing');stats['reviews'].append('modified_interview')
    cases=copy.deepcopy(fixture['cases'])
    require(cases[1]['id']=='faq-no-answer' and cases[1]['expectation']['mode']=='equals' and cases[1]['expectation']['expected']==old_reply,'Current no-answer case shape changed')
    cases[1]['expectation']['expected']=new_reply
    require(all(digest(cases[i])==digest(fixture['cases'][i]) for i in range(len(cases)) if i!=1),'Only the no-answer expectation may change')
    post('/test-cases',cases=cases);review_intake()

    # Modified model plan: only the paused replanning_review candidate with both literals changed.
    begin('modified_plan');call('POST',base+'/plan/generate',{'revision':fresh()['revision']},allowed=(200,422));known_models()
    t=fresh();op=t['planning_runs'][-1]
    require(op['status']=='paused' and op.get('stop_reason')=='replanning_review' and isinstance(op.get('last_candidate'),dict),'Only replanning_review with a saved candidate is allowed')
    require(digest(t.get('workflow_plan'))==digest(contract['original']['plan']),'Original formal plan must remain saved')
    candidate=copy.deepcopy(op['last_candidate'])
    literal_change(contract['original']['plan'],candidate)
    receipt=b.wait_review('modified_plan',{'candidate_is_strict_literal_change':True,'candidate_sha256':digest(candidate),'original_plan_sha256':digest(contract['original']['plan']),'business_verified':False},candidate)
    require(receipt,'Modified plan root review receipt missing');stats['reviews'].append('modified_plan')
    post('/plan',plan=candidate);review_intake()
    if fresh().get('plan_stale'):post('/plan',plan=candidate)
    require(not fresh().get('plan_stale'),'Modified plan still stale after same-value save')
    adopt('modified',receipt,candidate)
    version='modified';app=resources('modified')
    b.phase='modified_cases';run_cases(cases,receipt.get('trace_expectations'),app)
    export_bundle('modified',app,candidate)
    require(len(stats['apps'])==2 and stats['publishes']==2 and stats['keys']==2,'Two App/publication/Key operations required')
    require(stats['starts']==12 and stats['services']==14 and stats['diagnostics']==14 and stats['bundles']==2 and stats['model_calls']==5 and len(stats['reviews'])==6,'Full batch dispatch incomplete')
    verify_history(original_history)
    known_models();saved=fresh();runs=[r for r in saved['runs'] if r.get('kind')=='run']
    require(len(runs)==12 and all(r.get('status')=='success' for r in runs),'Twelve successful starts required')
    record=b.record
    record.update(state='passed',task_id=b.owner,final_revision=saved['revision'],mainline_autonomous_verified=(mode=='live'),business_acceptance_complete=False,human_signoff=False)
    record['public_summary']={'verification':'live_normal_product_api_root_reviewed' if mode=='live' else 'synthetic_protocol_only','model_calls':stats['model_calls'],'apps':len(stats['apps']),'publishes':stats['publishes'],'keys':stats['keys'],'starts':stats['starts'],'services':stats['services'],'diagnostics':stats['diagnostics'],'bundles':stats['bundles'],'original_plan_sha256':digest(contract['original']['plan']),'modified_plan_sha256':digest(contract['modified']['plan']),'business_acceptance_complete':False,'human_signoff':False}
    b.save()
    (output/'journey-report.json').write_text(json.dumps(record['public_summary'],ensure_ascii=False,indent=2),'utf-8')
    return record
