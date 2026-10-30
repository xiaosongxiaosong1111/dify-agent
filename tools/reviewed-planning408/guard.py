"""One model request, disposable data, explicit root review; no Dify traffic."""
import copy,json,time
from decimal import Decimal
from urllib.parse import urlsplit
from common import PROJECT,ReadOnly,digest,require

STAGES=('original',)
CAP=Decimal('0.080')

def baseline(fixture):
    t=ReadOnly(PROJECT/'data').get('task',fixture['source_task_id'])
    require(t and t['id']=='aedbefb3-36a4-42cb-8f73-19f9f621ed8c' and t['revision']==7 and t['plan_source']=='manual','Exact source Task/revision required')
    require(digest(t['workflow_plan'])==fixture['source_plan_sha256'] and digest(t['test_cases'])==fixture['source_cases_sha256'] and t['test_cases']==fixture['cases'] and t['requirements']==fixture['base_requirements'],'Saved source graph/cases/requirements changed')
    require({k:v for k,v in t['configuration'].items() if k not in {'assistant_provider_id','resource_plan'}}=={k:v for k,v in fixture['configuration'].items() if k not in {'assistant_provider_id','resource_plan'}},'Other Dify/business configuration changed')
    return copy.deepcopy(t['workflow_plan'])

def prompt_delta(before,after):
    require(isinstance(after,dict),'Full candidate object required');restored=copy.deepcopy(after);changes=[]
    old_node=next(n for n in before['nodes'] if n['id']=='faq_answer')
    nodes=restored.get('nodes');require(isinstance(nodes,list),'Full nodes required')
    target=next((n for n in nodes if isinstance(n,dict) and n.get('id')=='faq_answer'),None)
    require(target is not None and isinstance(target.get('config'),dict),'Original answer node required')
    for key in ('system_prompt','user_prompt'):
        require(key in target['config'] and isinstance(target['config'][key],str) and target['config'][key].strip(),'Literal complete answer prompts required')
        if target['config'][key]!=old_node['config'][key]:changes.append('faq_answer.config.'+key)
        target['config'][key]=old_node['config'][key]
    require(changes and digest(restored)==digest(before),'Only answer prompt text may change; no unchanged graph or other edits')
    return changes

def candidate(h,task,fixture,first=None):
    from app.workflow_plan import compile_workflow_plan
    import yaml
    p=task['workflow_plan'];require(isinstance(p,dict),'No current model candidate')
    require(1<=len(p['nodes'])<=80 and all(n['type'] in {'start','answer','code','template-transform','if-else','question-classifier','parameter-extractor','knowledge-retrieval','llm','assigner'} for n in p['nodes']),'Only reviewed root Chatflow subset')
    states=p.get('conversation_variables',[])
    require(len(states)==2 and {r['name'] for r in states}=={'order_wait_requested','order_wait_consumed'} and all(r['var_type']=='boolean' and r['initial_value'] is False and r['persistence_policy']=='per_conversation' and r['unwritten_policy']=='retain_current' for r in states),'Only the two specified isolated boolean flags')
    text,checked=compile_workflow_plan(task);require(checked['valid'],'Candidate compile failed');native=yaml.safe_load(text)
    for n in native['workflow']['graph']['nodes']:
        data=n['data']
        if 'model' in data:
            model=data['model'];require(model['provider']==fixture['configuration']['dify_model_provider'] and model['name']=='deepseek-flash' and model['completion_params'].get('temperature')==.2 and model['completion_params'].get('max_tokens')==512 and model['completion_params'].get('thinking') is False,'Generated Dify model differs')
        if data['type']=='knowledge-retrieval':
            cfg=data['multiple_retrieval_config'];require(data['dataset_ids']==fixture['configuration']['dataset_ids'] and cfg['top_k']==3 and not cfg['reranking_enable'] and cfg.get('score_threshold') is None and not cfg.get('score_threshold_enabled',False),'Generated retrieval source/settings differ')
    changes=prompt_delta(baseline(fixture),p)
    return {'native_sha256':digest(native),'plan_sha256':digest(p),'static_valid':True,'business_verified':False,'changed_fields':changes}

class Boundary:
    def __init__(self,provider,key,record,save):
        self.provider=provider;self.key=key;self.record=record;self.save=save
        self.phase=None;self.started=time.monotonic();self.halted=False;self.calls={s:0 for s in STAGES};self.quotes={};self.in_call=False;self.armed=False
    def begin(self,stage):
        require(not self.halted and stage in STAGES and self.calls[stage]==0 and not self.in_call,'Stage unavailable or consumed')
        require(stage=='original' or self.record.get('reviews',{}).get('original'),'Root original review required before modified call');self.phase=stage
    def prepare(self,provider,key,messages,kwargs):
        from app.planning import reserve_cost
        require(not self.halted and time.monotonic()-self.started<1800 and self.phase in STAGES and self.calls[self.phase]==0 and not self.in_call,'No retry/expired/stopped')
        require(all(provider.get(k)==self.provider.get(k) for k in ('id','provider','protocol','base_url','model','pricing')) and key==self.key,'Wrong provider/credential')
        require(kwargs.get('max_tokens')==6000 and 0<kwargs.get('timeout',0)<=120 and kwargs.get('json_mode') is True and not kwargs.get('stream',False) and not kwargs.get('allow_images',False),'Model call settings differ')
        require(isinstance(messages,list) and all(m.get('role') in {'system','user','assistant'} and isinstance(m.get('content'),str) for m in messages),'Only frozen text profile')
        quote=reserve_cost(messages,provider['pricing'],6000);require(0<=quote<=CAP and sum(self.quotes.values(),Decimal(0))+quote<=CAP,'Model estimate cap exceeded')
        self.quotes[self.phase]=quote;self.message_sha=digest(messages);self.record.setdefault('estimates',{})[self.phase]=str(quote);self.in_call=True;self.armed=True;self.save()
    def admit(self,request):
        endpoint=self.provider['base_url'].rstrip('/')+'/chat/completions'
        require(self.armed and self.in_call and not self.halted and request.method=='POST' and str(request.url)==endpoint,'Only one prepared model endpoint; Dify and other traffic forbidden')
        require(request.headers.get('authorization')=='Bearer '+self.key,'Wrong model key')
        body=json.loads(request.content)
        require(set(body)<={'model','messages','max_tokens','stream','thinking','response_format'} and body['model']==self.provider['model'] and body['max_tokens']==6000 and body.get('stream') is False and body.get('thinking')=={'type':'disabled'} and body.get('response_format')=={'type':'json_object'},'Unexpected model payload')
        require(digest(body['messages'])==self.message_sha,'Quoted messages changed before dispatch')
        self.armed=False;self.calls[self.phase]+=1;self.record['model_http_started']=sum(self.calls.values());self.record['stage_counts']=dict(self.calls);self.save()
    def finish(self):self.in_call=False;self.armed=False
    def stop(self):self.halted=True;self.armed=False;self.save()

def check_review(receipt,source,live):
    require(isinstance(receipt,dict) and type(receipt.get('revision')) is int and all(receipt.get(k)==source[k] for k in ('stage','task_id','revision','source_sha256')) and receipt.get('decision')=='proceed' and receipt.get('actor')==('agent_delegated' if live else 'synthetic_protocol') and isinstance(receipt.get('note'),str) and receipt['note'].strip(),'Explicit current-source root review missing/rejected')
    return {'source_sha256':source['source_sha256'],'actor':receipt['actor'],'note':receipt['note'],'semantic_reviewed':live,'human_signoff':False}
