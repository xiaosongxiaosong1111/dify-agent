"""Public rejection-path checks for the local review gate; no network or real data."""
import copy,json,sys,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace

PROJECT=Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT/'backend'))
from common import require
from reviews import Reviews

WORK=PROJECT/'work'
TOKEN='PUBLIC-REVIEW-TOKEN-ONLY-7f3a9c'
REQ=('goal','audience','input','output','rules','knowledge','exceptions','tests')
TASK_ID='11111111-1111-4111-8111-111111111111'
ENV_ID='22222222-2222-4222-8222-222222222222'
PROVIDER_ID='33333333-3333-4333-8333-333333333333'
FIXTURE={'schema_version':1,'task_name':'公开复核演示','requirements':{k:'公开需求：'+k for k in REQ},
         'configuration':{'assistant_provider_id':PROVIDER_ID},'inputs':{},'cases':[],
         'provider_id':PROVIDER_ID,'environment_id':ENV_ID,'workspace_id':'44444444-4444-4444-8444-444444444444'}


def base_task():
    return {'id':TASK_ID,'revision':1,'name':'公开复核Task','app_type':'advanced-chat','environment_id':ENV_ID,
            'requirements':{k:'公开需求：'+k for k in REQ},'configuration':{},
            'messages':[],'intake_review':None,'intake_history':[],'interview_attempts':[],
            'workflow_plan':None,'plan_source':None,'planning_runs':[],'test_cases':[],
            'requirements_confirmed':False,'configuration_confirmed':False,'plan_stale':False,
            'runs':[],'artifact':None,'dify_app_id':None,'active_interview_id':None}


def host(task):
    h=SimpleNamespace(task=task)
    def get_task(item_id):
        require(item_id==h.task['id'],'Unexpected Task read')
        return copy.deepcopy(h.task)
    h.get_task=get_task
    h.sierra_fixture=copy.deepcopy(FIXTURE)
    h.sierra_review_secrets=[TOKEN]
    return h


def wait_until(predicate,deadline,message):
    while not predicate():
        require(time.monotonic()<deadline,message)
        time.sleep(.02)


def receipt_for(record):
    waiting=record['waiting_review']
    return {'stage':waiting['stage'],'task_id':waiting['task_id'],'revision':waiting['revision'],
            'source_sha256':waiting['source_sha256'],'decision':'proceed','actor':'agent_delegated',
            'note':'仅为公开拒绝路径测试，非实际签收'}


def tamper_source(context):
    body=json.loads(context.source_path.read_text('utf-8'))
    body['public_tamper']=True
    context.source_path.write_text(json.dumps(body,ensure_ascii=False,indent=2),'utf-8')


def run_case(name,expected,tamper=None,after=None,token=False):
    with tempfile.TemporaryDirectory(dir=WORK,prefix='review-check-') as folder:
        output=Path(folder);task=base_task();h=host(task)
        record={'task_id':TASK_ID,'responses':{'first_interview':{'file':'model-response-first_interview.txt','sha256':'0'*64,'characters':12}},'reviews':{}}
        assessment={'public_note':'公开复核','anchor':TOKEN} if token else {'public_note':'公开复核','nothing_built':True}
        source_path=output/'review-source-first_interview.json'
        errors=[]
        def target():
            try:Reviews(output,h,record,live=True,save=lambda:None).wait('first_interview',assessment)
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=target,daemon=True);thread.start()
        deadline=time.monotonic()+3
        if token:
            thread.join(3)
            if thread.is_alive():
                (output/'stop.json').write_text('{}','utf-8');thread.join(1)
            require(not thread.is_alive(),name+': review thread did not stop')
            require(not source_path.exists(),name+': rejected assessment still wrote review source')
        else:
            wait_until(source_path.exists,deadline,name+': review source not written')
            wait_until(lambda:'waiting_review' in record,deadline,name+': review did not register source')
            receipt=receipt_for(record)
            if tamper:tamper(receipt)
            receipt_path=output/'review-first_interview.json'
            receipt_path.write_text(json.dumps(receipt,ensure_ascii=False),'utf-8')
            if after:after(SimpleNamespace(output=output,h=h,record=record,source_path=source_path,receipt_path=receipt_path,receipt=receipt,task=task))
            thread.join(3)
            if thread.is_alive():
                (output/'stop.json').write_text('{}','utf-8');thread.join(1)
            require(not thread.is_alive(),name+': review thread did not stop')
        require(errors,name+': expected an explicit rejection; no error was raised')
        require(len(errors)==1,name+': unexpected extra errors')
        error=errors[0]
        require(isinstance(error,RuntimeError),name+': unexpected error type '+type(error).__name__+': '+str(error))
        require(expected in str(error),name+': unexpected rejection: '+str(error))
        require(not record.get('reviews'),name+': rejected review was accepted into record.reviews')
        require(all(not value.get('human_signoff') for value in record.get('reviews',{}).values()),name+': simulated receipt marked as human signoff')


def main():
    import httpx
    WORK.mkdir(parents=True,exist_ok=True)
    physical={'count':0}
    old_sync=httpx.HTTPTransport.handle_request;old_async=httpx.AsyncHTTPTransport.handle_async_request
    def forbidden(*args,**kwargs):
        physical['count']+=1
        raise RuntimeError('Physical HTTP forbidden')
    httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=forbidden
    try:
        run_case('wrong source sha','Explicit current-source review missing or rejected',tamper=lambda r:r.update(source_sha256='0'*64))
        run_case('wrong actor','Review actor is not the delegated root agent',tamper=lambda r:r.update(actor='synthetic_protocol'))
        run_case('rejected decision','Explicit current-source review rejected',tamper=lambda r:r.update(decision='reject'))
        run_case('source task revision changed','Review source task changed',after=lambda c:c.task.update(revision=2))
        run_case('source file changed','Review source file changed',after=tamper_source)
        run_case('stop file with ready receipt','Late or stopped root review',after=lambda c:(c.output/'stop.json').write_text('{}','utf-8'))
        run_case('assessment contains test token','Review text contains in-memory credential',token=True)
    finally:
        httpx.HTTPTransport.handle_request=old_sync;httpx.AsyncHTTPTransport.handle_async_request=old_async
    require(physical['count']==0,'Physical HTTP attempted')
    print('passed 7 / physical_http0')


if __name__=='__main__':main()
