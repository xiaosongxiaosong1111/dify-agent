import sys,copy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app import main
from app.dataset_configuration_check import describe,DatasetRequest,selection_token
from test_api import client,create_env
from test_agent_environment_mapping import state,A,B


def row(ident=A,**patch):return {'id':ident,'name':'公开资料','document_count':3,'available_document_count':3,'indexing_technique':'economy',**patch}


@pytest.mark.parametrize('patch,status',[({},'counts_consistent'),({'document_count':0,'available_document_count':0},'empty'),({'available_document_count':0},'not_indexed'),({'available_document_count':2},'partial'),({'available_document_count':4},'unknown_metadata'),({'document_count':True},'unknown_metadata'),({'document_count':3.0},'unknown_metadata'),({'document_count':-1},'unknown_metadata'),({'available_document_count':9007199254740993},'unknown_metadata'),({'indexing_technique':'external'},'unknown_metadata'),({'indexing_technique':'high_quality'},'embedding_unresolved'),({'indexing_technique':'high_quality','embedding_model':'public-embed','embedding_model_provider':'public/provider'},'counts_consistent')])
def test_counts_and_known_index_fields_do_not_claim_retrieval(patch,status):
    original=row(**patch);before=copy.deepcopy(original);v=describe(A,original,complete=True)
    assert v['status']==status and not v['retrieval_tested'] and original==before
    assert v['metadata'].get('available_document_count')!=9007199254740993


def test_missing_complete_and_partial_catalog_are_different():
    assert describe(A,None,complete=True)['status']=='not_listed'
    assert describe(A,None,complete=False)['status']=='outside_window'


def install(monkeypatch,pages,*,change=False,source='console'):
    calls=[]
    async def read(self,page,limit):
        calls.append((page,limit));assert limit==100
        if change:
            env=main.store.get('environment',self.env['id']);env['connection_revision']='changed';main.store.put('environment',env['id'],env)
        value=pages[page-1]
        if isinstance(value,Exception):raise value
        return copy.deepcopy(value)
    async def wrong(*args):pytest.fail('must not silently switch credential source or read model catalog')
    monkeypatch.setattr(main.DifyClient,'console_datasets',read if source=='console' else wrong)
    monkeypatch.setattr(main.DifyClient,'datasets',read if source=='service' else wrong)
    monkeypatch.setattr(main.DifyClient,'models',wrong)
    return calls


def request(client,env,**patch):
    return client.post(f"/api/environments/{env['id']}/dataset-configuration-check",json={'dataset_ids':[A],'source':'console','max_pages':3,'expected_connection_revision':env.get('connection_revision'),**patch})


def test_all_selected_found_first_page_stops_without_scanning_unrelated_pages(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[{'data':[row(),row(B,name='UNSELECTED-PRIVATE')],'has_more':True}]);before=state()
    r=request(client,env);assert r.status_code==200,r.text;v=r.json()
    assert calls==[(1,100)] and state()==before and 'UNSELECTED-PRIVATE' not in r.text
    assert v['status']=='known_metadata_consistent' and not v['catalog_complete'] and v['search_complete_for_selected']
    assert v['rows'][0]['counts_consistent'] and not v['retrieval_tested'] and not v['target_resources_verified'] and not v['platform_verified'] and not v['business_verified'] and not v['task_modified'] and v['model_calls']==0
    assert v['selection_token']==selection_token(DatasetRequest(dataset_ids=[A],source='console',max_pages=3))


def test_missing_id_after_page_limit_unknown_not_nonexistent(client,monkeypatch):
    env=create_env(client);ids=['c3333333-3333-4333-8333-333333333333','d4444444-4444-4444-8444-444444444444','e5555555-5555-4555-8555-555555555555']
    calls=install(monkeypatch,[{'data':[row(i)],'has_more':True} for i in ids]);before=state()
    r=request(client,env);assert r.status_code==200 and len(calls)==3 and state()==before
    v=r.json();assert v['rows'][0]['status']=='outside_window' and not v['search_complete_for_selected'] and not v['catalog_complete']


