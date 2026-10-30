import copy,importlib,json,sys
from pathlib import Path
import httpx,pytest

SOURCE=Path(__file__).resolve().parents[2]/'tools/reviewed-planning408'

@pytest.fixture(autouse=True)
def isolated_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]));monkeypatch.syspath_prepend(str(SOURCE))
    for p in SOURCE.glob('*.py'):monkeypatch.delitem(sys.modules,p.stem,raising=False)
    global guard,entry,common
    guard=importlib.import_module('guard');entry=importlib.import_module('execute');common=importlib.import_module('common')
    yield
    for p in SOURCE.glob('*.py'):sys.modules.pop(p.stem,None)

def provider():return {'id':'public','provider':'deepseek','protocol':'openai-compatible','base_url':'https://api.deepseek.com','model':'deepseek-flash','pricing':{'input_per_million_usd':.3,'output_per_million_usd':1.2}}
def messages():return [{'role':'user','content':'公开合成单次规划'}]
def gate():return guard.Boundary(provider(),'PUBLIC_KEY',{},lambda:None)
def kwargs():return {'max_tokens':6000,'timeout':120,'json_mode':True}
def request(body=None,url='https://api.deepseek.com/chat/completions',method='POST',key='PUBLIC_KEY'):
    return httpx.Request(method,url,json=body or {'model':'deepseek-flash','messages':messages(),'max_tokens':6000,'stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}},headers={'authorization':'Bearer '+key})

def test_no_second_stage_even_after_root_review_and_no_retry():
    b=gate();b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs());b.admit(request());b.finish()
    b.record['reviews']={'original':{'actor':'agent_delegated'}}
    for stage in ('original','modified'):
        with pytest.raises(RuntimeError):b.begin(stage)
    with pytest.raises(RuntimeError):b.admit(request())
    assert b.calls=={'original':1}

@pytest.mark.parametrize('change',['model','key','output','timeout','stream','images','price','oversize','expired'])
def test_bad_request_or_over_budget_never_arms(change):
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
    assert b.calls=={'original':0} and not b.armed

@pytest.mark.parametrize('change',['dify','method','key','message','tools','thinking','output'])
def test_exact_prequoted_model_transport_only(change):
    b=gate();b.begin('original');b.prepare(provider(),'PUBLIC_KEY',messages(),kwargs())
    body=json.loads(request().content);url='https://api.deepseek.com/chat/completions';method='POST';key='PUBLIC_KEY'
    if change=='dify':url='http://127.0.0.1:8080/v1/chat-messages'
    if change=='method':method='GET'
    if change=='key':key='OTHER'
    if change=='message':body['messages'][0]['content']='Changed'
    if change=='tools':body['tools']=[]
    if change=='thinking':body['thinking']['type']='enabled'
    if change=='output':body['max_tokens']=6001
    with pytest.raises(RuntimeError):b.admit(request(body,url,method,key))
    assert b.calls=={'original':0}

def packet(root):
    p={'batch_id':'reviewed-planning408','policy':copy.deepcopy(entry.POLICY),'limits':copy.deepcopy(common.LIMITS),'new_conservative_upper':copy.deepcopy(entry.UPPER),'runtime_build':'0.373.0-f8dc99952a3bf70b3b6d','backend_path':str(common.PROJECT/'.runtime/snapshots/0.373.0-f8dc99952a3bf70b3b6d/backend'),'provider_id':'9513f594-c256-46b7-882a-35d9871bf9d0','all_old_reservations_kept':True,'billing_hard_cap':False,'regrant':copy.deepcopy(entry.REGRANT),'protected_isolated':{k:{} for k in ('391','394','399','401','405')},'source_model_plan_sha256':entry.SOURCE_PLAN,'source_cases_sha256':entry.SOURCE_CASES}
    for name in entry.FROZEN:(root/name).write_text('{}','utf-8')
    def save():
        (root/'plan.json').write_text(json.dumps(p),'utf-8')
        (root/'manifest.json').write_text(json.dumps({'batch_id':p['batch_id'],'files':{name:common.sha(root/name) for name in entry.FROZEN}}),'utf-8')
    save();return p,save

@pytest.mark.parametrize('field,value',[('policy',{'max_model_http':2}),('limits',{'model':2}),('new_conservative_upper',{}),('regrant',{}),('protected_isolated',{}),('all_old_reservations_kept',False),('billing_hard_cap',True)])
def test_scope_regrant_and_protected_isolated_source_required(tmp_path,field,value):
    p,save=packet(tmp_path);assert entry.validated(tmp_path)==p
    p[field]=value;save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

def test_no_direct_approval_no_worker_and_consumed_attempt_no_replay(tmp_path):
    p,_=packet(tmp_path)
    with pytest.raises(FileNotFoundError):entry.approved(tmp_path,p)
    entry.claim(tmp_path,{'state':'stopped'})
    with pytest.raises(FileExistsError):entry.claim(tmp_path,{'state':'admitted'})
    assert not (tmp_path/'worker-started.json').exists()

def test_frozen_sources_cannot_be_changed_after_scope_review(tmp_path):
    packet(tmp_path);(tmp_path/'fixture.json').write_text('Changed','utf-8')
    with pytest.raises(RuntimeError):entry.validated(tmp_path)

def test_original_failed_isolated_task_and_fee_must_match(monkeypatch):
    class ReadOnly:
        def __init__(self,root):self.root=root
        def list(self,kind):return [{}]*25
    monkeypatch.setattr(entry,'ReadOnly',ReadOnly)
    monkeypatch.setattr(entry,'capture',lambda source:{} if source.root==common.PROJECT/'data' else {'changed':'failed_391_fee'})
    with pytest.raises(RuntimeError,match='Old isolated'):
        entry.current({'protected_data':{},'protected_isolated':{k:{} for k in ('391','394','399','401','405')}})

@pytest.mark.parametrize('field,value',[('revision',True),('source_sha256','changed'),('task_id','other'),('actor','direct_human'),('decision','reject'),('note','')])
def test_root_review_binds_current_candidate_not_fake_human(field,value):
    source={'stage':'original','task_id':'public','revision':1,'source_sha256':'a'*64}
    receipt={**source,'actor':'agent_delegated','decision':'proceed','note':'实际核对来源和完整候选；非人类签收。'}
    assert guard.check_review(receipt,source,True)['semantic_reviewed']
    receipt[field]=value
    with pytest.raises(RuntimeError):guard.check_review(receipt,source,True)


def graph():
    return {'nodes':[{'id':'faq_answer','type':'llm','config':{'system_prompt':'Only retrieved facts.','user_prompt':'{{#retrieve.result#}}','temperature':.2}}, {'id':'no_hit','type':'answer','config':{'text':'Original fallback.'}}], 'edges':[{'source':'faq_answer','target':'no_hit'}]}


@pytest.mark.parametrize('fields',[('system_prompt',),('user_prompt',),('system_prompt','user_prompt')])
def test_only_answer_prompt_text_can_change(fields):
    old=graph();after=copy.deepcopy(old)
    for field in fields:after['nodes'][0]['config'][field]+=' Include the applicable conditions from retrieval.'
    assert guard.prompt_delta(old,after)==['faq_answer.config.'+field for field in fields]
    assert old==graph()  # Comparison must not mutate either source.
    assert after!=old


@pytest.mark.parametrize('change',['unchanged','other_node','model','edges','order','removed_prompt','empty_prompt','nontext_prompt','extra_field','duplicate_node'])
def test_replan_cannot_rebuild_graph_or_widen_prompt_change(change):
    old=graph();after=copy.deepcopy(old);after['nodes'][0]['config']['system_prompt']+=' Answer completely.'
    if change=='unchanged':after=copy.deepcopy(old)
    if change=='other_node':after['nodes'][1]['config']['text']='Changed fallback.'
    if change=='model':after['nodes'][0]['config']['temperature']=.5
    if change=='edges':after['edges']=[]
    if change=='order':after['nodes'].reverse()
    if change=='removed_prompt':del after['nodes'][0]['config']['user_prompt']
    if change=='empty_prompt':after['nodes'][0]['config']['system_prompt']=' '
    if change=='nontext_prompt':after['nodes'][0]['config']['system_prompt']={'text':'No'}
    if change=='extra_field':after['new']='outside scope'
    if change=='duplicate_node':after['nodes'].append(copy.deepcopy(after['nodes'][0]))
    with pytest.raises(RuntimeError):guard.prompt_delta(old,after)


@pytest.mark.parametrize('change',['revision','cases','requirements','configuration','plan_source','graph'])
def test_source_task_is_exact_saved_revision_not_other_failure(monkeypatch,change):
    f={'source_task_id':'aedbefb3-36a4-42cb-8f73-19f9f621ed8c','cases':[],'base_requirements':{'goal':'Public'},'configuration':{'assistant_provider_id':'new','resource_plan':'model only','dify_model':'fixed'}}
    t={'id':f['source_task_id'],'revision':7,'plan_source':'manual','test_cases':[],'requirements':f['base_requirements'].copy(),'configuration':{'assistant_provider_id':None,'resource_plan':'old','dify_model':'fixed'},'workflow_plan':graph()}
    f.update(source_plan_sha256=common.digest(t['workflow_plan']),source_cases_sha256=common.digest(t['test_cases']))
    class ReadOnly:
        def __init__(self,root):pass
        def get(self,kind,item):return t
    monkeypatch.setattr(guard,'ReadOnly',ReadOnly)
    assert guard.baseline(f)==graph()
    if change=='revision':t['revision']=8
    if change=='cases':t['test_cases']=[{'id':'changed'}]
    if change=='requirements':t['requirements']['goal']='Changed'
    if change=='configuration':t['configuration']['dify_model']='other'
    if change=='plan_source':t['plan_source']='model_draft'
    if change=='graph':t['workflow_plan']['edges']=[]
    with pytest.raises(RuntimeError):guard.baseline(f)


@pytest.mark.parametrize('change',['source','new_slot','estimate','source_graph','source_cases','one_root_missing'])
def test_regrant_cannot_silently_borrow_other_unused_scopes(tmp_path,change):
    p,save=packet(tmp_path)
    if change=='source':p['regrant']['source_batch']='reviewed-platform406'
    if change=='new_slot':p['regrant']['new_slots']=1
    if change=='estimate':p['regrant']['estimate_usd']='0.160'
    if change=='source_graph':p['source_model_plan_sha256']='0'*64
    if change=='source_cases':p['source_cases_sha256']='0'*64
    if change=='one_root_missing':p['protected_isolated'].pop('401')
    save()
    with pytest.raises(RuntimeError):entry.validated(tmp_path)
