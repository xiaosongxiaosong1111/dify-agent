"""One fixed two-App Chatflow batch, including each physical conversation turn."""
import copy
import json
import time
from urllib.parse import parse_qs,urlsplit
from common import LIMITS,digest,require,uuid


class Boundary:
    def __init__(self,env,fixture,contract,record,old_apps=()):
        self.env=env;self.f=fixture;self.contract=contract;self.record=record;self.old_apps=set(old_apps)
        self.owner=None;self.current=None;self.apps={};self.messages={};self.native_runs={};self.sessions=set()
        self.started=time.monotonic();self.halted=False;self.phase='reconnect';self.version='original';self.case_index=None
        self.workspace_verified=False;self.login_tokens=None;self.counts={k:0 for k in LIMITS if k!='new_tasks'}
        record.update(dispatch_counts=self.counts,dispatches=[]);self.save=lambda:None

    def admit(self,request):
        require(not self.halted and time.monotonic()-self.started<3600,'Batch stopped or expired')
        url=urlsplit(str(request.url));target=urlsplit(self.env['base_url'])
        require((url.scheme,url.netloc)==(target.scheme,target.netloc) and not url.fragment,'Unapproved origin')
        method,path=request.method,url.path;body=json.loads(request.content) if request.content else None
        require(method=='GET' or not url.query,'Unexpected mutation query')
        kind=None;app=self.current;extra={}
        if method=='POST' and path=='/console/api/login':
            require(self.phase=='reconnect' and isinstance(body,dict) and set(body)=={'email','password','remember_me'} and body['remember_me'] is False,'Unapproved login');kind='login'
        elif method=='GET':
            common=path in {'/console/api/apps','/console/api/workspaces/current/summary'}
            scoped=any(path==f'/console/api/apps/{a}'+tail for a in self.apps for tail in ('','/workflows/draft','/workflows/publish','/api-keys'))
            message=any(path==f'/console/api/apps/{a}/messages/{m}' for m,(a,c) in self.messages.items())
            native=any(path in (f'/console/api/apps/{a}/workflow-runs/{rid}',f'/console/api/apps/{a}/workflow-runs/{rid}/node-executions') for rid,a in self.native_runs.items())
            require(common or scoped or message or native,'Unapproved management read')
            require(parse_qs(url.query,keep_blank_values=True)==({'page':['1'],'limit':['1']} if path=='/console/api/apps' else {}),'Unexpected query');kind='reads'
        elif method=='POST' and path=='/console/api/apps/imports':
            require(self.workspace_verified and self.phase==self.version+'_import' and isinstance(body,dict) and set(body)=={'mode','yaml_content','name'} and body['mode']=='yaml-content' and body['name']==self.f['task_name'],'Unapproved import')
            from app.dsl_roundtrip import parse
            from app.workflow_publication import core
            native=parse(body['yaml_content'],'advanced-chat')
            require(native['app']['mode']=='advanced-chat' and not native.get('dependencies') and not native['workflow'].get('environment_variables') and not native['workflow'].get('conversation_variables'),'Unexpected dependencies/type/state')
            require(digest(core(native['workflow']))==digest(self.contract[self.version]['core']),'Imported graph differs from frozen reviewed template');kind='import'
        elif method=='POST' and app in self.apps and path==f'/console/api/apps/{app}/workflows/publish':
            row=self.apps[app];require(self.phase==self.version+'_publish' and row['unpublished'] and not row['published'] and not row['publish_started'] and isinstance(body,dict) and set(body)=={'marked_name','marked_comment'},'Duplicate/unapproved publication');row['publish_started']=True;kind='publish'
        elif method=='POST' and app in self.apps and path==f'/console/api/apps/{app}/api-keys':
            row=self.apps[app];require(self.phase==self.version+'_key' and row['published'] and not row['key_started'] and body=={},'Duplicate/unapproved key');row['key_started']=True;kind='key'
        elif method=='POST' and path=='/v1/chat-messages':
            require(app in self.apps and self.phase==self.version+'_cases' and type(self.case_index) is int and 0<=self.case_index<6,'Unapproved case phase')
            row=self.apps[app];sequence=row['service_count'];expected_sequence=sum(2 if c.get('followups') else 1 for c in self.f['cases'][:self.case_index])
            require(sequence in {expected_sequence,expected_sequence+1} and (sequence==expected_sequence or self.case_index==5),'Duplicate/out-of-order turn')
            second=sequence!=expected_sequence;case=self.f['cases'][self.case_index];turn=case['followups'][0] if second else case
            require(isinstance(body,dict) and set(body)==({'inputs','query','response_mode','conversation_id','user'} if second else {'inputs','query','response_mode','user'}) and body['inputs']=={} and body['query']==turn['input']['query'] and body['response_mode']=='blocking' and body['user']=='flowcraft-local','Unexpected Chatflow input/user')
            require(body.get('conversation_id')==(row['last_cid'] if second else None),'Cross-case/session source')
            require(request.headers.get('authorization')=='Bearer '+str(row['key']),'Wrong runtime key')
            require(sequence<7,'Per-App Service cap');row['service_count']+=1;kind='run';extra={'case_index':self.case_index,'second_turn':second}
        require(kind is not None and self.counts[kind]<LIMITS[kind],'Unapproved path or exhausted count')
        self.counts[kind]+=1;entry={'method':method,'path':path,'kind':kind,'version':self.version,'status':None,**extra}
        self.record['dispatches'].append(entry);self.save();return entry

    def observed(self,entry,response):
        path,kind=entry['path'],entry['kind'];entry['status']=response.status_code
        if response.status_code==404 and entry['method']=='GET' and path.endswith('/workflows/publish'):
            app=path.split('/')[4];row=self.apps[app];require(not row['published'] and not row['publish_started'],'Existing publish disappeared');row['unpublished']=True;self.save();return
        require(response.status_code in (200,201),'Unexpected HTTP status; stop without retry')
        value=response.json()
        if kind=='login':
            cookies={c.name:c.value for c in response.cookies.jar};prefix='__Host-' if '__Host-access_token' in cookies else ''
            self.login_tokens={'console_token':cookies.get(prefix+'access_token'),'csrf_token':cookies.get(prefix+'csrf_token')}
            require(all(isinstance(v,str) and v for v in self.login_tokens.values()),'Login tokens missing')
        elif path=='/console/api/workspaces/current/summary':require(value.get('id')==self.env['console_workspace_id'],'Wrong workspace');self.workspace_verified=True
        elif kind=='import':
            app=value.get('app_id');require(value.get('status')=='completed' and uuid(app) and app not in self.old_apps and app not in self.apps,'Import did not return new App')
            self.current=app;self.apps[app]={'version':self.version,'published':None,'unpublished':False,'publish_started':False,'key_started':False,'key':None,'service_count':0,'last_cid':None}
        elif path.endswith('/workflows/draft') or path.endswith('/workflows/publish') and entry['method']=='GET':
            from app.workflow_publication import core
            app=path.split('/')[4];row=self.apps[app]
            if value is None:require(not row['published'] and not row['publish_started'],'Published workflow missing');row['unpublished']=True
            else:
                require(digest(core(value))==digest(self.contract[row['version']]['core']),'Remote draft/published graph differs')
                if path.endswith('/publish'):require(uuid(value.get('id')),'Missing published identity');row['published']=value['id']
        elif kind=='publish':require(value.get('result')=='success','Publication reply not success')
        elif kind=='key':
            require(isinstance(value.get('token'),str) and value['token'].startswith('app-') and uuid(value.get('id')),'Invalid key reply');self.apps[self.current]['key']=value['token']
        elif kind=='run':
            app=self.current;row=self.apps[app];mid=value.get('message_id');cid=value.get('conversation_id')
            require(uuid(mid) and value.get('id')==mid and mid not in self.messages and uuid(cid) and value.get('mode')=='advanced-chat' and isinstance(value.get('answer'),str) and value['answer'].strip(),'Unknown Chatflow response identity')
            require(cid==row['last_cid'] if entry['second_turn'] else cid not in self.sessions,'Session reuse/change')
            self.sessions.add(cid);row['last_cid']=cid;self.messages[mid]=(app,cid)
        elif '/messages/' in path:
            mid=path.rsplit('/',1)[-1];app,cid=self.messages[mid];rid=value.get('workflow_run_id')
            require(value.get('id')==mid and value.get('conversation_id')==cid and uuid(rid) and rid not in self.native_runs,'Message mapping mismatch/duplicate');self.native_runs[rid]=app
        elif '/workflow-runs/' in path and not path.endswith('/node-executions'):
            from app.diagnostic_graph_source import fingerprint
            rid=path.rsplit('/',1)[-1];app=self.native_runs[rid]
            require(value.get('id')==rid and fingerprint(value.get('graph'))==fingerprint(self.contract[self.apps[app]['version']]['native']['workflow']['graph']),'Native execution graph/identity mismatch')
        self.save()

    async def dispatch(self,send,request):
        response=None
        try:
            entry=self.admit(request);response=await send(request)
            response.request=request;entry['status']=response.status_code;entry['response_body_read']=False;self.save()
            await response.aread();entry['response_body_read']=True;self.observed(entry,response);return response
        except BaseException:
            self.halted=True;self.record['stopped']=True
            if response is not None:
                try:await response.aclose()
                except Exception:pass
            self.save();raise
