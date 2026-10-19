import copy
import pytest
import yaml
from test_api import client
from test_iteration import batch_plan
from test_loop import loop_plan
from test_preserved_loop import review
from app.workflow_plan import compile_workflow_plan,validate_plan
from app.dsl_roundtrip import validate_preserved,digest
from app.body_http import KEY,PREFIX


def plan(owner='iteration',mode='workflow',method='GET'):
    p=batch_plan() if owner=='iteration' else loop_plan();parent=next(n for n in p['nodes'] if n['type']==owner);cfg=parent['config']
    selector=parent['id']+'.'+('item' if owner=='iteration' else 'count')
    request={'id':'fetch','type':'http-request','config':{'method':method,'url':'https://httpbin.org/get?value={{#'+selector+'#}}','headers':'Accept:application/json','params':'','body':{'type':'none','data':[]},KEY:{'read_only':True,'reason':'逐项或逐轮只读查询技术接口，接口语义需核对；失败终止，不写入业务数据。'}}}
    final=cfg['nodes'][0]
    if owner=='iteration':
        final['config'].update(code='def main(body: str) -> dict:\n    return {"result": body}\n',variables=[{'variable':'body','value_selector':['fetch','body']}])
    else:
        final['config']['variables'].append({'variable':'status','value_selector':['fetch','status_code']});final['config']['code']='def main(count: float, status: float) -> dict:\n    return {"next_count": count + 1}\n'
    cfg['nodes']=[request,final]
    if mode=='advanced-chat':
        p['nodes'][0]['config']['variables']=[];p['nodes'][-1].update(type='answer',config={'answer':'请求处理完毕'})
        if owner=='iteration':p['nodes'][1]['config']['variables'][0]['value_selector']=['sys','query']
    return p,parent,request


def task(p,mode='workflow'):return {'app_type':mode,'workflow_plan':p,'configuration':{}}


@pytest.mark.parametrize('owner,mode,method',[(o,m,h) for o in ('iteration','loop') for m in ('workflow','advanced-chat') for h in ('GET','HEAD')])
def test_read_request_native_fields_scoped_templates_and_declaration_roundtrip(owner,mode,method):
    p,parent,request=plan(owner,mode,method);before=copy.deepcopy(p);content,checked=compile_workflow_plan(task(p,mode));assert checked['valid'],checked
    root=yaml.safe_load(content);raw=next(n for n in root['workflow']['graph']['nodes'] if n['id']=='fetch');data=raw['data']
    assert raw['parentId']==parent['id'] and data['url']==request['config']['url'] and data['method']==method.lower() and data['desc'].startswith(PREFIX)
    assert KEY not in data and p==before and data['retry_config']['retry_enabled'] is False
    checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked
    data['url']+='&manual=1';raw['position']['x']+=11;stamp=digest(root)
    checked=validate_preserved(root,loop_reviews=review(root) if owner=='loop' else None);assert checked['valid'],checked;assert digest(root)==stamp
    assert any('不是平台强制只读' in warning for warning in checked['warnings'])


@pytest.mark.parametrize('change',['write','no_policy','no_reason','false','unknown','missing_method','future_ref','leak','bad_retry'])
def test_no_implicit_read_only_or_changed_methods_or_cross_scope(change):
    p,parent,node=plan();cfg=node['config']
    if change=='write':cfg['method']='POST'
    elif change=='no_policy':cfg.pop(KEY)
    elif change=='no_reason':cfg[KEY]['reason']=''
    elif change=='false':cfg[KEY]['read_only']=False
    elif change=='unknown':cfg[KEY]['fee_cap']=1
    elif change=='missing_method':cfg.pop('method')
    elif change=='future_ref':cfg['url']='https://httpbin.org/get?value={{#clean.result#}}'
    elif change=='leak':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['fetch','body']
    else:cfg['retry_config']={'retry_enabled':True,'max_retries':0,'retry_interval':0}
    before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert not checked['valid'] and p==before


def test_secret_declarations_cover_internal_nodes_and_global_conflicts():
    p,parent,node=plan();node['config']['authentication']={'type':'bearer','secret_variable':'ORDER_READ_KEY','description':'只读订单接口认证，不包含值。','header':'Authorization'}
    content,checked=compile_workflow_plan(task(p));assert checked['valid'],checked;root=yaml.safe_load(content)
    declaration=root['workflow']['environment_variables'][0];assert declaration['name']=='ORDER_READ_KEY' and declaration['value']=='' and declaration['value_type']=='secret'
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='fetch');assert data['authorization']['config']['api_key']=='{{#env.ORDER_READ_KEY#}}'
    assert validate_preserved(root)['valid']
    duplicate=copy.deepcopy(node);duplicate['id']='fetch2';duplicate['config']['authentication']['description']='冲突的另一用途';parent['config']['nodes'].insert(1,duplicate)
    checked=validate_plan(task(p),p);assert not checked['valid'] and any('用途说明不同' in e for e in checked['errors'])


def test_actual_missing_or_replaced_read_declaration_is_not_assumed_or_repaired():
    p,_,_=plan();content,checked=compile_workflow_plan(task(p));assert checked['valid'];root=yaml.safe_load(content)
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='fetch');data['desc']='普通手改说明，并非明确重复读取声明'
    before=copy.deepcopy(root);assert not validate_preserved(root)['valid'] and root==before


def test_parallel_http_still_needs_declared_independence_and_concurrency():
    p,parent,_=plan();parent['config'].update(is_parallel=True,parallel_nums=2,parallel_safe=True,parallel_reason='各项只读请求独立；服务器限流和同时收费仍待核对。')
    assert validate_plan(task(p),p)['valid'];parent['config']['parallel_safe']=False
    assert not validate_plan(task(p),p)['valid']


def test_actual_read_reason_is_in_case_semantics_without_native_guarantee():
    from app.case_dsl_semantics import summary
    p,parent,node=plan();content,checked=compile_workflow_plan(task(p));assert checked['valid']
    value=summary(yaml.safe_load(content));assert value['repeated_http_reads']==[{'node_id':'fetch','parent_id':parent['id'],'policy':node['config'][KEY],'native_read_only_enforcement':False}]


def test_scope_nine_cannot_enable_or_resolve_expanded_read_declarations(client):
    from test_assistant_routing import setup,enable,state
    from app import main
    saved,p,light=setup(client);assert enable(client,saved,light,scope_version=9).status_code==409
    assert enable(client,saved,light).status_code==200
    old=main.routing.get(saved['id']);old['scope_version']=9;main.store.put('assistant_routing',saved['id'],old)
    current=state(client,saved);assert current['required_scope_version']==18 and current['blocker'] and '重复读取用途' in current['scope_note']


def test_actual_changed_write_method_or_duplicate_declaration_refused_before_dispatch():
    from app.body_http import require_native_reads
    p,_,_=plan();content,checked=compile_workflow_plan(task(p));assert checked['valid'];root=yaml.safe_load(content)
    data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='fetch');data['method']='post'
    with pytest.raises(ValueError,match='GET'):require_native_reads(root)
    data['method']='get';data['desc']=PREFIX+'{"read_only":false,"read_only":true,"reason":"重复字段不接受"}'
    with pytest.raises(ValueError,match='JSON'):require_native_reads(root)
