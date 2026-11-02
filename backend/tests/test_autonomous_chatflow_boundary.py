"""Four-stage isolated approval, request and source boundaries; no live HTTP."""
import copy,importlib,json,sys
from pathlib import Path
import httpx,pytest

SOURCE=Path(__file__).resolve().parents[2]/'tools/autonomous-chatflow414'

@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SOURCE));monkeypatch.syspath_prepend(str(SOURCE.parents[1]/'backend'))
    for p in SOURCE.glob('*.py'):monkeypatch.delitem(sys.modules,p.stem,raising=False)
    global guard,entry,common
    guard=importlib.import_module('guard');entry=importlib.import_module('execute');common=importlib.import_module('common')
    yield
    for p in SOURCE.glob('*.py'):sys.modules.pop(p.stem,None)

def provider():return {'id':'public','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'output_per_million_usd':1.2}}
def messages():return [{'role':'user','content':'公开合成模糊售后需求'}]
def options():return {'max_tokens':6000,'timeout':120,'json_mode':True}
def gate():return guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None)
def request(body=None,url='https://api.deepseek.com/chat/completions',method='POST',key='PUBLIC_KEY'):
    return httpx.Request(method,url,json=body or {'model':'deepseek-flash','messages':messages(),'max_tokens':6000,'stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}},headers={'authorization':'Bearer '+key})
def call(b,stage):
    b.begin(stage);b.prepare(provider(),'PUBLIC_KEY',messages(),options());b.admit(request());b.finish()

def test_four_stages_require_each_previous_review_and_never_replay():
    b=gate()
    for stage in guard.STAGES:
        call(b,stage)
        with pytest.raises(RuntimeError):b.begin(stage)
        if stage!=guard.STAGES[-1]:
            with pytest.raises(RuntimeError):b.begin(guard.STAGES[guard.STAGES.index(stage)+1])
        b.record.setdefault('reviews',{})[stage]={'actor':'agent_delegated'}
    for stage in guard.STAGES:
        with pytest.raises(RuntimeError):b.begin(stage)
    assert list(b.calls.values())==[1,1,1,1]

@pytest.mark.parametrize('stage',['complete_interview','original','modified','repair','other'])
def test_cannot_skip_vague_interview(stage):
    with pytest.raises(RuntimeError):gate().begin(stage)

@pytest.mark.parametrize('change',['model','key','output','timeout','stream','images','price','oversize','expired','json'])
def test_invalid_quote_or_profile_never_arms(change):
    b=gate();b.begin('vague_interview');p=provider();k='PUBLIC_KEY';m=messages();kw=options()
    if change=='model':p['model']='other'
    if change=='key':k='OTHER'
    if change=='output':kw['max_tokens']=6001
    if change=='timeout':kw['timeout']=121
    if change=='stream':kw['stream']=True
    if change=='images':kw['allow_images']=True
    if change=='price':p['pricing']['input_per_million_usd']=5
    if change=='oversize':m[0]['content']='X'*400000
    if change=='expired':b.started-=3601
    if change=='json':kw['json_mode']=False
    with pytest.raises(RuntimeError):b.prepare(p,k,m,kw)
    assert sum(b.calls.values())==0 and not b.armed

@pytest.mark.parametrize('change',['dify','method','key','message','tools','thinking','output','model','stream','format'])
def test_only_prequoted_nonstreaming_model_http(change):
    b=gate();b.begin('vague_interview');b.prepare(provider(),'PUBLIC_KEY',messages(),options())
    body=json.loads(request().content);url='https://api.deepseek.com/chat/completions';method='POST';key='PUBLIC_KEY'
    if change=='dify':url='http://127.0.0.1:8765/api/tasks'
    if change=='method':method='GET'
    if change=='key':key='OTHER'
    if change=='message':body['messages'][0]['content']='Changed'
    if change=='tools':body['tools']=[]
    if change=='thinking':body['thinking']['type']='enabled'
    if change=='output':body['max_tokens']=6001
    if change=='model':body['model']='other'
    if change=='stream':body['stream']=True
    if change=='format':body['response_format']['type']='text'
    with pytest.raises(RuntimeError):b.admit(request(body,url,method,key))
    assert sum(b.calls.values())==0

def test_duplicate_transport_and_halted_phase_are_forbidden():
    b=gate();call(b,'vague_interview')
    with pytest.raises(RuntimeError):b.admit(request())
    b.record['reviews']={'vague_interview':{}};b.stop()
    with pytest.raises(RuntimeError):b.begin('complete_interview')
    assert sum(b.calls.values())==1

def packet(root):
    p={'batch_id':'autonomous-chatflow414','policy':copy.deepcopy(entry.POLICY),'limits':copy.deepcopy(entry.LIMITS),'new_conservative_upper':copy.deepcopy(entry.UPPER),'runtime_build':'0.376.0-57d49ddcad74036f8ec8','backend_path':str(common.PROJECT/'.runtime/snapshots/0.376.0-57d49ddcad74036f8ec8/backend'),'provider_id':'9513f594-c256-46b7-882a-35d9871bf9d0','all_old_reservations_kept':True,'billing_hard_cap':False,'new_model_slots':4,'regrant':None,'protected_isolated':{k:{} for k in entry.ISOLATED},'original_model_has_no_saved_graph':True,'full_business_accepted':False}
    for name in entry.FROZEN:(root/name).write_text('{}','utf-8')
    def save():
        (root/'plan.json').write_text(json.dumps(p),'utf-8')
        (root/'manifest.json').write_text(json.dumps({'batch_id':p['batch_id'],'files':{n:common.sha(root/n) for n in entry.FROZEN}}),'utf-8')
    save();return p,save

@pytest.mark.parametrize('field,value',[('policy',{}),('limits',{'model':5}),('new_conservative_upper',{}),('regrant',{'old_slot':1}),('new_model_slots',3),('protected_isolated',{}),('all_old_reservations_kept',False),('billing_hard_cap',True),('original_model_has_no_saved_graph',False),('full_business_accepted',True),('runtime_build','other'),('provider_id','other')])
def test_fresh_exact_scope_and_all_old_roots_required(tmp_path,field,value):
    p,save=packet(tmp_path);assert entry.validated(tmp_path)==p
    p[field]=value;save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

def approval(root,p):
    return {'batch_id':p['batch_id'],'authorization_source':'direct_human_reply','decision':'approve','plan_sha256':common.sha(root/'plan.json'),'manifest_sha256':common.sha(root/'manifest.json'),'policy':entry.POLICY,'new_conservative_upper':entry.UPPER,'new_model_slots':4,'question_ref':'public','reply':'允许新完整范围'}

@pytest.mark.parametrize('field,value',[('authorization_source','agent_delegated'),('plan_sha256','old'),('manifest_sha256','old'),('new_model_slots',3),('policy',{}),('new_conservative_upper',{}),('question_ref',''),('reply',''),('decision','reject')])
def test_new_direct_approval_binds_final_four_calls(tmp_path,field,value):
    p,_=packet(tmp_path);a=approval(tmp_path,p);(tmp_path/'approval.json').write_text(json.dumps(a),'utf-8');entry.approved(tmp_path,p)
    a[field]=value;(tmp_path/'approval.json').write_text(json.dumps(a),'utf-8')
    with pytest.raises(RuntimeError):entry.approved(tmp_path,p)

def test_no_approval_or_consumed_attempt_cannot_start(tmp_path):
    p,_=packet(tmp_path)
    with pytest.raises(FileNotFoundError):entry.approved(tmp_path,p)
    entry.claim(tmp_path,{'state':'stopped'})
    with pytest.raises(FileExistsError):entry.claim(tmp_path,{'state':'admitted'})
    assert not (tmp_path/'worker-started.json').exists()

def test_response_sources_cannot_change_after_freeze(tmp_path):
    packet(tmp_path);(tmp_path/'worker.py').write_text('changed','utf-8')
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

@pytest.mark.parametrize('field,value',[('revision',True),('source_sha256','other'),('task_id','other'),('stage','modified'),('actor','direct_human'),('decision','reject'),('note','')])
def test_actual_review_is_current_source_bound_not_human_signoff(field,value):
    source={'stage':'original','task_id':'public','revision':1,'source_sha256':'a'*64};receipt={**source,'actor':'agent_delegated','decision':'proceed','note':'根代理实际核完整候选，非人类签收。'}
    assert guard.check_review(receipt,source,True)['semantic_reviewed']
    receipt[field]=value
    with pytest.raises(RuntimeError):guard.check_review(receipt,source,True)

def test_literal_change_requires_both_llm_and_direct_fallback_and_preserves_other_fields():
    fixture={'inputs':{'no_hit_reply':'原文。'},'changed_no_hit_reply':'原文和商品型号。'}
    plan={'nodes':[{'id':'answer_model','type':'llm','config':{'system_prompt':'请回答；不足时：原文。','user_prompt':'{{context}}'}},{'id':'fallback','type':'template-transform','config':{'template':'原文。'}}],'edges':[{'source':'a','target':'b'}],'extra':'原文。'}
    changed=guard.changed_plan(plan,fixture)
    assert changed['nodes'][0]['config']['system_prompt']=='请回答；不足时：原文和商品型号。'
    assert changed['nodes'][1]['config']['template']==fixture['changed_no_hit_reply']
    assert changed['extra']==plan['extra'] and changed['edges']==plan['edges'] and plan['nodes'][1]['config']['template']=='原文。'
    for index in (0,1):
        bad=copy.deepcopy(plan);bad['nodes'][index]['config']={}
        with pytest.raises(RuntimeError):guard.changed_plan(bad,fixture)

@pytest.mark.parametrize('raw',['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'])
def test_approval_json_never_accepts_ambiguous_values(tmp_path,raw):
    f=tmp_path/'input.json';f.write_text(raw,'utf-8')
    with pytest.raises(RuntimeError):entry.load(f)
