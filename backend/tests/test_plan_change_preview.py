import copy,json
import pytest
from test_api import client,approved,create,forbid_api_external_calls
from test_workflow_plan import base_plan
from app import main


def setup(client,plan=None,app_type='workflow'):
    task=create(client,app_type=app_type) if app_type=='agent' else approved(client);task['workflow_plan' if app_type!='agent' else 'agent_plan']=copy.deepcopy(plan)
    main.store.put('task',task['id'],task);return task


def preview(client,task,plan=None,**changes):
    return client.post(f"/api/tasks/{task['id']}/plan/change-preview",content=json.dumps({'revision':task['revision'],'plan_text':json.dumps(plan,ensure_ascii=False),**changes},ensure_ascii=True),headers={'Content-Type':'application/json'})


def test_same_changed_and_readonly_metadata_not_customer_values(client,monkeypatch):
    task=setup(client,base_plan());before=copy.deepcopy(main.store.get('task',task['id']));draft=copy.deepcopy(task['workflow_plan'])
    def forbidden(*a,**kw):pytest.fail('Preview must not decrypt, compile or save')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main,'store_plan',forbidden)
    same=preview(client,task,draft).json();assert same['content_changed'] is False and same['node_changes']['changed']==0
    draft['nodes'][1]['config']['system_prompt']='PRIVATE-PROMPT-MARKER'
    response=preview(client,task,draft);assert response.status_code==200,response.text
    result=response.json();assert result['content_changed'] and result['node_changes']['changed']==1
    assert '提示词' in result['node_changes']['details']['items'][0]['fields']
    assert 'PRIVATE-PROMPT-MARKER' not in response.text and main.store.get('task',task['id'])==before
    assert not result['task_modified'] and not result['network_requested'] and not result['plan_validated']


def test_node_add_remove_reorder_and_connection_changes(client):
    task=setup(client,base_plan());draft=copy.deepcopy(task['workflow_plan']);draft['nodes'][1]['id']='new-node-id';draft['nodes']=list(reversed(draft['nodes']));draft['edges']=[]
    result=preview(client,task,draft).json()['node_changes']
    assert result['added']==result['removed']==1 and result['moved']==2 and result['connections_changed'] and result['root_order_changed']


def test_container_scoped_node_identity_and_body_changes(client):
    saved={'nodes':[{'id':'body','type':'iteration','config':{'nodes':[{'id':'child','type':'code','config':{'code':'old'}}],'edges':[]}}, {'id':'other','type':'iteration','config':{'nodes':[{'id':'child','type':'code','config':{'code':'keep'}}],'edges':[]}}],'edges':[]}
    task=setup(client,saved);draft=copy.deepcopy(saved);draft['nodes'][0]['config']['nodes'][0]['config']['code']='new'
    result=preview(client,task,draft).json()['node_changes'];assert result['changed']==1
    item=result['details']['items'][0];assert item['current_path']==item['historical_path']==[1,1] and item['fields']==['代码或语言']


def test_exact_integer_and_json_type_comparison_not_javascript_rounding(client):
    plan={'nodes':[{'id':'one','type':'code','config':{'value':9007199254740993}}],'edges':[]};task=setup(client,plan)
    assert preview(client,task,plan).json()['content_changed'] is False
    changed=copy.deepcopy(plan);changed['nodes'][0]['config']['value']=9007199254740992
    assert preview(client,task,changed).json()['node_changes']['changed']==1
    plan['nodes'][0]['config']['value']=True;task=setup(client,plan);changed=copy.deepcopy(plan);changed['nodes'][0]['config']['value']=1
    assert preview(client,task,changed).json()['content_changed']


def test_detail_limit_no_partial_claim_and_duplicate_identity(client):
    task=setup(client,{'nodes':[],'edges':[]});draft={'nodes':[{'id':str(i),'type':'template-transform'} for i in range(33)],'edges':[]}
    result=preview(client,task,draft).json()['node_changes'];assert result['added']==33 and result['details']['total']==33 and len(result['details']['items'])==30 and result['details']['omitted']==3
    draft['nodes'][1]['id']='0';result=preview(client,task,draft).json()['node_changes'];assert result['available'] is False and 'details' not in result


def test_first_plan_agent_and_stale_plan_have_explicit_scope(client):
    task=setup(client);result=preview(client,task,base_plan()).json();assert not result['has_saved_plan'] and result['node_changes']['added']==3
    task=setup(client,{'instruction':'old'},'agent');result=preview(client,task,{'instruction':'new','PRIVATE-FIELD-MARKER':'PRIVATE-VALUE-MARKER'}).json()
    assert result['node_changes'] is None and result['other_field_changes']==1 and 'PRIVATE-' not in json.dumps(result)
    task=setup(client,base_plan());task['plan_stale']=True;main.store.put('task',task['id'],task)
    result=preview(client,task,base_plan()).json();assert result['saved_plan_stale'] and result['content_changed'] is False


@pytest.mark.parametrize('text',['{"nodes":[],"nodes":[]}','{"v":NaN}','[]','{bad','{"x":"\ud800"}','{"x":"'+'字'*700000+'"}'],ids=['duplicate','nonfinite','array','syntax','unicode','oversize'])
def test_bad_or_oversize_text_is_not_echoed_or_saved(client,text):
    task=setup(client,base_plan());before=main.store.get('task',task['id'])
    response=preview(client,task,plan_text=text);assert response.status_code==422 and main.store.get('task',task['id'])==before
    assert 'bad' not in response.text


@pytest.mark.parametrize('changes',[{'revision':True},{'revision':0},{'revision':'1'},{'plan_text':{}},{'extra':'PRIVATE-MARKER'}])
def test_strict_envelope_is_not_echoed(client,changes):
    task=setup(client);response=preview(client,task,{},**changes);assert response.status_code==422 and 'PRIVATE-MARKER' not in response.text


def test_stale_or_unknown_task_and_duplicate_envelope(client):
    task=setup(client,base_plan());assert preview(client,task,{},revision=task['revision']+1).status_code==409
    assert preview(client,{**task,'id':'missing'},{}).status_code==404
    response=client.post(f"/api/tasks/{task['id']}/plan/change-preview",content='{"revision":1,"revision":2,"plan_text":"{}"}',headers={'Content-Type':'application/json'});assert response.status_code==422
