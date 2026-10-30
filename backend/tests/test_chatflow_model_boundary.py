import copy,importlib,json,sys
from pathlib import Path
import httpx,pytest
SOURCE=Path(__file__).resolve().parents[2]/'tools/chatflow-model391'

@pytest.fixture(autouse=True)
def isolated_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]));monkeypatch.syspath_prepend(str(SOURCE))
    for p in SOURCE.glob('*.py'):monkeypatch.delitem(sys.modules,p.stem,raising=False)
    global guard,entry,common
    guard=importlib.import_module('guard');entry=importlib.import_module('execute');common=importlib.import_module('common')
    yield
    for p in SOURCE.glob('*.py'):sys.modules.pop(p.stem,None)

def provider():return {'id':'public','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'output_per_million_usd':1.2}}
def gate():return guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None)
def messages():return [{'role':'user','content':'公开合成JSON规划，不包含客户资料。'}]
def kwargs():return {'max_tokens':6000,'timeout':120,'json_mode':True}
def request(b,body=None,url=None,method='POST',key='PUBLIC_KEY'):
    return httpx.Request(method,url or 'https://api.deepseek.com/chat/completions',json=body or {'model':'deepseek-flash','messages':messages(),'max_tokens':6000,'stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}},headers={'authorization':'Bearer '+key})

def test_exact_one_dispatch_per_stage_and_root_review_before_second():
    b=gate();b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs());b.admit(request(b));b.finish()
    with pytest.raises(RuntimeError):b.begin('original')
    with pytest.raises(RuntimeError):b.begin('modified')
    b.record['reviews']={'original':{'actor':'agent_delegated'}};b.begin('modified');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs());b.admit(request(b));b.finish()
    assert b.record['model_http_started']==2
    with pytest.raises(RuntimeError):b.admit(request(b))

@pytest.mark.parametrize('change',['model','key','output','timeout','stream','images','price','oversize','expired'])
def test_wrong_call_or_quote_never_arms_dispatch(change):
    b=gate();b.begin('original');p=provider();k='PUBLIC_KEY';m=messages();kw=kwargs()
    if change=='model':p['model']='other'
    if change=='key':k='OTHER'
    if change=='output':kw['max_tokens']=6001
    if change=='timeout':kw['timeout']=121
    if change=='stream':kw['stream']=True
    if change=='images':kw['allow_images']=True
    if change=='price':p['pricing']['input_per_million_usd']=5
    if change=='oversize':m[0]['content']='X'*300000
    if change=='expired':b.started-=1801
    with pytest.raises(RuntimeError):b.prepare(p,k,m,kw)
    assert b.calls=={'original':0,'modified':0} and not b.armed

@pytest.mark.parametrize('change',['url','dify','method','key','message','extra','thinking','output'])
def test_transport_exact_endpoint_payload_and_prequoted_messages(change):
    b=gate();b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs());r=request(b);body=json.loads(r.content)
    if change=='url':r=request(b,url='https://other.invalid/chat/completions')
    if change=='dify':r=request(b,url='http://127.0.0.1:8080/v1/chat-messages')
    if change=='method':r=request(b,method='GET')
    if change=='key':r=request(b,key='WRONG')
    if change=='message':body['messages'][0]['content']='Changed after quote';r=request(b,body)
    if change=='extra':body['tools']=[];r=request(b,body)
    if change=='thinking':body['thinking']['type']='enabled';r=request(b,body)
    if change=='output':body['max_tokens']=7000;r=request(b,body)
    with pytest.raises(RuntimeError):b.admit(r)
    assert sum(b.calls.values())==0

@pytest.mark.parametrize('field,value',[('revision',True),('revision',2),('source_sha256','other'),('task_id','other'),('stage','modified'),('actor','direct_human'),('decision','reject'),('note','')])
def test_content_review_must_bind_actual_source_and_delegated_actor(field,value):
    source={'stage':'original','task_id':'public','revision':1,'source_sha256':'a'*64};r={**source,'actor':'agent_delegated','decision':'proceed','note':'根代理已按公开需求逐项核对，非人类签收。'}
    assert guard.check_review(r,source,True)['semantic_reviewed']
    r[field]=value
    with pytest.raises(RuntimeError):guard.check_review(r,source,True)

def test_synthetic_review_never_claims_real_semantic_quality():
    s={'stage':'original','task_id':'public','revision':1,'source_sha256':'a'*64};r={**s,'actor':'synthetic_protocol','decision':'proceed','note':'仅公开协议。'}
    assert not guard.check_review(r,s,False)['semantic_reviewed']
    with pytest.raises(RuntimeError):guard.check_review(r,s,True)

