import copy,importlib,json,sys
from pathlib import Path
import httpx,pytest
SOURCE=Path(__file__).resolve().parents[2]/'tools/reviewed-chatflow401'

@pytest.fixture(autouse=True)
def isolated_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]));monkeypatch.syspath_prepend(str(SOURCE))
    for p in SOURCE.glob('*.py'):monkeypatch.delitem(sys.modules,p.stem,raising=False)
    global guard,entry,common
    guard=importlib.import_module('guard');entry=importlib.import_module('execute');common=importlib.import_module('common')
    yield
    for p in SOURCE.glob('*.py'):sys.modules.pop(p.stem,None)

def provider():return {'id':'public','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'output_per_million_usd':1.2}}
def messages():return [{'role':'system','content':'公开合成JSON规划'},{'role':'user','content':'明确公开需求'}]
def kwargs():return {'max_tokens':6000,'timeout':120,'json_mode':True}
def request(rows,url='https://api.deepseek.com/chat/completions',method='POST',key='PUBLIC_KEY',**fields):
    body={'model':'deepseek-flash','messages':rows,'max_tokens':6000,'stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},**fields}
    return httpx.Request(method,url,json=body,headers={'authorization':'Bearer '+key})
def first_call():
    b=guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None);b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs());b.admit(request(messages()));b.finish();return b
def operation():return {'settings':{'max_retries':1},'last_response_excerpt':'{"nodes": [}','response_truncated':False,'attempts':[{'number':1,'status':'invalid','cost_basis':'reported_usage','usage':{'prompt_tokens':100,'completion_tokens':20},'diagnostics':['返回内容不是可解析的 JSON 计划','JSON候选片段语法错误：第1行，第12列']} ]}
def repair_messages(op):return messages()+[{'role':'assistant','content':op['last_response_excerpt']},{'role':'user','content':'只修复 JSON 格式，或给已指出缺少冒号的 Python 语句头补一个冒号，返回完整JSON。'}]

def test_only_one_proven_json_repair_two_distinct_quotes_and_no_third_call():
    b=first_call();op=operation();rows=repair_messages(op)
    with pytest.raises(RuntimeError):b.prepare(provider(),'PUBLIC_KEY',rows,kwargs())
    b.preflight_json_repair(op);b.prepare(provider(),'PUBLIC_KEY',rows,kwargs());b.admit(request(rows));b.finish()
    assert b.calls=={'original':2} and set(b.quotes)=={'original:1','original:2'}
    assert b.record['json_repair_admission']['known_usage'] is True
    with pytest.raises(RuntimeError):b.prepare(provider(),'PUBLIC_KEY',rows,kwargs())
    with pytest.raises(RuntimeError):b.admit(request(rows))

@pytest.mark.parametrize('change',['valid','unknown_usage','missing_usage','wrong_diagnostic','duplicate_fields','depth','bad_detail','truncated','missing_raw','too_large','wrong_settings','extra_attempt'])
def test_second_call_cannot_be_authorized_for_other_conditions(change):
    b=first_call();op=operation();row=op['attempts'][0]
    if change=='valid':row['status']='valid'
    if change=='unknown_usage':row['cost_basis']='reserved_unknown_usage'
    if change=='missing_usage':row['usage']={}
    if change=='wrong_diagnostic':row['diagnostics']=['业务路径需确认']
    if change=='duplicate_fields':row['diagnostics'][1]='JSON候选对象含重复字段'
    if change=='depth':row['diagnostics'][1]='JSON候选超出60层'
    if change=='bad_detail':row['diagnostics'][1]={}
    if change=='truncated':op['response_truncated']=True
    if change=='missing_raw':op['last_response_excerpt']=''
    if change=='too_large':op['last_response_excerpt']='{'+'x'*17000
    if change=='wrong_settings':op['settings']['max_retries']=2
    if change=='extra_attempt':op['attempts'].append(copy.deepcopy(row))
    with pytest.raises(RuntimeError):b.preflight_json_repair(op)
    assert b.calls=={'original':1} and not b.repair_preflight

@pytest.mark.parametrize('change',['prefix','raw','role','instruction','missing'])
def test_second_message_chain_must_preserve_first_inputs_raw_response_and_normal_prompt(change):
    b=first_call();op=operation();b.preflight_json_repair(op);rows=repair_messages(op)
    if change=='prefix':rows[0]['content']='changed'
    if change=='raw':rows[-2]['content']='changed'
    if change=='role':rows[-2]['role']='user'
    if change=='instruction':rows[-1]['content']='请重新设计整个业务'
    if change=='missing':rows=rows[:1]
    with pytest.raises(RuntimeError):b.prepare(provider(),'PUBLIC_KEY',rows,kwargs())
    assert b.calls=={'original':1} and not b.armed

@pytest.mark.parametrize('change',['endpoint','method','key','tools','thinking','output','messages'])
def test_prepared_transport_is_exact_and_cannot_dispatch_other_work(change):
    b=guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None);b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs())
    rows=messages();url='https://api.deepseek.com/chat/completions';method='POST';key='PUBLIC_KEY';fields={}
    if change=='endpoint':url='http://127.0.0.1:8765/api/health'
    if change=='method':method='GET'
    if change=='key':key='OTHER'
    if change=='tools':fields['tools']=[]
    if change=='thinking':fields['thinking']={'type':'enabled'}
    if change=='output':fields['max_tokens']=6001
    if change=='messages':rows[0]['content']='changed after quote'
    with pytest.raises(RuntimeError):b.admit(request(rows,url,method,key,**fields))
    assert b.calls=={'original':0}

