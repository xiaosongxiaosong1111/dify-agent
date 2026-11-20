"""Explicit source-bound local content reviews; never a platform or human approval."""
import copy,json,re,time
from pathlib import Path
from common import MODEL_STAGES,digest,require

PUBLIC_FIELDS=('id','revision','name','app_type','environment_id','requirements','configuration','messages','intake_review','intake_history','interview_attempts','workflow_plan','plan_source','planning_runs','test_cases','requirements_confirmed','configuration_confirmed','plan_stale','runs','artifact','dify_app_id','active_interview_id')
STAGES=MODEL_STAGES+('faq_read',)
PUBLIC_FIXTURE=('schema_version','task_name','requirements','configuration','inputs','cases','provider_id','environment_id','workspace_id')


def public_task(task):return {k:copy.deepcopy(task.get(k)) for k in PUBLIC_FIELDS}


def public_fixture(fixture):return {k:copy.deepcopy(fixture[k]) for k in PUBLIC_FIXTURE if k in fixture}


def response_index(responses):
    result={}
    if not isinstance(responses,dict):return result
    for stage,row in responses.items():
        if isinstance(row,dict):result[stage]={k:copy.deepcopy(row[k]) for k in ('file','sha256','characters') if k in row}
        elif isinstance(row,str):result[stage]=row
    return result


class Reviews:
    def __init__(self,output,h,record,live,save):
        self.root=Path(output);self.h=h;self.record=record;self.live=bool(live);self.save=save;self.current=None
        require(isinstance(getattr(h,'sierra_fixture',None),dict),'Sierra fixture missing')

    def check(self,value):
        text=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
        from app.plan_drafts import inspect_text
        inspect_text(text)
        secrets=getattr(self.h,'sierra_review_secrets',())
        require(isinstance(secrets,(list,tuple)),'Review secret registry must be in-memory list')
        for secret in secrets:
            require(not (isinstance(secret,str) and secret and secret in text),'Review text contains in-memory credential')
        return text

    def wait(self,stage,assessment,candidate=None):
        require(stage in STAGES,'Unknown content review stage')
        require(self.current is None,'Previous content review is still pending')
        require(stage not in self.record.get('reviews',{}),'Review already consumed')
        require(candidate is None or isinstance(candidate,dict),'Candidate must be the saved model JSON')
        fixture=self.h.sierra_fixture
        if stage=='faq_read':
            task=None;task_id=None;revision=None
        else:
            require(self.record.get('task_id'),'Review Task not registered')
            task=self.h.get_task(self.record['task_id']);task_id=task['id'];revision=task['revision']
        body={'stage':stage,'task_id':task_id,'revision':revision,'task':None if task is None else public_task(task),
              'candidate':copy.deepcopy(candidate),'assessment':copy.deepcopy(assessment),
              'requested_requirements':copy.deepcopy(fixture.get('requirements')),'fixture':public_fixture(fixture),
              'responses':response_index(self.record.get('responses')),
              'verification':'requires_actual_root_review_not_model_or_human_approval'}
        self.check(body)
        source=digest(body)
        source_path=self.root/('review-source-'+stage+'.json')
        source_path.write_text(json.dumps(body,ensure_ascii=False,indent=2),'utf-8')
        self.current={'stage':stage,'task_id':task_id,'revision':revision,'source_sha256':source,
                      'saved_task_sha256':None if task is None else digest(public_task(task)),'assessment_sha256':digest(assessment),
                      'candidate_sha256':None if candidate is None else digest(candidate)}
        self.record['waiting_review']={k:self.current[k] for k in ('stage','task_id','revision','source_sha256')};self.save()
        path=self.root/('review-'+stage+'.json')
        if not self.live:
            receipt={'stage':stage,'task_id':task_id,'revision':revision,'source_sha256':source,
                     'decision':'proceed','actor':'synthetic_protocol',
                     'note':'合成协议复核：仅核对本机来源与已登记结构，不代表模型语义、实际平台或人工签收。',
                     'semantic_reviewed':False,'human_signoff':False}
            if candidate is not None:
                hook=getattr(self.h,'sierra_synthetic_trace_expectations',None)
                require(callable(hook),'Synthetic trace expectation hook missing')
                expected=hook(candidate);require(expected is not None,'Synthetic trace expectations missing')
                receipt['trace_expectations']=copy.deepcopy(expected)
            self.check(receipt);path.write_text(json.dumps(receipt,ensure_ascii=False),'utf-8')
        receipt=self.await_receipt(stage,body,source,source_path,path)
        review={'stage':stage,'source_sha256':source,'actor':receipt['actor'],'note':receipt['note'],
                'semantic_reviewed':self.live,'human_signoff':False,
                'saved_task_sha256':self.current['saved_task_sha256'],'assessment_sha256':self.current['assessment_sha256'],
                'candidate_sha256':self.current['candidate_sha256']}
        if 'trace_expectations' in receipt:review['trace_expectations']=copy.deepcopy(receipt['trace_expectations'])
        self.record.setdefault('reviews',{})[stage]=review;self.record.pop('waiting_review',None);self.current=None;self.save()
        return receipt

    def await_receipt(self,stage,body,source,source_path,path):
        deadline=time.monotonic()+300
        while not path.exists():
            require(not (self.root/'stop.json').exists(),'Review stopped by explicit stop file')
            require(time.monotonic()<deadline,'Root review timeout')
            if self.current['task_id'] is not None:require(public_task(self.h.get_task(self.current['task_id']))==body['task'],'Review source task changed')
            require(digest(json.loads(source_path.read_text('utf-8')))==source,'Review source file changed')
            time.sleep(.1)
        require(time.monotonic()<deadline and not (self.root/'stop.json').exists(),'Late or stopped root review')
        from app.publication_dispatch_receipt import strict_json
        receipt=strict_json(path.read_bytes())
        self.check(receipt)
        require(isinstance(receipt,dict) and all(receipt.get(k)==self.current[k] for k in ('stage','task_id','revision','source_sha256')),'Explicit current-source review missing or rejected')
        require(receipt.get('decision')=='proceed','Explicit current-source review rejected')
        require(receipt.get('actor')==('agent_delegated' if self.live else 'synthetic_protocol'),'Review actor is not the delegated root agent')
        note=receipt.get('note')
        require(isinstance(note,str) and note.strip(),'Review note missing')
        if self.live:require(re.search('[一-鿿]',note),'Delegated review note must be non-empty Chinese')
        if self.current['task_id'] is not None:require(public_task(self.h.get_task(self.current['task_id']))==body['task'],'Review source task changed')
        require(digest(json.loads(source_path.read_text('utf-8')))==source,'Review source file changed')
        return receipt
