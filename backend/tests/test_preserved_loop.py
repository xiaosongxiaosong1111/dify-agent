import ast,copy
import pytest,yaml
from test_api import client
from test_loop import loop_plan,task,cfg
from test_dsl_roundtrip import prepared,capture
from app import main
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved,digest,parse
from app.preserved_loop import candidates


def native(plan=None):
    text,v=compile_workflow_plan(task(plan));assert v['valid'],v['errors'];return yaml.safe_load(text)


def review(root,**changes):
    return {'repeat':{'root_token':digest(root),'progress_variables':['count'],'no_progress_limit':2,'progress_reason':'已核对本技术计数进度、状态更新、入口／停止保护和最大轮数，非客户业务验收。','acknowledge_behavior':True,**changes}}


def parts(root):return root['workflow']['graph'],{n['id']:n for n in root['workflow']['graph']['nodes']}


def test_missing_review_keeps_full_loop_and_reports_precise_gate():
    root=native();before=copy.deepcopy(root);v=validate_preserved(root)
    assert not v['valid'] and '核对当前最终文件' in v['errors'][0] and root==before
    assert candidates(root)[0]['variables']==['count']


def test_generated_loop_dsl_is_accepted_by_own_safe_reader_without_shared_yaml_anchors():
    text,v=compile_workflow_plan(task());assert v['valid']
    root=parse(text,'workflow');assert root['workflow']['graph']['nodes']
    assert '&id' not in text and '*id' not in text


def test_explicit_review_preserves_body_code_layout_guards_and_order_without_execution():
    root=native();graph,nodes=parts(root);nodes['increment']['data']['code']='def main(count: float) -> dict:\n    return {"next_count": count + 2}\n';nodes['increment']['position']['x']+=77;graph['nodes'].reverse();graph['edges'].reverse();before=copy.deepcopy(root)
    v=validate_preserved(root,loop_reviews=review(root));assert v['valid'],v['errors']
    assert root==before and any('原保护代码AST' in w for w in v['warnings'])


def test_same_guard_ast_with_comments_or_whitespace_is_not_silently_rewritten():
    root=native();graph,nodes=parts(root);nodes['repeat__loop_input']['data']['code']+='\n# 人工说明，不改变AST\n'
    before=copy.deepcopy(root);assert validate_preserved(root,loop_reviews=review(root))['valid'];assert root==before


@pytest.mark.parametrize('change',['missing_input','missing_progress','missing_limit','start_id','update_version','update_operation','update_target','private_value','private_source','guard_language','guard_binding','guard_output','guard_code','guard_error_strategy','parent_error_strategy','body_memory','body_error_continue','body_unknown','nested','scope_id','scope_flag','cross_edge','bypass_guard','guard_other_input','skip_progress','cycle','extra_child','condition_without_guard','limit_declaration','progress_declaration'])
def test_protection_or_scope_changes_are_rejected_without_altering_source(change):
    root=native();graph,nodes=parts(root);r=review(root);d=nodes['repeat']['data'];body=nodes['increment'];up=nodes['repeat__loop_update']['data'];guard=nodes['repeat__loop_progress']['data']
    if change.startswith('missing_'):graph['nodes'].remove(nodes['repeat__loop_'+change[8:]])
    elif change=='start_id':d['start_node_id']='increment'
    elif change=='update_version':up['version']='1'
    elif change=='update_operation':up['items'][0]['operation']='add'
    elif change=='update_target':up['items'][0]['variable_selector']=['start','count']
    elif change=='private_value':d['loop_variables'][-1]['value']=9
    elif change=='private_source':up['items'][-1]['value']=['increment','next_count']
    elif change=='guard_language':guard['code_language']='javascript'
    elif change=='guard_binding':guard['variables'][-1]['value_selector']=['increment','next_count']
    elif change=='guard_output':guard['outputs']['stagnant_rounds']['type']='string'
    elif change=='guard_code':guard['code']=guard['code'].replace('stagnant + 1','0')
    elif change=='guard_error_strategy':guard['error_strategy']='default-value'
    elif change=='parent_error_strategy':d['error_strategy']='fail-branch'
    elif change=='body_memory':body['data']['memory']={}
    elif change=='body_error_continue':body['data']['error_strategy']='default-value'
    elif change=='body_unknown':body['data']['type']='http-request'
    elif change=='nested':nodes['repeat']['parentId']='unknown-container'
    elif change=='scope_id':body['data']['loop_id']='foreign'
    elif change=='scope_flag':body['data']['isInLoop']=False
    elif change=='cross_edge':next(e for e in graph['edges'] if e['source']=='increment')['target']='end'
    elif change=='bypass_guard':next(e for e in graph['edges'] if e['source']=='repeat')['target']='end'
    elif change=='guard_other_input':graph['edges'].append({'source':'start','target':'repeat__loop_limit'})
    elif change=='skip_progress':next(e for e in graph['edges'] if e['source']=='increment')['target']='repeat__loop_update'
    elif change=='cycle':next(e for e in graph['edges'] if e['source']=='increment')['target']='repeat__loop_input'
    elif change=='extra_child':extra=copy.deepcopy(body);extra['id']='extra';graph['nodes'].append(extra)
    elif change=='condition_without_guard':d['break_conditions'][0]['value']='10'
    elif change=='limit_declaration':r['repeat']['no_progress_limit']=3
    elif change=='progress_declaration':r['repeat']['progress_variables']=[]
    r['repeat']['root_token']=digest(root);before=copy.deepcopy(root);v=validate_preserved(root,loop_reviews=r)
    assert not v['valid'] and v['errors'] and root==before,change