def test_complete_visible_catalog_not_found_does_not_say_deleted(client,monkeypatch):
    env=create_env(client);install(monkeypatch,[{'data':[],'has_more':False}]);r=request(client,env)
    assert r.status_code==200 and r.json()['catalog_complete'] and r.json()['search_complete_for_selected']
    assert r.json()['rows'][0]['status']=='not_listed' and '不推断已删除' in r.text


def test_explicit_service_source_and_403_never_use_console_fallback(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[main.DifyError('HTTP 403',http_status=403)],source='service');before=state()
    r=request(client,env,source='service');assert r.status_code==502 and '不自动扩大权限或换凭据' in r.text and calls==[(1,100)] and state()==before


@pytest.mark.parametrize('patch',[{'dataset_ids':[A,A]},{'dataset_ids':['private-invalid-id']},{'dataset_ids':[]},{'dataset_ids':[A]*101},{'max_pages':True},{'max_pages':4},{'source':'automatic'},{'expected_connection_revision':'stale'},{'extra':'private'}])
def test_invalid_scope_or_connection_does_not_read_or_write(client,monkeypatch,patch):
    env=create_env(client);calls=install(monkeypatch,[]);before=state();r=request(client,env,**patch)
    assert r.status_code in {409,422} and calls==[] and state()==before and 'private-invalid-id' not in r.text


def test_connection_changes_between_pages_never_mix_metadata(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[{'data':[row()],'has_more':True}],change=True)
    r=request(client,env);assert r.status_code==409 and len(calls)==1


def test_duplicate_selected_id_changed_across_pages_rejected(client,monkeypatch):
    env=create_env(client);install(monkeypatch,[{'data':[row()],'has_more':True},{'data':[row(document_count=4),row(B)],'has_more':False}]);before=state()
    r=request(client,env,dataset_ids=[A,B]);assert r.status_code==409 and state()==before


def test_no_pagination_progress_stops_without_auto_retry(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[{'data':[row(B)],'has_more':True},{'data':[row(B)],'has_more':True}]);before=state()
    r=request(client,env);assert r.status_code==502 and '没有新增ID' in r.text and len(calls)==2 and state()==before


def test_dropped_secret_fields_and_unsafe_counts_not_serialized_to_browser(client,monkeypatch):
    env=create_env(client);install(monkeypatch,[{'data':[row(available_document_count=9007199254740993,credentials='PRIVATE-CREDENTIAL')],'has_more':False}]);r=request(client,env)
    assert r.status_code==200 and 'PRIVATE-CREDENTIAL' not in r.text and '9007199254740993' not in r.text
    assert 'available_document_count' in r.json()['rows'][0]['unavailable_fields']


def test_later_read_failure_does_not_return_partial_success(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[{'data':[row(A)],'has_more':True},main.DifyError('Dify 请求超时。外部写入结果可能未知。')]);before=state()
    r=request(client,env,dataset_ids=[A,B]);assert r.status_code==502 and '未执行检索、索引或写资源' in r.text and 'rows' not in r.json() and len(calls)==2 and state()==before


def test_duplicate_transport_key_no_echo_and_no_reads(client,monkeypatch):
    env=create_env(client);calls=install(monkeypatch,[]);raw='{"dataset_ids":["private-invalid"],"dataset_ids":[]}'
    r=client.post(f"/api/environments/{env['id']}/dataset-configuration-check",content=raw,headers={'Content-Type':'application/json'})
    assert r.status_code==422 and 'private-invalid' not in r.text and calls==[]


@pytest.mark.parametrize('status',['empty','not_indexed','partial','embedding_unresolved','outside_window','not_listed','unknown_metadata'])
def test_observed_gap_has_explicit_alternatives_and_impacts_without_execution(status):
    from app.dataset_configuration_check import guidance
    value=guidance(status);assert len(value)==3
    assert all(set(v)=={'option','experience','cost','manual_work'} and all(isinstance(t,str) and t for t in v.values()) for v in value)
    assert value[-1]['option']=='保留为待验证草稿' and '不能算' in value[-1]['experience']
    assert '不会自动替换' in value[1]['manual_work']


def test_consistent_counts_do_not_add_unprompted_failure_remediation():
    from app.dataset_configuration_check import guidance
    assert guidance('counts_consistent')==[]
