"""Normal product API journey for the reused first case plus two reviewed graphs."""
import copy,hashlib,io,json,zipfile
from pathlib import Path
from uuid import UUID
from app.dsl_roundtrip import parse
from app.workflow_publication import core
from tool import digest,require
from reviewed_diagnostic_redaction import ScopedDiagnosticClient
import tool as _tool

def _native_artifact(h,task,expected):
    # The plan compiler emits no revision metadata, only DSL version/name/config/plan,
    # so the fresh native and built artifact must match the frozen native/core exactly.
    content,validation=h.compile_current(task)
    require(validation.get('valid') is True,'Fresh native compile invalid')
    root=parse(content,task['app_type'])
    require(root==expected['native'] and core(root['workflow'])==expected['core'],
            'Fresh native/core differs from frozen review')
    raw=Path(h.artifact_path(task)).read_text('utf-8')
    artifact=parse(raw,task['app_type'])
    require(artifact==expected['native'] and core(artifact['workflow'])==expected['core'],
            'Artifact native differs from frozen review')
    return True

def submit_intake(api,h,b,fixture,side):
    require(side in {'original','modified'},'Intake side must be original/modified')
    frozen=fixture.get('topic_answers')
    require(isinstance(frozen,dict) and set(frozen)=={'original','modified'},'Two-version topic answers required')
    answers=frozen.get(side)
    require(isinstance(answers,dict) and answers,'Frozen topic answers missing: '+side)
    require(all(isinstance(value,str) and value.strip() for value in answers.values()),'Frozen topic answers malformed: '+side)
    require(not b.halted,'Batch stopped')
    base='/api/tasks/'+b.owner
    r=api.request('GET',base+'/intake')
    require(r.status_code==200,'Intake read failed '+str(r.status_code))
    state=r.json();standard=state.get('standard')
    require(isinstance(standard,list) and standard,'Intake standard missing')
    ids=[row.get('id') for row in standard if isinstance(row,dict)]
    require(len(ids)==len(standard) and all(isinstance(item,str) and item for item in ids),'Intake standard malformed')
    require(len(ids)==len(set(ids)) and set(ids)==set(answers),'Intake standard differs from frozen '+side+' topic answers')
    token=state.get('context_token');require(isinstance(token,str) and token,'Intake context token missing')
    task=h.get_task(b.owner)
    body={'revision':task['revision'],'context_token':token,'answers':copy.deepcopy(answers),'acknowledge_review':True,
          'actor':'agent_delegated','actor_note':'根代理按冻结公开售后逐项核对当前标准主题；是代理受托复核，不是人类签收或新模型访谈。'}
    r=api.request('POST',base+'/intake/manual',json=body)
    require(r.status_code in (200,201),'Explicit topic answers refused '+str(r.status_code))
    return r.json()

