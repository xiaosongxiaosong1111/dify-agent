"""Counterexamples for the 337 boundary; zero physical HTTP and no live Dify."""
import asyncio
import json
import sys
from pathlib import Path

import httpx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'backend'))

from common import LIMITS,digest,require
from boundary import Boundary

FIXTURE=json.loads((HERE/'fixture.json').read_text(encoding='utf-8'))
ENV={'base_url':'https://dify.invalid','console_workspace_id':FIXTURE['workspace_id']}
KEY='local-boundary-key'
PROVIDER={'id':'public-provider','provider':'deepseek','protocol':'openai-compatible','base_url':'https://model.invalid/v1','model':'deepseek-flash','pricing':{'input_per_million_usd':0.14,'output_per_million_usd':0.28,'cached_input_per_million_usd':0.014}}
MESSAGES=[{'role':'user','content':'公开合成售后需求'}]
SETTINGS={'max_tokens':6000,'timeout':30,'json_mode':True}


class FakeResponse:
    def __init__(self,payload=None,status=200):
        self.status_code=status;self.payload=payload;self.request=None
        class Cookies:jar=[]
        self.cookies=Cookies()
    def json(self):return self.payload
    async def aread(self):pass
    async def aclose(self):pass


def make(contract=None):
    record={}
    boundary=Boundary(ENV,PROVIDER,KEY,FIXTURE,contract or {'owner_task_id':'task-public'},record)
    boundary.owner='task-public'
    return boundary


def app_row():
    return {'version':'original','published':None,'unpublished':False,'publish_started':False,'key_started':False,'key':None,'service_count':0,'last_cid':None}


def model_request(messages,key=KEY):
    body=json.dumps({'model':PROVIDER['model'],'messages':messages,'max_tokens':6000,'stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'}})
    return httpx.Request('POST',PROVIDER['base_url']+'/chat/completions',headers={'authorization':'Bearer '+key},content=body)


def sender(response):
    calls=[0]
    async def send(request):calls[0]+=1;return response
    return send,calls


def rejected(fn,text):
    try:fn()
    except RuntimeError as exc:require(text in str(exc),'wrong rejection: '+str(exc));return
    raise AssertionError('expected RuntimeError: '+text)


async def denied(boundary,request,text):
    send,calls=sender(FakeResponse())
    try:await boundary.dispatch(send,request)
    except RuntimeError as exc:
        require(text in str(exc),'wrong rejection: '+str(exc));require(calls[0]==0,'sender ran for a rejected request');return
    raise AssertionError('expected RuntimeError: '+text)