def frozen(tmp):
    plan={'batch_id':'chatflow-model391','policy':copy.deepcopy(entry.POLICY),'limits':copy.deepcopy(common.LIMITS),'new_conservative_upper':copy.deepcopy(entry.UPPER),'runtime_build':'0.363.0-337d1119bd845a02a18b','backend_path':str(common.PROJECT/'.runtime/snapshots/0.363.0-337d1119bd845a02a18b/backend'),'provider_id':'9513f594-c256-46b7-882a-35d9871bf9d0','all_old_reservations_kept':True,'billing_hard_cap':False}
    for name in entry.FROZEN:(tmp/name).write_text('{}','utf-8')
    def save():
        (tmp/'plan.json').write_text(json.dumps(plan),'utf-8');(tmp/'manifest.json').write_text(json.dumps({'batch_id':'chatflow-model391','files':{n:common.sha(tmp/n) for n in entry.FROZEN}}),'utf-8')
    save();return plan,save

@pytest.mark.parametrize('key,value',[('max_model_http',3),('per_stage',2),('dify_http',1),('production_writes',True),('root_review_required',False),('no_retry',False),('output_tokens',7000),('total_estimate_usd','0.200')])
def test_frozen_scope_and_money_cannot_expand(tmp_path,key,value):
    p,save=frozen(tmp_path);assert entry.validated(tmp_path)==p;p['policy'][key]=value;save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

def test_no_direct_approval_no_worker_and_single_claim(tmp_path):
    p,_=frozen(tmp_path)
    with pytest.raises(FileNotFoundError):entry.approved(tmp_path,p)
    with pytest.raises(RuntimeError):entry.authorize_worker(SOURCE,p)
    assert not (tmp_path/'worker-started.json').exists()
    entry.claim(tmp_path,{'state':'admitted'})
    with pytest.raises(FileExistsError):entry.claim(tmp_path,{'state':'admitted'})

def test_literal_change_does_not_alter_keys_ids_other_text_or_original():
    p={'nodes':[{'id':'first','text':'旧文字','config':{'reply':'旧文字'}}],'edges':[]};before=copy.deepcopy(p)
    out=guard.replacement(p,'旧文字','新文字');assert out['nodes'][0]['id']=='first' and out['nodes'][0]['config']['reply']=='新文字' and p==before


def test_duplicate_review_json_and_source_file_tampering_are_rejected(tmp_path):
    frozen(tmp_path);(tmp_path/'guard.py').write_text('changed','utf-8')
    with pytest.raises(RuntimeError):entry.validated(tmp_path)
    p=tmp_path/'review.json';p.write_text('{"decision":"proceed","decision":"reject"}','utf-8')
    with pytest.raises(RuntimeError):entry.load(p)


@pytest.mark.parametrize('bad',['external_node','true_initial','extra_state','model','retrieval','context','changed_scope'])
def test_generated_candidate_must_keep_declared_resources_and_exact_change(bad):
    from app.after_sales_starter import prepare
    f=json.loads((SOURCE/'fixture.json').read_text('utf-8'));task={'id':'public-unit','name':'公开技术夹具','app_type':'advanced-chat','revision':1,'requirements':f['requirements'],'configuration':f['configuration']}
    task['workflow_plan']=json.loads(prepare(task,f['inputs'])[0]);assert guard.candidate(None,task,f)['static_valid'];first=copy.deepcopy(task['workflow_plan']);p=task['workflow_plan']
    if bad=='external_node':p['nodes'].append({'id':'external','type':'http-request','config':{}})
    if bad=='true_initial':p['conversation_variables'][0]['initial_value']=True
    if bad=='extra_state':p['conversation_variables'].append(copy.deepcopy(p['conversation_variables'][0]))
    if bad=='model':next(n for n in p['nodes'] if n['type']=='llm')['config']['model']={'provider':'other/provider','name':'other-model','mode':'chat','completion_params':{'temperature':.2,'max_tokens':512,'thinking':False}}
    if bad=='retrieval':next(n for n in p['nodes'] if n['type']=='knowledge-retrieval')['config']['top_k']=5
    if bad=='context':next(n for n in p['nodes'] if n['id']=='grounded_answer')['config']['user_prompt']='{{#sys.query#}}'
    if bad=='changed_scope':
        task['workflow_plan']=guard.replacement(p,f['inputs']['no_hit_reply'],f['changed_no_hit_reply']);task['workflow_plan']['nodes'][0]['title']='Changed beyond reply'
    with pytest.raises(RuntimeError):guard.candidate(None,task,f,first if bad=='changed_scope' else None)