@pytest.mark.parametrize('patch',[{'root_token':'old'},{'acknowledge_behavior':1},{'acknowledge_behavior':False},{'no_progress_limit':True},{'no_progress_limit':11},{'progress_reason':''},{'progress_variables':['count','count']},{'progress_variables':['loop_round']},{'extra':'unknown'}])
def test_stale_or_incomplete_current_file_declarations_refused(patch):
    root=native();assert not validate_preserved(root,loop_reviews=review(root,**patch))['valid']


def test_declared_initial_string_and_boolean_states_are_protected():
    p=loop_plan();c=cfg(p);c['loop_variables']=[{'label':'done','var_type':'boolean','value_type':'constant','value':False},{'label':'text','var_type':'string','value_type':'constant','value':'a'}];c['nodes'][0]['config']={'code_language':'python3','code':'def main(done: bool, text: str) -> dict:\n    return {"done": True, "text": text + "b"}\n','variables':[{'variable':'done','value_selector':['repeat','done']},{'variable':'text','value_selector':['repeat','text']}],'outputs':{'done':{'type':'boolean','children':None},'text':{'type':'string','children':None}}};c['updates']=[{'variable':'done','value_selector':['increment','done']},{'variable':'text','value_selector':['increment','text']}];c['break_conditions']=[{'variable_selector':['repeat','done'],'varType':'boolean','comparison_operator':'is','value':True}];c['progress_variables']=['text'];p['nodes'][-1]['config']['outputs']=[{'variable':'result','value_selector':['repeat','done']}]
    root=native(p);v=validate_preserved(root,loop_reviews=review(root,progress_variables=['text']));assert v['valid'],v['errors']


def test_actual_capture_preview_apply_confirm_build_preserve_root_and_policy(client):
    t,_=prepared(client);root=native();graph,nodes=parts(root);nodes['increment']['data']['code']='def main(count: float) -> dict:\n    return {"next_count": count + 2}\n';t=capture(client,t,root);url=f"/api/tasks/{t['id']}/dsl-merge";first=client.get(url).json();assert not first['validation']['valid'] and first['loop_candidates'][0]['id']=='repeat'
    reviews=review(parse(first['content'],'workflow'));p=client.post(url+'/preview',json={'revision':t['revision'],'loop_reviews':reviews}).json();assert p['validation']['valid'],p['validation']
    body={'revision':t['revision'],'reference_id':p['reference_id'],'merge_token':p['merge_token'],'loop_reviews':reviews}
    changed=copy.deepcopy(body);changed['loop_reviews']['repeat']['progress_reason']='未预览新理由';assert client.post(url+'/apply',json=changed).status_code==409
    response=client.post(url+'/apply',json=body);assert response.status_code==200,response.text;t=response.json();assert t['dsl_overlay']['loop_reviews']==reviews and not t['configuration_confirmed']
    for kind in ('requirements','configuration'):
        response=client.post(f"/api/tasks/{t['id']}/confirm",json={'revision':t['revision'],'kind':kind});assert response.status_code==200,response.text;t=response.json()
    response=client.post(f"/api/tasks/{t['id']}/build",json={'revision':t['revision']});assert response.status_code==200,response.text
    assert parse(main.artifact_path(response.json()).read_text(encoding='utf-8'),'workflow')==root