async def checks():
    passed=0
    boundary=make();boundary.counts['reads']=LIMITS['reads']
    await denied(boundary,httpx.Request('GET',ENV['base_url']+'/console/api/apps?page=1&limit=1'),'exhausted count');passed+=1
    boundary=make();boundary.counts['login']=LIMITS['login']
    await denied(boundary,httpx.Request('POST',ENV['base_url']+'/console/api/login',json={'email':'public@example.invalid','password':'public-only','remember_me':False}),'exhausted count');passed+=1
    boundary=make();boundary.counts['model']=LIMITS['model'];boundary.model_stage='first_interview';boundary.in_call=True;boundary.armed=True;boundary.message_sha=digest(MESSAGES)
    await denied(boundary,model_request(MESSAGES),'exhausted count');passed+=1
    boundary=make()
    await denied(boundary,httpx.Request('GET','https://evil.invalid/console/api/apps?page=1&limit=1'),'Unapproved origin');passed+=1
    boundary=make()
    await denied(boundary,httpx.Request('GET',ENV['base_url']+'/console/api/apps?page=1&limit=2'),'Unexpected query');passed+=1
    boundary=make(contract={'owner_task_id':'task-public'});boundary.workspace_verified=True;boundary.phase='original_import'
    dsl='kind: app\nversion: "0.7.0"\napp:\n  mode: advanced-chat\nworkflow:\n  graph: {}\n  environment_variables: []\n'
    await denied(boundary,httpx.Request('POST',ENV['base_url']+'/console/api/apps/imports',json={'mode':'yaml-content','yaml_content':dsl,'name':FIXTURE['task_name']}),'not registered yet');passed+=1
    boundary=make();app='11111111-1111-1111-1111-111111111111';boundary.current=app;boundary.phase='original_key';boundary.apps[app]=app_row()
    await denied(boundary,httpx.Request('POST',ENV['base_url']+f'/console/api/apps/{app}/api-keys',json={}),'Duplicate/unapproved key');passed+=1
    boundary=make();app='22222222-2222-2222-2222-222222222222';boundary.current=app;boundary.phase='original_cases';boundary.case_index=0;boundary.apps[app]=app_row()
    body={'inputs':{},'query':FIXTURE['cases'][0]['input']['query'],'response_mode':'blocking','user':'flowcraft-local'}
    await denied(boundary,httpx.Request('POST',ENV['base_url']+'/v1/chat-messages',headers={'authorization':'Bearer None'},json=body),'runtime key');passed+=1
    boundary=make();boundary.current=app;boundary.phase='original_cases';boundary.case_index=0
    published=app_row();published['published']='55555555-5555-5555-5555-555555555555';boundary.apps[app]=published
    await denied(boundary,httpx.Request('POST',ENV['base_url']+'/v1/chat-messages',headers={'authorization':'Bearer None'},json=body),'runtime key');passed+=1
    boundary=make();boundary.model_stage='complete_interview';boundary.in_call=True;boundary.message_sha=digest(MESSAGES)
    await denied(boundary,model_request(MESSAGES),'Only one prepared model endpoint');passed+=1
    boundary=make();boundary.begin_model('additional_interview');boundary.prepare_model(PROVIDER,KEY,MESSAGES,SETTINGS)
    await denied(boundary,model_request([{'role':'user','content':'变更后的合成消息'}]),'Quoted messages changed');passed+=1
    boundary=make();boundary.begin_model('original_plan');boundary.prepare_model(PROVIDER,KEY,MESSAGES,SETTINGS)
    await denied(boundary,model_request(MESSAGES,key='other-local-key'),'Wrong model key');passed+=1
    boundary=make();boundary.begin_model('modified_interview');boundary.prepare_model(PROVIDER,KEY,MESSAGES,SETTINGS)
    send,calls=sender(FakeResponse());response=await boundary.dispatch(send,model_request(MESSAGES))
    require(calls[0]==1 and response.status_code==200,'valid model dispatch did not run once')
    require(boundary.counts['model']==1 and boundary.stage_counts['modified_interview']==1 and boundary.counts['model']<=LIMITS['model'],'model counting differs')
    boundary.finish_model();rejected(lambda:boundary.begin_model('modified_interview'),'Model stage unavailable')
    require(calls[0]==1,'model sender ran more than once');passed+=1
    boundary=make();boundary.phase='faq_read';boundary.documents=['33333333-3333-3333-3333-333333333333']
    dataset=FIXTURE['configuration']['dataset_ids'][0]
    await denied(boundary,httpx.Request('GET',ENV['base_url']+f'/console/api/datasets/{dataset}/documents/44444444-4444-4444-4444-444444444444/segments?page=1&limit=20'),'Unapproved management read');passed+=1
    boundary=make();send,calls=sender(FakeResponse(payload={'id':'some-other-workspace'}))
    try:await boundary.dispatch(send,httpx.Request('GET',ENV['base_url']+'/console/api/workspaces/current/summary'))
    except RuntimeError as exc:
        require('Wrong workspace' in str(exc),'wrong workspace rejection')
        require(calls[0]==1 and boundary.halted and boundary.counts['reads']==1,'workspace halt state differs')
    else:raise AssertionError('expected RuntimeError: Wrong workspace')
    passed+=1
    return passed


async def main():
    physical=[0]
    def forbidden_request(self,request):
        physical[0]+=1;raise AssertionError('physical HTTP is forbidden in boundary checks')
    async def forbidden_async(self,request):
        physical[0]+=1;raise AssertionError('physical HTTP is forbidden in boundary checks')
    original=(httpx.HTTPTransport.handle_request,httpx.AsyncHTTPTransport.handle_async_request)
    httpx.HTTPTransport.handle_request=forbidden_request
    httpx.AsyncHTTPTransport.handle_async_request=forbidden_async
    try:
        passed=await checks()
        require(physical[0]==0,'a physical transport was used')
        print('passed',passed);print('physical_http0')
    finally:
        httpx.HTTPTransport.handle_request,httpx.AsyncHTTPTransport.handle_async_request=original


if __name__=='__main__':asyncio.run(main())
