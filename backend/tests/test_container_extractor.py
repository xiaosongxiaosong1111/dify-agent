import copy
import pytest
import yaml
from test_iteration import batch_plan
from test_loop import loop_plan
from test_parameter_extractor import plan as extractor_plan
from test_preserved_loop import review
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.conversation import memory_configuration


def plan(owner='iteration',mode='workflow'):
    p=batch_plan() if owner=='iteration' else loop_plan();container=next(n for n in p['nodes'] if n['type']==owner);cfg=container['config'];example=extractor_plan();body=copy.deepcopy(example['nodes'][1:-1]);extract=body[0]
    if owner=='loop':
        p['nodes'][0]['config']['variables']=[{'variable':'query','type':'text-input','required':True}]
        body[2]={'id':'success','type':'code','config':{'code_language':'python3','code':'def main(count: float, order_no: str) -> dict:\n    return {"result": count + len(order_no)}\n','variables':[{'variable':'count','value_selector':['repeat','count']},{'variable':'order_no','value_selector':['extract','order_no']}],'outputs':{'result':{'type':'number','children':None}}}}
        body[3]={'id':'failure','type':'code','config':{'code_language':'python3','code':'def main() -> dict:\n    raise ValueError("明确失败：没有提取订单号")\n','variables':[],'outputs':{'result':{'type':'number','children':None}}}}
        body[4]['config'].update(variables=[['success','result'],['failure','result']],output_type='number');cfg['updates']=[{'variable':'count','value_selector':['merge','output']}]
    cfg.update(nodes=body,entry_node_id='extract',edges=copy.deepcopy(example['edges'][1:-1]))
    if owner=='iteration':cfg['output_selector']=['merge','output']
    extract['config']['query']=['batch','item'] if owner=='iteration' else ['start','query']
    if mode=='advanced-chat':
        p['nodes'][0]['config']['variables']=[];p['nodes'][-1].update(type='answer',config={'answer':'处理完毕'})
        if owner=='iteration':p['nodes'][1]['config']['variables'][0]['value_selector']=['sys','query']
        else:extract['config']['query']=['sys','query']
    return p,container,extract


def task(p,mode='workflow'):
    return {'app_type':mode,'workflow_plan':p,'configuration':{'dify_model_provider':'mock/provider','dify_model':'mock-model','conversation_memory':mode=='advanced-chat','memory_turns':3}}


@pytest.mark.parametrize('owner,mode',[(o,m) for o in ('iteration','loop') for m in ('workflow','advanced-chat')])
def test_container_extraction_keeps_success_gate_scoped_models_and_actual_rules(owner,mode):
    p,parent,node=plan(owner,mode);before=copy.deepcopy(p);content,result=compile_workflow_plan(task(p,mode));assert result['valid'],result
    root=yaml.safe_load(content);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='extract');data=raw['data']
    assert raw['parentId']==parent['id'] and data['query']==node['config']['query'] and 'memory' not in data and data['model']['name']=='mock-model'
    assert any(e['source']=='extract' and e['target']=='check' for e in root['workflow']['graph']['edges']) and p==before
    checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked
    data['parameters'][0]['description']='实际手改明确订单字段';data['instruction']='不得推测未提供信息';raw['position']['x']+=9;stamp=digest(root)
    checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked;assert digest(root)==stamp
    data['memory']=memory_configuration('advanced-chat',{'conversation_memory':True,'memory_turns':3})
    assert not validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None)['valid']


@pytest.mark.parametrize('owner,change',[(o,c) for o in ('iteration','loop') for c in ('missing_gate','failed_business','common_business','sequential','number_query')])
def test_extraction_never_uses_default_business_values_or_bypasses_internal_gates(owner,change):
    p,parent,node=plan(owner);cfg=parent['config']
    if change=='missing_gate':cfg['edges'][0]['target']='success'
    elif change=='failed_business':cfg['nodes'][3]['config']['variables']=[{'variable':'order_no','value_selector':['extract','order_no']}]
    elif change=='common_business':cfg['nodes'][4]['config']['variables']=[['extract','order_no'],['failure','output' if owner=='iteration' else 'result']]
    elif change=='sequential':cfg.pop('edges');cfg.pop('entry_node_id')
    else:node['config']['query']=[parent['id'],'index' if owner=='iteration' else 'count']
    checked=validate_plan(task(p),p);assert not checked['valid'] and checked['errors']


def test_parallel_extraction_still_requires_explicit_independence_and_count():
    p,parent,_=plan();parent['config'].update(is_parallel=True,parallel_nums=2,parallel_safe=True,parallel_reason='每项提取与成功检查独立，不共享状态，不产生接口副作用。')
    assert validate_plan(task(p),p)['valid'];parent['config']['parallel_safe']=False
    assert not validate_plan(task(p),p)['valid']


def test_root_aggregation_cannot_turn_native_failed_defaults_into_business_values():
    p=extractor_plan();p['nodes'][5]['config']['variables']=[['extract','order_no'],['failure','output']]
    checked=validate_plan(task(p),p)
    assert not checked['valid'] and any('未经成功分支保护' in error for error in checked['errors'])
