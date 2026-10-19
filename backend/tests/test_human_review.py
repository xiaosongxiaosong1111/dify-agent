import copy,json,uuid
import pytest,yaml
from test_api import client,approved
from app import main
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.human_review import validate,HANDLES


def plan():
    nodes=[{'id':'start','type':'start','config':{'variables':[{'variable':'query','type':'paragraph','required':True,'max_length':10000}]}},{'id':'review','type':'human-input','config':{'form_content':'请审核：\n{{#start.query#}}','inputs':[],'user_actions':[{'id':'approve','title':'批准','button_style':'primary'},{'id':'reject','title':'拒绝','button_style':'default'}],'timeout':1,'timeout_unit':'hour','delivery_methods':[{'id':'22222222-2222-4222-8222-222222222222','type':'webapp','enabled':True,'config':{}}]}}]
    edges=[{'source':'start','target':'review'}]
    for handle,text in [('approve','已批准'),('reject','已拒绝'),('__timeout','节点等待超时')]:
        nid='result'+str(len(nodes));end=nid+'end'
        nodes += [{'id':nid,'type':'template-transform','config':{'template':text,'variables':[]}},{'id':end,'type':'end','config':{'outputs':[{'variable':'result','value_selector':[nid,'output']}]}}]
        edges += [{'source':'review','target':nid,'source_handle':handle},{'source':nid,'target':end}]
    return {'schema_version':1,'nodes':nodes,'edges':edges}


def task(p,mode='workflow'):return {'app_type':mode,'configuration':{},'workflow_plan':p}


def test_complete_review_branches_compile_native_and_preserve_exact_fields():
    p=plan();before=copy.deepcopy(p);content,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(content);data=root['workflow']['graph']['nodes'][1]['data']
    assert data['version']=='1' and all(data[k]==v for k,v in p['nodes'][1]['config'].items())
    assert {e['sourceHandle'] for e in root['workflow']['graph']['edges'] if e['source']=='review'}==HANDLES
    assert '暂不导入或运行' in root['app']['description'] and p==before
    data['desc']='人工修改说明';root['workflow']['graph']['nodes'][1]['position']['x']+=20;stamp=digest(root)
    assert validate_preserved(root)['valid'] and digest(root)==stamp


@pytest.mark.parametrize('field,value',[('inputs',[{'type':'paragraph','output_variable_name':'comment'}]),('timeout',True),('timeout',0),('timeout',73),('timeout_unit',{}),('form_content',''),('form_content','{{#$output.comment#}}'),('form_content','{{#start.query.extra#}}'),('form_content','{{#unfinished'),('delivery_methods',[]),('user_actions',[])])
def test_no_default_or_silent_omission_of_unadapted_form_fields(field,value):
    cfg=plan()['nodes'][1]['config'];cfg[field]=value;before=copy.deepcopy(cfg)
    assert validate(cfg,'workflow') and cfg==before


@pytest.mark.parametrize('handle',['approve','reject','__timeout'])
def test_all_actions_and_timeout_require_one_explicit_edge(handle):
    p=plan();p['edges']=[e for e in p['edges'] if e.get('source_handle')!=handle]
    result=validate_plan(task(p),p);assert not result['valid'] and any(handle in e for e in result['errors'])


def test_undeclared_default_edge_and_downstream_human_outputs_not_guessed():
    p=plan();p['edges'][1].pop('source_handle');assert not validate_plan(task(p),p)['valid']
    p=plan();p['nodes'][2]['config']={'template':'{{decision}}','variables':[{'variable':'decision','value_selector':['review','__action_id']}]}
    result=validate_plan(task(p),p);assert not result['valid'] and any('变量' in e for e in result['errors'])


def test_source_type_and_dominance_do_not_accept_sibling_review_data():
    p=plan();p['nodes'][1]['config']['form_content']='{{#result2.output#}}';assert not validate_plan(task(p),p)['valid']
    p=plan();p['nodes'][0]['config']['variables']=[{'variable':'query','type':'number','required':True,'max_length':10}];assert not validate_plan(task(p),p)['valid']


@pytest.mark.parametrize('patch',[{'type':'email'},{'enabled':False},{'id':'not-uuid'},{'config':{'private':'fake'}}])
def test_only_explicit_webapp_no_notifications_or_identity_defaults(patch):
    cfg=plan()['nodes'][1]['config'];cfg['delivery_methods'][0].update(patch);assert validate(cfg,'workflow')


def test_non_workflow_unrecognized_native_settings_reject_without_rewriting():
    p=plan();assert not validate_plan(task(p,'advanced-chat'),p)['valid']
    root=yaml.safe_load(compile_workflow_plan(task(p))[0]);root['workflow']['graph']['nodes'][1]['data']['unknown_delivery_behavior']=True
    assert not validate_preserved(root)['valid']


def test_real_import_run_gates_before_any_platform_request_and_task_change(client,monkeypatch):
    t=approved(client);t['workflow_plan']=plan();main.store.put('task',t['id'],t)
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    t=response.json();before=copy.deepcopy(main.get_task(t['id']))
    async def forbidden(*a,**kw):pytest.fail('人审尚未接入真实运行，不应派发')
    monkeypatch.setattr(main.DifyClient,'request',forbidden)
    for action in ('import','run'):
        response=client.post(f"/api/tasks/{t['id']}/{action}",json={'revision':t['revision']});assert response.status_code==422 and '人工审核' in response.text
    assert main.get_task(t['id'])==before
    # Final preserved file, not just IR, must retain the same runtime block.
    row=main.get_task(t['id']);row['workflow_plan']=None;main.store.put('task',row['id'],row)
    response=client.post(f"/api/tasks/{t['id']}/import",json={'revision':t['revision']});assert response.status_code==422 and '人工审核' in response.text


def test_semantic_summary_includes_review_policy_and_old_light_scope_stale():
    from app.case_dsl_semantics import summary
    from app.assistant_routing import SCOPE_VERSION
    root=yaml.safe_load(compile_workflow_plan(task(plan()))[0]);value=summary(root)
    row=next(n for n in value['nodes'] if n['type']=='human-input')
    assert row['config']['timeout']==1 and row['config']['user_actions'][0]['id']=='approve' and SCOPE_VERSION==18


def test_old_scope_15_remains_blocked_until_explicit_new_scope_confirmation(client):
    from test_assistant_routing import setup,enable,state
    t,_,light=setup(client);assert enable(client,t,light).status_code==200
    row=main.store.get('assistant_routing',t['id']);row['scope_version']=15;main.store.put('assistant_routing',t['id'],row)
    current=state(client,t);assert current['required_scope_version']==18 and '人工审核' in current['blocker']
    assert enable(client,t,light,scope_version=15).status_code==409
    assert main.store.get('assistant_routing',t['id'])['scope_version']==15


def test_unknown_button_style_unhashable_does_not_crash_and_three_branches_stay_distinct():
    p=plan();p['nodes'][1]['config']['user_actions'][0]['button_style']={};assert validate(p['nodes'][1]['config'],'workflow')
    p=plan();p['edges'][3]['target']=p['edges'][1]['target'];assert not validate_plan(task(p),p)['valid']
