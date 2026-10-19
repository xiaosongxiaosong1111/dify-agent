import copy
import pytest
import yaml
from test_iteration import batch_plan
from test_loop import loop_plan
from test_preserved_loop import review
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest


def code(nid,variables,outputs,body):
    return {'id':nid,'type':'code','config':{'code_language':'python3','code':body,'variables':variables,'outputs':{name:{'type':kind,'children':None} for name,kind in outputs.items()}}}


def plan(owner='iteration',outside=False,explicit=False):
    p=batch_plan() if owner=='iteration' else loop_plan();container=next(n for n in p['nodes'] if n['type']==owner);cfg=container['config'];kind='array[string]' if owner=='iteration' else 'array[number]'
    source=code('values',[{'variable':'item','value_selector':['batch','item']}] if owner=='iteration' else [{'variable':'count','value_selector':['repeat','count']}],{'items':kind},'def main(item: str) -> dict:\n    return {"items": item.split()}\n' if owner=='iteration' else 'def main(count: float) -> dict:\n    return {"items": [count, count + 1]}\n')
    selection=['values','items']
    if outside:
        selection=['parse','items']
        if owner=='loop':
            external=code('parse',[],{'items':kind},'def main() -> dict:\n    return {"items": [1, 2]}\n');p['nodes'].insert(1,external);p['edges']=[{'source':'start','target':'parse'},{'source':'parse','target':'repeat'},{'source':'repeat','target':'end'}]
    operator={'id':'filtered','type':'list-operator','config':{'variable':selection,'input_type':kind,'filter_by':{'enabled':False,'conditions':[]},'order_by':{'enabled':True,'key':'','value':'asc'},'extract_by':{'enabled':False,'serial':'1'},'limit':{'enabled':True,'size':1}}}
    if owner=='iteration':
        final=code('render',[{'variable':'items','value_selector':['filtered','result']}],{'result':'string'},'import json\ndef main(items: list) -> dict:\n    return {"result": json.dumps(items)}\n');cfg['output_selector']=['render','result']
    else:
        final=cfg['nodes'][0];final['config']['variables'].append({'variable':'items','value_selector':['filtered','result']});final['config']['code']='def main(count: float, items: list) -> dict:\n    return {"next_count": count + len(items)}\n'
    cfg['nodes']=([source] if not outside else [])+[operator,final]
    if explicit:
        cfg['entry_node_id']=cfg['nodes'][0]['id'];cfg['edges']=[{'source':a['id'],'target':b['id']} for a,b in zip(cfg['nodes'],cfg['nodes'][1:])]
    return p,container,operator


def task(p):return {'app_type':'workflow','configuration':{},'workflow_plan':p}


@pytest.mark.parametrize('owner,outside,explicit',[(o,s,e) for o in ('iteration','loop') for s in (False,True) for e in (False,True)])
def test_internal_scalar_array_operations_generate_and_preserve_actual_scope(owner,outside,explicit):
    p,parent,node=plan(owner,outside,explicit);before=copy.deepcopy(p);content,result=compile_workflow_plan(task(p));assert result['valid'],result
    root=yaml.safe_load(content);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']==node['id']);assert raw['parentId']==parent['id'] and raw['data']['variable']==node['config']['variable']
    assert raw['data']['limit']==node['config']['limit'] and p==before
    references=review(root) if owner=='loop' else None;checked=validate_preserved(root,loop_reviews=references);assert checked['valid'],checked
    raw['data']['limit']['size']=0;raw['position']['x']+=15;stamp=digest(root)
    checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked;assert digest(root)==stamp


@pytest.mark.parametrize('owner,change',[('iteration','mismatch'),('loop','mismatch'),('iteration','future_source'),('loop','future_source'),('iteration','leak'),('loop','leak'),('iteration','array_terminal'),('loop','unknown_field')])
def test_internal_list_does_not_relax_types_scope_or_scalar_terminal(owner,change):
    p,parent,node=plan(owner);cfg=parent['config']
    if change=='mismatch':node['config']['input_type']='array[boolean]'
    elif change=='future_source':node['config']['variable']=[cfg['nodes'][-1]['id'],'result' if owner=='iteration' else 'next_count']
    elif change=='leak':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['filtered','result']
    elif change=='array_terminal':cfg['nodes'].pop();cfg['output_selector']=['filtered','result']
    else:node['config']['skip_errors']=True
    checked=validate_plan(task(p),p);assert not checked['valid'] and checked['errors']


def test_parallel_list_operations_still_require_independence_and_finite_count():
    p,parent,_=plan();parent['config'].update(is_parallel=True,parallel_nums=3,parallel_safe=True,parallel_reason='本项产生数组后独立筛选和文字输出，不读共享状态。')
    assert validate_plan(task(p),p)['valid'];parent['config']['parallel_safe']=False
    assert not validate_plan(task(p),p)['valid']
