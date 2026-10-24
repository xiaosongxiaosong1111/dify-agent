import copy
import pytest
from test_api import client, approved, forbid_api_external_calls
from test_run_comparison import sample
from app import main, run_comparison


def setup(client):
    task=approved(client);task['runs']=sample()['runs'];main.store.put('task',task['id'],task)
    value=client.get(f"/api/tasks/{task['id']}/run-comparison",params={'revision':task['revision'],'before_run_id':'old-run','after_run_id':'new-run'}).json()
    return task,{'revision':task['revision'],'before_run_id':'old-run','after_run_id':'new-run','snapshot_token':value['snapshot_token'],'export_token':value['export_token']}


def export(client,task,params):return client.get(f"/api/tasks/{task['id']}/run-comparison/report",params=params)


def test_report_is_observed_pair_and_readonly_no_decrypt(client,monkeypatch):
    task,params=setup(client);budget=main.store.get('task_budget',task['id'])
    def forbid(*args,**kwargs):pytest.fail('Report must not write or decrypt')
    monkeypatch.setattr(main.store,'put',forbid);monkeypatch.setattr(main.store,'secret',forbid)
    response=export(client,task,params);assert response.status_code==200,response.text
    assert response.headers['content-type'].startswith('text/markdown') and response.headers['cache-control']=='no-store'
    assert response.headers['x-sierra-comparison-token']==params['snapshot_token'] and response.headers['x-sierra-export-token']==params['export_token']
    assert '旧回复' in response.text and '新回复' in response.text and '不能归因' in response.text
    assert main.get_task(task['id'])==task and main.store.get('task_budget',task['id'])==budget


@pytest.mark.parametrize('field',['snapshot_token','export_token','revision','before_run_id'])
def test_wrong_observation_or_scope_refused(client,field):
    task,params=setup(client);params[field]=task['revision']+1 if field=='revision' else 'foreign' if field=='before_run_id' else '0'*64
    assert export(client,task,params).status_code in {404,409}


def test_hidden_sensitive_value_change_changes_export_binding_without_leaking(client):
    task,params=setup(client);task['runs'][0]['input']={'password':'HIDDEN-FIRST'};main.store.put('task',task['id'],task)
    first=run_comparison.compare(task,'old-run','new-run');params.update(snapshot_token=first['snapshot_token'],export_token=first['export_token'])
    task['runs'][0]['input']['password']='HIDDEN-SECOND';main.store.put('task',task['id'],task)
    second=run_comparison.compare(task,'old-run','new-run')
    assert first['snapshot_token']==second['snapshot_token'] and first['export_token']!=second['export_token']
    assert export(client,task,params).status_code==409
    params.update(export_token=second['export_token']);response=export(client,task,params)
    assert response.status_code==200 and 'HIDDEN' not in response.text and '未作比较' in response.text


@pytest.mark.parametrize('change',['input','error','current_app'])
def test_same_revision_saved_source_fact_changes_refuse_old_report(client,change):
    task,params=setup(client)
    if change=='input':task['runs'][1]['input']['query']='改后的问题'
    if change=='error':task['runs'][1]['error']='稍后保存的错误说明'
    if change=='current_app':task['dify_app_id']='other-current-app'
    main.store.put('task',task['id'],task)
    assert export(client,task,params).status_code==409


def test_json_text_cannot_close_its_markdown_fence():
    task=sample();task['runs'][0]['input']={'query':'```\n<script>example</script>\n```'}
    value=run_comparison.compare(task,'old-run','new-run');text=run_comparison.render_report(value)
    assert '````\n{' in text and '<script>example</script>' in text
    assert '不是平台实时证明或签名' in text


def test_unknown_and_missing_result_labels_not_upgraded():
    task=sample();task['runs'][1].update(status='unknown',result={})
    text=run_comparison.render_report(run_comparison.compare(task,'old-run','new-run'))
    assert '字段未完整保存' in text and '不能直接重试' in text and 'unknown' in text


def test_change_during_render_not_returned_as_mixed_report(client,monkeypatch):
    task,params=setup(client);original=run_comparison.render_report
    def mutate(value):
        text=original(value);current=main.get_task(task['id']);current['runs'][0]['error']='render期间更新';main.store.put('task',task['id'],current);return text
    monkeypatch.setattr(run_comparison,'render_report',mutate)
    assert export(client,task,params).status_code==409


def test_export_unmarkable_or_oversized_source_is_not_falsely_certified():
    task=sample();task['runs'][0]['ignored_blob']='x'*8000001
    value=run_comparison.compare(task,'old-run','new-run')
    assert value['export_token'] is None and value['snapshot_token']