@pytest.mark.parametrize('change',['output','timeout','stream','images','wrong_model','oversize','expired'])
def test_wrong_call_parameters_or_quote_stop_before_arming(change):
    b=guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None);b.begin('original');p=provider();kw=kwargs();rows=messages()
    if change=='output':kw['max_tokens']=6001
    if change=='timeout':kw['timeout']=121
    if change=='stream':kw['stream']=True
    if change=='images':kw['allow_images']=True
    if change=='wrong_model':p['model']='other'
    if change=='oversize':rows[0]['content']='x'*300000
    if change=='expired':b.started-=1801
    with pytest.raises(RuntimeError):b.prepare(p,'PUBLIC_KEY',rows,kw)
    assert not b.armed and b.calls=={'original':0}

def packet(root):
    p={'batch_id':'reviewed-chatflow401','policy':copy.deepcopy(entry.POLICY),'limits':copy.deepcopy(common.LIMITS),'new_conservative_upper':copy.deepcopy(entry.UPPER),'runtime_build':'0.370.0-308fe1cec1c33471f170','backend_path':str(common.PROJECT/'.runtime/snapshots/0.370.0-308fe1cec1c33471f170/backend'),'provider_id':'9513f594-c256-46b7-882a-35d9871bf9d0','all_old_reservations_kept':True,'billing_hard_cap':False,'new_scope':copy.deepcopy(entry.NEW_SCOPE),'protected_isolated_391':{},'protected_isolated_394':{},'protected_isolated_399':{},'regrant_origin':copy.deepcopy(entry.ORIGIN)}
    for name in entry.FROZEN:(root/name).write_text('{}','utf-8')
    def save():
        (root/'plan.json').write_text(json.dumps(p),'utf-8');(root/'manifest.json').write_text(json.dumps({'batch_id':p['batch_id'],'files':{n:common.sha(root/n) for n in entry.FROZEN}}),'utf-8')
    save();return p,save

@pytest.mark.parametrize('field,value',[('policy',{'max_model_http':3}),('limits',{'model':3}),('new_conservative_upper',{}),('new_scope',{}),('protected_isolated_391',None),('protected_isolated_394',None),('protected_isolated_399',None),('regrant_origin',{}),('all_old_reservations_kept',False),('billing_hard_cap',True)])
def test_whole_new_scope_prices_and_old_data_bindings_cannot_change(tmp_path,field,value):
    p,save=packet(tmp_path);assert entry.validated(tmp_path)==p;p[field]=value;save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

def test_direct_new_scope_required_and_consumed_attempt_cannot_replay(tmp_path):
    p,_=packet(tmp_path)
    with pytest.raises(FileNotFoundError):entry.approved(tmp_path,p)
    entry.claim(tmp_path,{'state':'stopped'})
    with pytest.raises(FileExistsError):entry.claim(tmp_path,{'state':'admitted'})
    assert not (tmp_path/'worker-started.json').exists()

@pytest.mark.parametrize('field,value',[('revision',True),('source_sha256','other'),('actor','direct_human'),('decision','reject')])
def test_root_review_must_bind_current_candidate_and_normal_fix_source(field,value):
    source={'stage':'original','task_id':'public','revision':1,'source_sha256':'a'*64};receipt={**source,'actor':'agent_delegated','decision':'proceed','note':'实际核对完整候选、原响应及修复记录。'}
    assert guard.check_review(receipt,source,True)['semantic_reviewed'];receipt[field]=value
    with pytest.raises(RuntimeError):guard.check_review(receipt,source,True)


@pytest.mark.parametrize('field,value',[
    ('regranted_from','clarified-chatflow394'),('regranted_model_slots',2),
    ('regranted_estimate_usd','0.160'),('new_model_slots',0),
    ('new_estimate_usd','0'),('total_model_slots',3),('total_estimate_usd','0.240'),
])
def test_remaining_regrant_cannot_become_another_source_or_automatic_refund(tmp_path,field,value):
    p,save=packet(tmp_path);p['new_scope'][field]=value;save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)


def test_old399_approval_and_agent_delegation_cannot_approve_new_increment(tmp_path):
    p,_=packet(tmp_path)
    a={'authorization_source':'direct_human_reply','decision':'approve','batch_id':'bounded-chatflow399',
       'plan_sha256':common.sha(tmp_path/'plan.json'),'manifest_sha256':common.sha(tmp_path/'manifest.json'),
       'policy':entry.POLICY,'new_conservative_upper':entry.UPPER,'question_ref':'old399','reply':'approve'}
    (tmp_path/'approval.json').write_text(json.dumps(a),'utf-8')
    with pytest.raises(RuntimeError):entry.approved(tmp_path,p)
    a.update(batch_id=p['batch_id'],authorization_source='agent_delegated')
    (tmp_path/'approval.json').write_text(json.dumps(a),'utf-8')
    with pytest.raises(RuntimeError):entry.approved(tmp_path,p)


def test_actual399_data_is_checked_independently_of_production_and_snapshot_files(monkeypatch):
    monkeypatch.setattr(entry,'capture',lambda root: {'changed':True} if isinstance(root,Path) and root.as_posix().endswith('bounded-chatflow399/live-output/data') else {})
    class FakeSource:
        def list(self,kind):return [{}]*24
    monkeypatch.setattr(entry,'ReadOnly',lambda root:FakeSource() if root==common.PROJECT/'data' else root)
    p={'protected_data':{},'protected_isolated_391':{},'protected_isolated_394':{},'protected_isolated_399':{}}
    with pytest.raises(RuntimeError,match='399 isolated Task/settled changed'):entry.current(p)
