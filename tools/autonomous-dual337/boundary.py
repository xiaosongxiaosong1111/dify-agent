"""One bounded dual-revision Chatflow batch with a frozen model gate."""
import copy
import json
import time
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit
from common import LIMITS,MODEL_CAP_USD,MODEL_STAGES,MODEL_TOTAL_USD,digest,require,uuid

PROTOCOLS=('openai-compatible','deepseek')


class Boundary:
    def __init__(self,env,provider,key,fixture,contract,record,old_apps=()):
        self.env=env;self.provider=copy.deepcopy(provider);self.key=key;self.f=fixture;self.contract=contract;self.record=record;self.old_apps=set(old_apps)
        self.owner=None;self.current=None;self.apps={};self.messages={};self.native_runs={};self.sessions=set();self.documents=[]
        self.started=time.monotonic();self.halted=False;self.phase='reconnect';self.version='original';self.case_index=None
        self.workspace_verified=False;self.login_tokens=None;self.counts={k:0 for k in LIMITS if k!='new_tasks'}
        self.failure=None
        self.stage_counts={s:0 for s in MODEL_STAGES};self.prepared_stages=set();self.quotes={};self.model_stage=None;self.message_sha=None;self.in_call=False;self.armed=False
        record.update(dispatch_counts=self.counts,stage_counts=dict(self.stage_counts),dispatches=[]);self.save=lambda:None

    def begin_failure(self,message_id,conversation_id):
        require(self.failure is None and self.messages.get(message_id)==(self.current,conversation_id),'Only one known failed-message capture')
        self.failure={'message':message_id,'native':None,'step':0}

    def begin_model(self,stage):
        require(not self.halted and time.monotonic()-self.started<3600,'Batch stopped or expired')
        require(stage in MODEL_STAGES and stage not in self.prepared_stages and self.stage_counts[stage]==0 and sum(self.stage_counts.values())<LIMITS['model'] and not self.in_call and not self.armed and self.model_stage is None,'Model stage unavailable or consumed')
        self.prepared_stages.add(stage);self.model_stage=stage

    def prepare_model(self,provider,key,messages,kwargs):
        from app.planning import reserve_cost
        require(not self.halted and time.monotonic()-self.started<3600,'Batch stopped or expired')
        require(self.model_stage in MODEL_STAGES and self.stage_counts[self.model_stage]==0 and not self.in_call and not self.armed,'No prepared model stage')
        require(all(provider.get(k)==self.provider.get(k) for k in ('id','provider','protocol','base_url','model','pricing')) and key==self.key,'Wrong provider/credential')
        require(self.provider.get('protocol') in PROTOCOLS,'Unsupported product protocol; never switch models')
        require(kwargs.get('max_tokens')==6000 and 0<kwargs.get('timeout',0)<=120 and kwargs.get('json_mode') is True and not kwargs.get('stream',False) and not kwargs.get('allow_images',False),'Model call settings differ')
        require(isinstance(messages,list) and messages and all(isinstance(m,dict) and m.get('role') in {'system','user','assistant'} and type(m.get('content')) is str and bool(m.get('content')) for m in messages),'Only frozen plain-text messages')
        quote=reserve_cost(messages,provider['pricing'],6000)
        require(0<=quote<=Decimal(MODEL_CAP_USD) and sum(self.quotes.values(),Decimal(0))+quote<=Decimal(MODEL_TOTAL_USD),'Model estimate cap exceeded')
        self.quotes[self.model_stage]=quote;self.message_sha=digest(messages)
        self.record.setdefault('estimates',{})[self.model_stage]=str(quote)
        self.in_call=True;self.armed=True;self.save()

    def finish_model(self):
        self.in_call=False;self.armed=False;self.model_stage=None;self.message_sha=None;self.save()

    def _count(self,method,path,kind,extra):
        require(kind is not None and self.counts[kind]<LIMITS[kind],'Unapproved path or exhausted count')
        self.counts[kind]+=1;entry={'method':method,'path':path,'kind':kind,'version':self.version,'status':None,**extra}
        self.record['dispatches'].append(entry);self.save();return entry

    def _admit_model(self,request,url):
        endpoint=self.provider['base_url'].rstrip('/')+'/chat/completions'
        require(self.armed and self.in_call and request.method=='POST' and str(request.url)==endpoint,'Only one prepared model endpoint; other traffic forbidden')
        require(request.headers.get('authorization')=='Bearer '+self.key,'Wrong model key')
        body=json.loads(request.content)
        require(set(body)<={'model','messages','max_tokens','stream','thinking','response_format'} and body.get('model')==self.provider['model'] and body.get('max_tokens')==6000 and body.get('stream') is False and body.get('thinking')=={'type':'disabled'} and body.get('response_format')=={'type':'json_object'},'Unexpected model payload')
        require(self.message_sha is not None and digest(body.get('messages'))==self.message_sha,'Quoted messages changed before dispatch')
        stage=self.model_stage
        require(stage in MODEL_STAGES and self.stage_counts[stage]==0 and sum(self.stage_counts.values())<LIMITS['model'],'Model slot already consumed')
        self.armed=False;self.stage_counts[stage]=1;self.message_sha=None
        self.record['model_http_started']=sum(self.stage_counts.values());self.record['stage_counts']=dict(self.stage_counts)
        return self._count('POST',url.path,'model',{'stage':stage})

    def admit(self,request):
        require(not self.halted and time.monotonic()-self.started<3600,'Batch stopped or expired')
        url=urlsplit(str(request.url))
        if self.armed or self.in_call:return self._admit_model(request,url)
        target=urlsplit(self.env['base_url'])
        require((url.scheme,url.netloc)==(target.scheme,target.netloc) and not url.fragment,'Unapproved origin')
        method,path=request.method,url.path;body=json.loads(request.content) if request.content else None
        require(method=='GET' or not url.query,'Unexpected mutation query')
        kind=None;app=self.current;extra={}
        if self.failure is not None:
            f=self.failure;prefix='/console/api/apps/'+self.current
            paths=(prefix+'/messages/'+f['message'],prefix+'/workflow-runs/'+str(f['native']),prefix+'/workflow-runs/'+str(f['native'])+'/node-executions',prefix+'/workflows/publish')
            require(method=='GET' and not request.content and not url.query and f['step']<4 and path==paths[f['step']],'Only selected failure-message four-read sequence; no writes/Service/retry')
            f['step']+=1;kind='reads';extra={'failure_capture':True}
        elif method=='POST' and path=='/console/api/login':
            require(self.phase=='reconnect' and isinstance(body,dict) and set(body)=={'email','password','remember_me'} and body['remember_me'] is False,'Unapproved login');kind='login'
        elif method=='GET':
            ids=self.f['configuration']['dataset_ids'][:1]
            require(len(ids)==1 and uuid(ids[0]),'Pinned FAQ dataset missing')
            base='/console/api/datasets/'+ids[0]
            faq_query={base:{},base+'/documents':{'page':['1'],'limit':['2']}}
            segments=any(path==base+'/documents/'+d+'/segments' for d in self.documents)
            faq=path in faq_query or segments
            common=path in {'/console/api/apps','/console/api/workspaces/current/summary'}
            scoped=any(path==f'/console/api/apps/{a}'+tail for a in self.apps for tail in ('','/workflows/draft','/workflows/publish','/api-keys'))
            message=any(path==f'/console/api/apps/{a}/messages/{m}' for m,(a,c) in self.messages.items())
            native=any(path in (f'/console/api/apps/{a}/workflow-runs/{rid}',f'/console/api/apps/{a}/workflow-runs/{rid}/node-executions') for rid,a in self.native_runs.items())
            require(common or scoped or message or native or faq,'Unapproved management read')
            if faq:
                require(self.phase=='faq_read','FAQ reads only in the pinned read phase')
                expected=faq_query[path] if path in faq_query else {'page':['1'],'limit':['20']}
            else:expected={'page':['1'],'limit':['1']} if path=='/console/api/apps' else {}
            require(parse_qs(url.query,keep_blank_values=True)==expected,'Unexpected query');kind='reads'
        elif method=='POST' and path=='/console/api/apps/imports':
            require(self.workspace_verified and self.phase==self.version+'_import' and isinstance(body,dict) and set(body)=={'mode','yaml_content','name'} and body['mode']=='yaml-content' and body['name']==self.f['task_name'],'Unapproved import')
            from app.dsl_roundtrip import parse
            from app.workflow_publication import core
            native=parse(body['yaml_content'],'advanced-chat')
            require(self.owner and self.contract.get('owner_task_id')==self.owner,'Owner state IDs not materialized')
            frozen=self.contract.get(self.version)
            require(isinstance(frozen,dict) and all(k in frozen for k in ('plan','native','core','trace_expectations')),'Reviewed graph for this revision not registered yet')
            require(native['app']['mode']=='advanced-chat' and not native.get('dependencies') and not native['workflow'].get('environment_variables'),'Unexpected dependencies/type')
            require(digest(native)==digest(frozen['native']),'Imported native graph differs from frozen reviewed revision')
            require(digest(core(native['workflow']))==digest(frozen['core']),'Imported graph differs from frozen reviewed template');kind='import'
        elif method=='POST' and app in self.apps and path==f'/console/api/apps/{app}/workflows/publish':
            row=self.apps[app];require(self.phase==self.version+'_publish' and row['unpublished'] and not row['published'] and not row['publish_started'] and isinstance(body,dict) and set(body)=={'marked_name','marked_comment'},'Duplicate/unapproved publication');row['publish_started']=True;kind='publish'
        elif method=='POST' and app in self.apps and path==f'/console/api/apps/{app}/api-keys':
            row=self.apps[app];require(self.phase==self.version+'_key' and row['published'] and not row['key_started'] and body=={},'Duplicate/unapproved key');row['key_started']=True;kind='key'
        elif method=='POST' and path=='/v1/chat-messages':
            require(app in self.apps and self.phase==self.version+'_cases' and type(self.case_index) is int and 0<=self.case_index<6,'Unapproved case phase')
            row=self.apps[app];require(row['published'] and isinstance(row['key'],str) and row['key'],'Unpublished App or missing runtime key')
            sequence=row['service_count'];expected_sequence=sum(2 if c.get('followups') else 1 for c in self.f['cases'][:self.case_index])
            require(sequence in {expected_sequence,expected_sequence+1} and (sequence==expected_sequence or self.case_index==5),'Duplicate/out-of-order turn')
            second=sequence!=expected_sequence;case=self.f['cases'][self.case_index];turn=case['followups'][0] if second else case
            require(isinstance(body,dict) and set(body)==({'inputs','query','response_mode','conversation_id','user'} if second else {'inputs','query','response_mode','user'}) and body['inputs']=={} and body['query']==turn['input']['query'] and body['response_mode']=='blocking' and body['user']=='flowcraft-local','Unexpected Chatflow input/user')
            require(body.get('conversation_id')==(row['last_cid'] if second else None),'Cross-case/session source')
            require(request.headers.get('authorization')=='Bearer '+str(row['key']),'Wrong runtime key')
            require(sequence<7,'Per-App Service cap');row['service_count']+=1;kind='run';extra={'case_index':self.case_index,'second_turn':second}
        return self._count(method,path,kind,extra)

    def observed(self,entry,response):
        path,kind=entry['path'],entry['kind'];entry['status']=response.status_code
        if kind=='model':
            require(response.status_code==200,'Unexpected model HTTP status; stop without retry');self.save();return
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
        elif path.startswith('/console/api/datasets/'):
            dataset=self.f['configuration']['dataset_ids'][0]
            if path==f'/console/api/datasets/{dataset}':require(value.get('id')==dataset,'Unexpected dataset identity')
            elif path==f'/console/api/datasets/{dataset}/documents':
                rows=value.get('data');require(isinstance(rows,list),'Unexpected document listing')
                self.documents=[row.get('id') for row in rows[:2] if isinstance(row,dict)]
                require(all(uuid(i) for i in self.documents),'Invalid document identity')
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
            if self.failure is not None:self.failure['native']=rid
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
