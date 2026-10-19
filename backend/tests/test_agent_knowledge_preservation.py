import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,yaml
from app.agent_preservation import validate
from app.dsl_roundtrip import preview,parse,digest
from app.agent_plan import compile_agent_plan
from test_agent_plan import knowledge_task
from test_agent_preservation import record,soul
from test_api import client
from app import main
from test_dsl_roundtrip import capture,apply
from test_agent_plan import prepare


def example():return yaml.safe_load(compile_agent_plan(knowledge_task())[0])


def test_final_knowledge_names_topk_and_native_defaults_preserved_exactly():
    proposal=example();current=copy.deepcopy(proposal);row=soul(current)['knowledge']['sets'][0]
    row.update(id='manual_knowledge_id',name='人工政策库',description='只回答明确的公开政策')
    row['retrieval'].update(top_k=7,reranking_model=None,weights=None,model=None)
    row['metadata_filtering'].update(metadata_model_config=None,conditions=None)
    row['datasets'][0].update(name='显示名称',description=None)
    result=preview(record(proposal,current),yaml.safe_dump(proposal),4)
    assert result['validation']['valid'],result
    assert digest(parse(result['content'],'agent'))==digest(current)
    assert any('知识集' in warning for warning in result['validation']['warnings'])


def test_both_changed_knowledge_list_is_atomic_explicit_conflict():
    proposal=example();current=copy.deepcopy(proposal);generated=copy.deepcopy(proposal)
    soul(current)['knowledge']['sets'][0]['retrieval']['top_k']=6
    soul(generated)['knowledge']['sets'][0]['description']='本次新的用途说明'
    p=preview(record(proposal,current),yaml.safe_dump(generated),5)
    assert p['unresolved']==1 and p['conflicts'][0]['path'].endswith('/knowledge/sets')
    for pick in ('current','generated'):
        selected=preview(record(proposal,current),yaml.safe_dump(generated),5,{p['conflicts'][0]['path']:pick})
        assert selected['unresolved']==0 and selected['validation']['valid']


def test_resource_change_never_reuses_old_confirmed_knowledge():
    old=example();new=copy.deepcopy(old)
    soul(new)['knowledge']['sets'][0]['datasets']=[{'id':'new-actual-library'}]
    current=copy.deepcopy(old);soul(current)['knowledge']['sets'][0]['description']='人工用途'
    p=preview(record(old,current),yaml.safe_dump(new),6)
    assert p['unresolved']==1
    path=p['conflicts'][0]['path']
    assert not preview(record(old,current),yaml.safe_dump(new),6,{path:'current'})['validation']['valid']
    assert preview(record(old,current),yaml.safe_dump(new),6,{path:'generated'})['validation']['valid']


def test_knowledge_api_apply_and_build_preserve_confirmed_ids(client):
    task=prepare(client);task['configuration']['dataset_ids']=['confirmed-library']
    plan=knowledge_task()['agent_plan'];task['agent_plan']=plan;main.save_task(task)
    root=parse(main.compile_current(task)[0],'agent');soul(root)['knowledge']['sets'][0]['retrieval']['top_k']=9
    task=capture(client,task,root);response,p=apply(client,task);assert response.status_code==200,response.text
    task=response.json()
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{task['id']}/confirm",json={'revision':task['revision'],'kind':kind});assert response.status_code==200,response.text
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']});assert response.status_code==200,response.text
    result=parse(main.artifact_path(response.json()).read_text('utf-8'),'agent')
    assert digest(result)==digest(root) and not response.json()['dify_app_id']


@pytest.mark.parametrize('path,value',[
    (['query','value'],'固定检索词'),(['query','mode'],'user_query'),
    (['retrieval','score_threshold'],0),(['retrieval','reranking_enable'],True),
    (['retrieval','reranking_model'],{'provider':'other','model':'ranker'}),
    (['retrieval','model'],{'provider':'other','name':'router'}),
    (['retrieval','weights'],{}),(['metadata_filtering','conditions'],[]),
    (['metadata_filtering','metadata_model_config'],{'provider':'other'}),
    (['metadata_filtering','mode'],'automatic'),(['unknown'],None),
    (['datasets'],[{'id':'confirmed-library','unknown':None}]),
    (['datasets'],[{'id':'same-name-different-id','name':'政策资料'}]),
    (['datasets'],[{'id':'confirmed-library'},{'id':'confirmed-library'}]),
    (['datasets'],[{'id':False}]),(['description'],None),(['name'],' '),(['id'],' padded '),
],ids=[f'policy{i}' for i in range(18)])
def test_knowledge_unadapted_policy_stays_in_preview_but_cannot_apply(path,value):
    original=example();current=copy.deepcopy(original);row=soul(current)['knowledge']['sets'][0]
    for key in path[:-1]:row=row[key]
    row[path[-1]]=value;before=copy.deepcopy(current)
    p=preview(record(original,current),yaml.safe_dump(original),5)
    assert not p['validation']['valid'] and parse(p['content'],'agent')==before==current


def test_knowledge_duplicate_ids_and_folded_names_blocked():
    original=example()
    for same_id,same_name in [(True,False),(False,True)]:
        current=copy.deepcopy(original);rows=soul(current)['knowledge']['sets']
        rows[0]['name']='Policy';second=copy.deepcopy(rows[0])
        second['id']=rows[0]['id'] if same_id else 'other_id';second['name']='policy' if same_name else 'different'
        rows.append(second)
        assert not validate(current,original)['valid']
