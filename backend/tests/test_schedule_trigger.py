import copy,json
import pytest,yaml
from test_api import client,approved
from app import main
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.schedule_trigger import validate,native


def plan(frequency='daily',visual=None):
    return {'schema_version':1,'nodes':[{'id':'timer','type':'trigger-schedule','config':{'mode':'visual','frequency':frequency,'visual_config':visual if visual is not None else {'time':'01:40 AM'},'timezone':'Asia/Shanghai'}},{'id':'fixed','type':'template-transform','config':{'template':'定时技术固定结果','variables':[]}},{'id':'end','type':'end','config':{'outputs':[{'variable':'result','value_selector':['fixed','output']}]}}],'edges':[{'source':'timer','target':'fixed'},{'source':'fixed','target':'end'}]}


def task(p,mode='workflow'):return {'app_type':mode,'configuration':{},'workflow_plan':p}


@pytest.mark.parametrize('frequency,visual',[('hourly',{'on_minute':0}),('daily',{'time':'12:00 AM'}),('daily',{'time':'12:00 PM'}),('weekly',{'time':'01:40 AM','weekdays':['mon','sun']}),('monthly',{'time':'11:59 PM','monthly_days':[1,31,'last']})])
def test_visual_schedule_compiles_and_preserves_exact_fields_without_dummy_start(frequency,visual):
    p=plan(frequency,visual);before=copy.deepcopy(p);text,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(text);nodes=root['workflow']['graph']['nodes'];timer=nodes[0]
    assert timer['data']['version']=='1' and timer['data']['visual_config']==visual
    assert not any(n['data']['type']=='start' for n in nodes)
    assert '尚未适配定时发布闭环' in root['app']['description'] and '试跑预算不限制后续费用' in root['app']['description']
    timer['position']['x']+=15;timer['data']['desc']='手动时区说明';stamp=digest(root)
    checked=validate_preserved(root);assert checked['valid'],checked
    assert digest(root)==stamp and p==before and any('持续调度' in w for w in result['warnings'])


@pytest.mark.parametrize('frequency,visual',[('hourly',{'on_minute':True}),('hourly',{'on_minute':'40'}),('hourly',{'on_minute':60}),('daily',{'time':'00:40 AM'}),('daily',{'time':'13:40 PM'}),('daily',{'time':'01:40'}),('daily',{'time':'01:40 AM','on_minute':40}),('weekly',{'time':'01:40 AM','weekdays':['mon','mon']}),('weekly',{'time':'01:40 AM','weekdays':[]}),('weekly',{'time':'01:40 AM','weekdays':[['mon']]}),('monthly',{'time':'01:40 AM','monthly_days':[True]}),('monthly',{'time':'01:40 AM','monthly_days':['1']}),('monthly',{'time':'01:40 AM','monthly_days':[0]}),('monthly',{'time':'01:40 AM','monthly_days':[32]}),('monthly',{'time':'01:40 AM','monthly_days':['last','last']}),('monthly',{'time':'01:40 AM','monthly_days':[{}]})])
def test_bad_visual_policy_never_guesses_or_rewrites_values(frequency,visual):
    p=plan(frequency,visual);before=copy.deepcopy(p);result=validate_plan(task(p),p)
    assert not result['valid'] and p==before


@pytest.mark.parametrize('fault',['timezone','mode','extra','missing','start_coexist','two_schedule','chatflow','fake_query'])
def test_schedule_entry_and_type_are_explicit(fault):
    p=plan();cfg=p['nodes'][0]['config'];mode='workflow'
    if fault=='timezone':cfg['timezone']='America/New_York'
    elif fault=='mode':cfg['mode']='cron'
    elif fault=='extra':cfg['silent_enable']=True
    elif fault=='missing':cfg.pop('timezone')
    elif fault in ('start_coexist','two_schedule'):
        p['nodes'].append({'id':'another','type':'start' if fault=='start_coexist' else 'trigger-schedule','config':{'variables':[]} if fault=='start_coexist' else copy.deepcopy(cfg)})
    elif fault=='chatflow':mode='advanced-chat';p['nodes'][-1].update(type='answer',config={'answer':'技术结果'})
    else:p['nodes'][1]['config']['variables']=[{'variable':'q','value_selector':['timer','query']}]
    assert not validate_plan(task(p,mode),p)['valid']


def test_native_unknown_execution_or_cron_behavior_is_not_dropped():
    text,_=compile_workflow_plan(task(plan()));root=yaml.safe_load(text)
    for key,value in [('retry_config',{'retry_enabled':True}),('cron_expression','* * * * *'),('version','2')]:
        changed=copy.deepcopy(root);changed['workflow']['graph']['nodes'][0]['data'][key]=value;stamp=digest(changed)
        assert not validate_preserved(changed)['valid'] and digest(changed)==stamp


def test_real_import_and_manual_run_are_blocked_before_dispatch_even_without_artifact(client,monkeypatch):
    t=approved(client);t['workflow_plan']=plan();main.store.put('task',t['id'],t)
    async def forbidden(*args,**kwargs):pytest.fail('定时真实资源操作未适配，不应派发')
    monkeypatch.setattr(main,'external_action',forbidden)
    for action,payload in [('import',{'revision':t['revision']}),('run',{'revision':t['revision'],'input':{}})]:
        response=client.post(f"/api/tasks/{t['id']}/{action}",json=payload)
        assert response.status_code==422 and '持续调度' in response.text
    assert main.get_task(t['id'])==t


def test_guard_checks_preserved_final_artifact_not_only_ir(client):
    from fastapi import HTTPException
    t=approved(client);t['workflow_plan']=plan();main.store.put('task',t['id'],t)
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    final=response.json();final['workflow_plan']=None
    with pytest.raises(HTTPException,match='持续调度'):main.require_manual_entry_runtime(final)
    from app.start_inputs import form_schema
    with pytest.raises(ValueError,match='没有普通start'):form_schema(yaml.safe_load(main.artifact_path(final).read_text(encoding='utf-8')))


def test_schedule_semantics_require_new_light_scope_before_sending_time_policy(client):
    from app.case_dsl_semantics import summary
    from test_assistant_routing import setup,enable,state
    text,_=compile_workflow_plan(task(plan()));root=yaml.safe_load(text)
    assert summary(root)['nodes'][0]['config']['visual_config']=={'time':'01:40 AM'}
    t,_,light=setup(client);assert enable(client,t,light).status_code==200
    old=main.routing.get(t['id']);old['scope_version']=14;main.store.put('assistant_routing',t['id'],old)
    value=state(client,t);assert value['required_scope_version']==18 and '定时入口' in value['blocker']
    assert enable(client,t,light,scope_version=14).status_code==409
    assert enable(client,t,light,scope_version=18).status_code==200


def test_capabilities_keep_schedule_root_only_and_workflow_only(client):
    workflow=client.get('/api/capabilities',params={'app_type':'workflow'}).json()
    chat=client.get('/api/capabilities',params={'app_type':'advanced-chat'}).json()
    assert 'trigger-schedule' in {n['type'] for n in workflow['root_nodes']}
    assert 'trigger-schedule' not in {n['type'] for n in chat['root_nodes']}
    assert all('trigger-schedule' not in {n['type'] for n in c['dag_nodes']} for c in workflow['containers'])
