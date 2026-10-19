import asyncio
import copy
import pytest
import yaml
from fastapi import HTTPException
from test_api import client,approved,create_env
from test_parameter_extractor import plan as root_plan
from test_container_extractor import plan as body_plan,task as body_task
from test_iteration import batch_plan
from test_loop import loop_plan
from app import main
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.extraction_safety import require_native_success


def native(p,mode='workflow'):
    content,checked=compile_workflow_plan(body_task(p,mode));assert checked['valid'],checked
    return yaml.safe_load(content)


@pytest.mark.parametrize('owner,mode',[(o,m) for o in ('iteration','loop') for m in ('workflow','advanced-chat')])
def test_native_success_cut_accepts_current_guarded_body_graph(owner,mode):
    p,_,_=body_plan(owner,mode);root=native(p,mode);before=copy.deepcopy(root)
    require_native_success(root);assert root==before


def test_native_old_root_aggregation_and_failed_path_return_are_refused():
    root=native(root_plan());graph=root['workflow']['graph'];before=copy.deepcopy(root);require_native_success(root);assert root==before
    merge=next(n['data'] for n in graph['nodes'] if n['id']=='merge');merge['variables']=[['extract','order_no'],['failure','output']]
    with pytest.raises(ValueError,match='失败分支'):require_native_success(root)
    root=native(root_plan());next(e for e in root['workflow']['graph']['edges'] if e['source']=='failure')['target']='success'
    with pytest.raises(ValueError,match='失败分支'):require_native_success(root)


@pytest.mark.parametrize('change',['condition','missing_exit','cross_scope'])
def test_native_incomplete_success_evidence_is_not_guessed(change):
    root=native(root_plan());graph=root['workflow']['graph']
    if change=='condition':next(n['data'] for n in graph['nodes'] if n['id']=='check')['cases'][0]['conditions'][0]['value']='0'
    elif change=='missing_exit':graph['edges']=[e for e in graph['edges'] if not (e['source']=='check' and e['sourceHandle']=='ok')]
    else:next(n for n in graph['nodes'] if n['id']=='extract')['parentId']='unknown-parent'
    with pytest.raises(ValueError):require_native_success(root)


def test_native_non_business_status_does_not_require_success_path():
    root=native(root_plan());next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='merge')['variables']=[['extract','__is_success']]
    require_native_success(root)


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_static_body_failed_route_cannot_rejoin_success_business_node(owner):
    p,parent,_=body_plan(owner);next(e for e in parent['config']['edges'] if e['source']=='failure')['target']='success'
    checked=validate_plan(body_task(p),p)
    assert not checked['valid'] and any('失败路径' in error for error in checked['errors'])


def outside_plan(owner='loop',guarded=True):
    p=root_plan();parent=copy.deepcopy(batch_plan()['nodes'][2] if owner=='iteration' else loop_plan()['nodes'][1])
    if owner=='iteration':
        parser=copy.deepcopy(batch_plan()['nodes'][1]);parser['config'].update(code='def main(query: str) -> dict:\n    return {"items": query.split()}\n',variables=[{'variable':'query','value_selector':['start','query']}]);p['nodes'].insert(1,parser)
        p['edges'][0]={'source':'start','target':'parse'};p['edges'].insert(1,{'source':'parse','target':'extract'})
        parent['config']['nodes'][0]['config']['variables'][0]['value_selector']=['extract','order_no']
    else:
        parent['config']['nodes'][0]['config']['variables'].append({'variable':'order_no','value_selector':['extract','order_no']});parent['config']['nodes'][0]['config']['code']='def main(count: float, order_no: str) -> dict:\n    return {"next_count": count + len(order_no)}\n'
    p['nodes'].insert(-1,parent)
    if guarded:
        next(e for e in p['edges'] if e['source']=='success')['target']=parent['id'];p['edges'].append({'source':parent['id'],'target':'merge'})
    else:
        next(e for e in p['edges'] if e['source']=='merge')['target']=parent['id'];p['edges'].append({'source':parent['id'],'target':'end'})
    return p,parent


@pytest.mark.parametrize('owner',['iteration','loop'])
def test_outer_extraction_must_guard_parent_not_be_lost_in_virtual_scope(owner):
    p,parent=outside_plan(owner);assert validate_plan(body_task(p),p)['valid'];root=native(p);require_native_success(root)
    bad,_=outside_plan(owner,False);checked=validate_plan(body_task(bad),bad)
    assert not checked['valid'] and any('正文外部提取参数' in e for e in checked['errors'])
    # Model an old native file bypassing the current static compiler.
    graph=root['workflow']['graph'];exit_id=parent['id'] if owner=='iteration' else parent['id']+'__loop_limit'
    next(e for e in graph['edges'] if e['source']=='success')['source']='merge'
    next(e for e in graph['edges'] if e['source']==exit_id and e['target']=='merge')['target']='end'
    next(e for e in graph['edges'] if e['source']=='merge' and e['target']=='end')['source']='success';next(e for e in graph['edges'] if e['source']=='success' and e['target']=='end')['target']='merge'
    with pytest.raises(ValueError,match='失败分支'):require_native_success(root)


@pytest.mark.parametrize('kind',['import','run'])
def test_old_artifact_gate_precedes_operation_pending_and_task_writes(client,kind):
    env=create_env(client);saved=approved(client,env_id=env['id']);tid=saved['id']
    saved=client.post(f'/api/tasks/{tid}/build',json={'revision':saved['revision']}).json()
    root=native(root_plan());next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='merge')['variables']=[['extract','order_no'],['failure','output']]
    main.artifact_path(saved).write_text(yaml.safe_dump(root,allow_unicode=True),encoding='utf-8');before=copy.deepcopy(main.get_task(tid));calls=[]
    async def operation(*args):calls.append(1);return {}
    with pytest.raises(HTTPException) as exc:asyncio.run(main.external_action(tid,saved['revision'],kind,operation,inputs={'query':'test'} if kind=='run' else None))
    assert exc.value.status_code==422 and '失败分支' in exc.value.detail
    assert calls==[] and main.get_task(tid)==before