def run(api,h,b,fixture,contract,output,scope=None,mode='success'):
    output=Path(output);stats={'apps':0,'reused':0,'publishes':0,'keys':0,'starts':0,'services':0,'diagnostics':0,'bundles':0};seen_apps=set()
    if scope is not None:api=ScopedDiagnosticClient(api,h.store,b)
    def call(method,path,body=None,allowed=(200,201)):
        require(not b.halted,'Batch stopped')
        r=api.request(method,path,json=body) if body is not None else api.request(method,path)
        require(r.status_code in allowed,'Product API refused '+path+' status '+str(r.status_code));return r.json()
    def fresh():return h.get_task(b.owner)
    base='/api/tasks/'+b.owner
    def post(path,**body):return call('POST',base+path,{'revision':fresh()['revision'],**body})
    def review(side):
        return submit_intake(api,h,b,fixture,side)
    def ensure_requirements(side):
        if not fresh().get('requirements_confirmed'):review(side);post('/confirm',kind='requirements')
    def ensure_config():
        if not fresh().get('configuration_confirmed'):post('/confirm',kind='configuration')
    def ensure_limits():
        state=h.store.get('execution_limits',b.owner)
        require(state is not None,'Existing execution policy required')
        require(state.get('max_started_runs')==12 and state.get('max_total_minutes')==45 and state.get('max_reported_cost_usd') is None,'Execution policy changed')
    def norm(value):
        try:
            return str(UUID(value))
        except (ValueError, TypeError, AttributeError):
            return None

    def capture_failed_turn(run_value):
        require('failure_capture' not in b.record, 'Failure report already attempted')
        turns = (run_value.get('result') or {}).get('turns') or []
        failed = [t for t in turns if (t.get('evaluation') or {}).get('status') == 'failed']
        require(not turns or len(failed) == 1, 'Failure turn ambiguous')
        turn = failed[0]['index'] if failed else None
        result = (failed[0].get('result') if failed else run_value.get('result')) or {}
        before = b.counts['reads']
        b.record['failure_capture'] = {'state': 'requested',
                                       'case_id': (run_value.get('test_case') or {}).get('id'),
                                       'turn': turn, 'reports_attempted': 1, 'management_reads': 0}
        b.save()
        try:
            b.begin_failure(result.get('message_id'), result.get('conversation_id'))
            report = post('/runs/' + run_value['id'] + '/diagnose', read_remote=True,
                          **({'turn_index': turn} if turn else {}))
            b.record['failure_capture'].update(
                state='captured' if report.get('trace_state') == 'read'
                and (report.get('source_graph') or {}).get('matched') else 'unavailable',
                native_run_id=report.get('remote_run_id'),
                node_ids=sorted(n['node_id'] for n in report.get('nodes', [])),
                remote_status=report.get('remote_status'),
                source_graph_matched=(report.get('source_graph') or {}).get('matched', False))
        finally:
            b.record['failure_capture']['management_reads'] = b.counts['reads'] - before
            b.halted = True
            b.save()
        require(b.record['failure_capture']['management_reads'] <= 4, 'Failure diagnostic cap exceeded')

    def assert_diagnostic(run_value, turn, expectations, app, revision):
        report = post('/runs/' + run_value['id'] + '/diagnose', read_remote=True,
                      **({'turn_index': turn} if turn else {}))
        stats['diagnostics'] += 1
        require(report.get('trace_state') == 'read' and report.get('truncated') is False
                and (report.get('source_graph') or {}).get('matched') is True
                and report.get('remote_status') == 'succeeded', 'Incomplete/mismatched native trace')
        require(report.get('snapshot_matches_current') is True and report.get('current_source') is True
                and report.get('app_id') == app and report.get('source_revision') == revision
                and report.get('environment_id') == fresh().get('environment_id'),
                'Diagnostic source is not this App/revision/environment')
        if turn:
            steps = [t for t in (run_value.get('result') or {}).get('turns', []) if t.get('index') == turn]
            require(len(steps) == 1 and isinstance(steps[0].get('result'), dict), 'Saved turn missing')
            saved = steps[0]['result']
        else:
            saved = run_value.get('result')
            require(isinstance(saved, dict), 'Saved result missing')
        native = norm(report.get('remote_run_id'))
        resolution = report.get('remote_id_resolution')
        saved_message = norm(saved.get('message_id') or saved.get('id'))
        if resolution:
            require(saved_message is not None
                    and norm(resolution.get('message_id')) == saved_message
                    and norm(resolution.get('conversation_id')) == norm(saved.get('conversation_id'))
                    and norm(resolution.get('workflow_run_id')) == native,
                    'Message/conversation/native identity mismatch')
        else:
            require(native is not None and native == norm(saved.get('workflow_run_id')),
                    'Native run identity missing')
        case_id = (run_value.get('test_case') or {}).get('id')
        require(case_id in expectations and str(turn or 1) in expectations[case_id],
                'No dynamic trace expectation')
        expected = expectations[case_id][str(turn or 1)]
        ids = {n['node_id'] for n in report['nodes']}
        statuses = {n['node_id']: n['status'] for n in report['nodes']}
        require(set(expected['must']) <= ids and not set(expected['must_not']) & ids,
                'Required/forbidden node presence mismatch')
        require(all(statuses.get(m) == 'succeeded' for m in expected['must']),
                'Required node did not succeed')
        groups = expected.get('any_of')
        if groups is not None:
            require(isinstance(groups, list) and groups
                    and all(isinstance(group, list) and group
                            and all(isinstance(node, str) and node for node in group)
                            for group in groups),
                    'Trace any_of malformed')
            require(any(set(group) <= ids and all(statuses.get(node) == 'succeeded' for node in group)
                        for group in groups), 'No allowed alternative terminal group succeeded')
        b.record.setdefault('traces', []).append({
            'version': b.version, 'case_id': case_id, 'turn': turn or 1,
            'native_run_id': report['remote_run_id'], 'node_ids': sorted(ids),
            'source_graph_matched': True})
        b.save()

    def run_cases(cases, expectations, app, start=0, expected_total=6):
        require(isinstance(expectations, dict) and expectations, 'Dynamic trace expectations required')
        b.cases = copy.deepcopy(cases)
        revision = fresh()['revision']
        prior=[r for r in fresh()['runs'] if r.get('kind') == 'run' and r.get('revision') == revision]
        require(len(prior)==start,'Version must start at the frozen prior count')
        for index, case in enumerate(cases):
            if index < start:continue
            b.case_index = index
            result = post('/run', case_id=case['id'])
            run_value = result['runs'][-1]
            stats['starts'] += 1
            stats['services'] += 1 + len(case.get('followups') or [])
            if run_value.get('status') == 'success' \
                    and (run_value.get('evaluation') or {}).get('status') == 'failed':
                capture_failed_turn(run_value)
            require(run_value.get('status') == 'success'
                    and (run_value.get('evaluation') or {}).get('status') == 'passed',
                    'Business rule failed; no further dispatch')
            require(run_value.get('app_id') == app and run_value.get('revision') == revision
                    and run_value.get('environment_id') == fresh().get('environment_id'),
                    'Run source mismatch')
            for turn in ((1, 2) if case.get('followups') else (None,)):
                assert_diagnostic(run_value, turn, expectations, app, revision)
        passed = [r for r in fresh()['runs'] if r.get('kind') == 'run'
                  and r.get('revision') == revision and r.get('status') == 'success'
                  and (r.get('evaluation') or {}).get('status') == 'passed']
        require(len(passed) == expected_total, 'Version must finish the frozen pass count')

    def export_bundle(label, app, candidate):
        revision = fresh()['revision']
        r = api.request('GET', base + '/delivery-bundle', params={'revision': revision})
        require(r.status_code == 200, 'Delivery download failed')
        with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            require(manifest.get('task_id') == b.owner and manifest.get('app_id') == app
                    and manifest.get('revision') == revision
                    and manifest.get('environment_id') == fresh().get('environment_id'),
                    'Wrong delivery source')
            require(all(manifest.get(k) is False for k in ('business_verified', 'platform_checked',
                                                           'network_requested')), 'Local flags altered')
            require(set(archive.namelist()) == set(manifest['files']) | {'manifest.json'},
                    'Unexpected bundle entries')
            for name, meta in manifest['files'].items():
                raw = archive.read(name)
                require(hashlib.sha256(raw).hexdigest() == meta['sha256'] and len(raw) == meta['bytes'],
                        'Bundle digest mismatch')
        require(digest(fresh().get('workflow_plan')) == digest(candidate),
                'Bundle plan differs from reviewed candidate')
        (output / (label + '.zip')).write_bytes(r.content)
        stats['bundles'] += 1
        b.record.setdefault('deliveries', []).append({
            'version': label, 'task_id': b.owner, 'revision': revision, 'app_id': app,
            'zip_sha256': hashlib.sha256(r.content).hexdigest(),
            'files': {n: m['sha256'] for n, m in manifest['files'].items()}})
        b.save()

    def resources(label):
        b.version = label
        b.phase = label + '_import'
        post('/import')
        app = fresh().get('dify_app_id')
        require(app and app not in seen_apps, 'Unique new App required')
        seen_apps.add(app)
        stats['apps'] += 1
        b.phase = label + '_publish'
        proposal = post('/workflow-publication/prepare')
        publication = post('/workflow-publication/confirm', proposal_id=proposal['id'],
                           review_token=proposal['review_token'], confirm_publish=True)
        require(publication['state'] == 'succeeded', 'Publication incomplete')
        stats['publishes'] += 1
        b.phase = label + '_key'
        proposal = post('/runtime-key-creation/plan')
        key = post('/runtime-key-creation/confirm', proposal_id=proposal['id'],
                   review_token=proposal['review_token'], confirm_create_and_bind=True)
        require(key['state'] == 'succeeded', 'Key not created')
        stats['keys'] += 1
        return app

    def reuse_original():
        task = fresh()
        app = task.get('dify_app_id')
        require(app and app == _tool.EXISTING_APP_ID, 'Existing App binding changed')
        require(task.get('environment_id') == b.env['id'], 'Existing App environment mismatch')
        require(b.env.get('service_app_id') == app, 'Existing service App not bound')
        require(app in b.old_apps, 'Existing App not in frozen known set')
        key = h.store.secret(b.env['id'], 'service_api_key')
        require(isinstance(key, str) and key.startswith('app-'), 'Existing runtime key missing')
        runs = [r for r in task['runs'] if r.get('kind') == 'run']
        require(len(runs) == 1, 'Exactly one prior run required')
        first = runs[0]
        require(first.get('id') == _tool.EXISTING_FIRST_RUN and first.get('revision') == task['revision']
                and first.get('app_id') == app and first.get('environment_id') == b.env['id'],
                'Prior run source changed')
        require(first.get('status') == 'success' and (first.get('evaluation') or {}).get('status') == 'passed',
                'Prior run not passed')
        require(not first.get('diagnostics'), 'Prior diagnostics must be absent at start')
        result = first.get('result') or {}
        mid = norm(result.get('message_id') or result.get('id')); cid = norm(result.get('conversation_id'))
        require(mid and cid, 'Prior message/session missing')
        require(mid == norm(_tool.EXISTING_MESSAGE) and cid == norm(_tool.EXISTING_SESSION),
                'Prior message/session changed')
        b.version = 'original'; b.phase = 'original_cases'; b.current = app
        b.apps[app] = {'version': 'original', 'published': True, 'unpublished': False, 'publish_started': True,
                       'key_started': True, 'key': key, 'service_count': 1, 'last_cid': cid}
        b.messages[mid] = (app, cid); b.sessions.add(cid)
        stats['reused'] = 1
        return first, app, mid, cid

    def capture_history():
        task = fresh()
        artifact = copy.deepcopy(task['artifact'])
        path = h.artifact_path(task)
        raw = path.read_bytes()
        require(artifact.get('sha256') == hashlib.sha256(raw).hexdigest(),
                'Original artifact digest mismatch at capture')
        return {'runs': copy.deepcopy(task['runs']), 'versions': copy.deepcopy(task['versions']),
                'requirements': copy.deepcopy(task['requirements']),
                'plan': copy.deepcopy(task['workflow_plan']), 'artifact': artifact,
                'path': str(path), 'artifact_sha256': hashlib.sha256(raw).hexdigest()}

    def verify_history(snap):
        task = fresh()
        require(_tool.check_existing_runs_prefix(snap['runs'], task['runs'], _tool.EXISTING_FIRST_RUN),
                'Original runs prefix changed')
        require(task['versions'][:len(snap['versions'])] == snap['versions'],
                'Original versions prefix changed')
        last = task['versions'][len(snap['versions']) - 1]
        require(digest(last['requirements']) == digest(snap['requirements'])
                and digest(last['workflow_plan']) == digest(snap['plan']),
                'Original requirements/graph history changed')
        require(digest(contract['original']['plan']) == digest(snap['plan']),
                'Registered original graph changed')
        require(hashlib.sha256(Path(snap['path']).read_bytes()).hexdigest()
                == snap['artifact_sha256'] == snap['artifact'].get('sha256'),
                'Original artifact bytes changed')
        b.record.setdefault('history', {}).update(
            runs=len(snap['runs']), versions=len(snap['versions']),
            requirements_sha256=digest(snap['requirements']),
            plan_sha256=digest(snap['plan']), artifact_sha256=snap['artifact_sha256'])
        b.save()

    prefix='/api/environments/'+b.env['id']+'/saved-login/'
    proposal=call('POST',prefix+'reconnect-plan',{})
    reconnect=call('POST',prefix+'reconnect',{'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True})
    require(reconnect.get('record',{}).get('state')=='succeeded' and b.workspace_verified,'Reconnect/workspace not proven')
    ensure_limits()
    require(digest(fresh().get('workflow_plan'))==digest(contract['original']['plan']),'Task is not at reviewed r8 original')
    require(fresh().get('artifact',{}).get('revision')==fresh()['revision'] and fresh()['artifact']['validation'].get('valid') is True,'r8 artifact not current/static valid')
    require(fresh().get('test_cases')==fixture['cases'],'Original six cases changed')
    ensure_requirements('original');ensure_config()
    _native_artifact(h,fresh(),contract['original'])
    first,app,mid,cid=reuse_original()
    assert_diagnostic(first,None,contract['original']['trace_expectations'],app,first['revision'])
    b.source_verified=True;b.save()
    run_cases(fixture['cases'],contract['original']['trace_expectations'],app,start=1,expected_total=6);export_bundle('original',app,contract['original']['plan']);original=capture_history()
    # Explicit reviewed modification: only the declared text fields and the unique no-answer expectation.
    cases=copy.deepcopy(fixture['cases']);hits=[i for i,c in enumerate(cases)
        if (c.get('expectation') or {}).get('expected')==fixture['inputs']['no_hit_reply']]
    require(len(hits)==1,'Unique no-answer expectation required')
    cases[hits[0]]['expectation']['expected']=fixture['changed_no_hit_reply']
    requirements=copy.deepcopy(fixture['requirements'])
    require(requirements['output'].count(fixture['inputs']['no_hit_reply'])==1,'Requirements output sentence missing')
    requirements['output']=requirements['output'].replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply'])
    call('PATCH',base,{'expected_revision':fresh()['revision'],'requirements':requirements});post('/test-cases',cases=cases)
    require(not fresh()['requirements_confirmed'] and not fresh()['configuration_confirmed'] and fresh()['plan_stale'],'Modification did not invalidate')
    ensure_requirements('modified');post('/plan',plan=contract['modified']['plan']);ensure_requirements('modified');ensure_config();post('/build')
    require(fresh()['plan_source']=='manual','Unexpected model origin')
    require(digest(fresh()['workflow_plan'])==digest(contract['modified']['plan']),'Saved modified graph differs from frozen review')
    _native_artifact(h,fresh(),contract['modified'])
    b.version='modified';app=resources('modified');b.phase='modified_cases';b.cases=copy.deepcopy(cases)
    run_cases(cases,contract['modified']['trace_expectations'],app,start=0,expected_total=6);export_bundle('modified',app,contract['modified']['plan']);verify_history(original)
    require(b.counts['run']==13 and len([r for r in fresh()['runs'] if r.get('kind')=='run'])==12,'Run count incomplete')
    require(stats['apps']==1 and stats['publishes']==1 and stats['keys']==1 and stats['reused']==1,'One new App plus one reuse required')
    require(stats['starts']==11 and stats['services']==13 and stats['diagnostics']==14 and stats['bundles']==2,'Batch dispatch incomplete')
    require(b.counts['model']==0 and b.counts['login']<=1 and b.counts['reads']<=103,'Model/login/read bound exceeded')
    b.record.update(state='passed',task_id=b.owner,final_revision=fresh()['revision'],stats=stats,counts=dict(b.counts),business_acceptance_complete=False,model_autonomous_planning_verified=False)
    b.save();return b.record
