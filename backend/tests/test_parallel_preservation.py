import copy
import pytest,yaml
from test_api import client
from test_dsl_roundtrip import prepared,capture
from test_preserved_iteration_branches import native
from app import main
from app.dsl_roundtrip import validate_preserved,digest,parse
from app.parallel_preservation import candidates


def parallel():
    root=native();node=next(n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='iteration')
    node['data'].update(is_parallel=True,parallel_nums=3);return root,node['id']


def review(root,nid):return {nid:{'root_token':digest(root),'acknowledge_independence':True,'reason':'每项仅用自身输入和上游只读值，无项间顺序依赖；代码、模板及模型没有写共享外部资源，接受并发模型调用及派发后不能即时取消的风险。'}}


def test_no_review_cannot_guess_parallel_independence():
    root,nid=parallel();before=copy.deepcopy(root);result=validate_preserved(root)
    assert not result['valid'] and '逐项独立性' in result['errors'][0] and root==before
    assert candidates(root)[0]['parallel_nums']==3


def test_explicit_exact_file_review_keeps_parallel_graph_model_layout_and_code():
    root,nid=parallel();root['workflow']['graph']['nodes'].reverse();root['workflow']['graph']['edges'].reverse();before=copy.deepcopy(root)
    result=validate_preserved(root,review(root,nid));assert result['valid'],result['errors']
    assert root==before and any('已派发项' in warning for warning in result['warnings'])


@pytest.mark.parametrize('field,value',[('acknowledge_independence',False),('acknowledge_independence',1),('reason',''),('reason','x'*2001),('root_token','old')])
def test_invalid_or_stale_declarations_refuse(field,value):
    root,nid=parallel();reviews=review(root,nid);reviews[nid][field]=value
    assert not validate_preserved(root,reviews)['valid']


@pytest.mark.parametrize('mutation',['code','layout','model','condition','count'])
def test_any_merged_file_change_requires_new_declaration(mutation):
    root,nid=parallel();reviews=review(root,nid);nodes=root['workflow']['graph']['nodes']
    if mutation=='code':next(n for n in nodes if n['data']['type']=='code')['data']['code']+='\n# 手工变更'
    elif mutation=='layout':nodes[0]['position']['x']+=1
    elif mutation=='model':nodes[0]['data']['manual_field']='current-model-change'
    elif mutation=='condition':next(n for n in nodes if n['data']['type']=='if-else')['data']['cases'][0]['conditions'][0]['comparison_operator']='empty'
    else:next(n for n in nodes if n['id']==nid)['data']['parallel_nums']=4
    result=validate_preserved(root,reviews);assert not result['valid'] and '文件已变化' in result['errors'][0]


def test_foreign_or_sequential_reviews_cannot_be_inactive():
    root,nid=parallel();reviews=review(root,nid);reviews['other']=reviews[nid]
    assert not validate_preserved(root,reviews)['valid']
    root= native();assert not validate_preserved(root,review(root,nid))['valid']


@pytest.mark.parametrize('count',[True,1,11,'3'])
def test_unsupported_actual_parallel_number_cannot_be_silently_replaced(count):
    root,nid=parallel();next(n for n in root['workflow']['graph']['nodes'] if n['id']==nid)['data']['parallel_nums']=count
    result=validate_preserved(root,review(root,nid));assert not result['valid'] and '并发数' in result['errors'][0]


def test_review_does_not_bypass_failure_continue_nested_or_memory():
    root,nid=parallel();next(n for n in root['workflow']['graph']['nodes'] if n['id']==nid)['data']['error_handle_mode']='continue-on-error'
    result=validate_preserved(root,review(root,nid));assert not result['valid'] and any('terminated' in e for e in result['errors'])


def test_preview_confirm_build_preserves_file_and_records_declared_review(client):
    t,_=prepared(client);root,nid=parallel();t=capture(client,t,root);url=f"/api/tasks/{t['id']}/dsl-merge"
    first=client.get(url).json();assert not first['validation']['valid'] and first['parallel_candidates'][0]['id']==nid
    reviews=review(parse(first['content'],'workflow'),nid)
    observed=client.post(url+'/preview',json={'revision':t['revision'],'parallel_reviews':reviews}).json();assert observed['validation']['valid'],observed
    body={'revision':t['revision'],'reference_id':observed['reference_id'],'merge_token':observed['merge_token'],'parallel_reviews':reviews}
    altered=copy.deepcopy(body);altered['parallel_reviews'][nid]['reason']='另一个未预览声明'
    assert client.post(url+'/apply',json=altered).status_code==409
    applied=client.post(url+'/apply',json=body);assert applied.status_code==200,applied.text;t=applied.json()
    assert t['dsl_overlay']['parallel_reviews']==reviews and not t['configuration_confirmed']
    for kind in ('requirements','configuration'):
        res=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert res.status_code==200,res.text;t=res.json()
    res=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert res.status_code==200,res.text
    actual=parse(main.artifact_path(res.json()).read_text(encoding='utf-8'),'workflow');assert actual==root
    assert actual['workflow']['graph']['nodes']==root['workflow']['graph']['nodes']
