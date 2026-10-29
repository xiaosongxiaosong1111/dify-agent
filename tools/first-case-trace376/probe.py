"""Exact existing failed-message trace plus limited public FAQ indexing metadata."""
import copy
import json
import math
import time
from urllib.parse import parse_qs,urlsplit
from support import require,uuid


class Boundary:
    def __init__(self,target,env,record):
        self.t=target;self.env=env;self.record=record;self.phase='reconnect';self.started=time.monotonic();self.halted=False
        self.counts={'reads':0,'login':0};self.auth_reads=0;self.trace_reads=0;self.metadata_reads=0;self.native=None;self.documents=[];self.read_documents=[];self.workspace_verified=False;self.tokens=None
        self.save=lambda:None;self.source_current=lambda:None;record.update(dispatch_counts=self.counts,dispatches=[])
    def admit(self,request):
        require(not self.halted and time.monotonic()-self.started<600,'Read batch stopped or expired')
        self.source_current()
        url=urlsplit(str(request.url));base=urlsplit(self.env['base_url']);path=url.path;method=request.method
        require((url.scheme,url.netloc)==(base.scheme,base.netloc) and not url.fragment,'Wrong origin')
        body=json.loads(request.content) if request.content else None;query=parse_qs(url.query,keep_blank_values=True);kind=None
        require(method!='GET' or not request.content,'GET body forbidden')
        if self.phase=='reconnect':
            if method=='POST' and path=='/console/api/login':
                require(self.counts['login']==0 and not query and isinstance(body,dict) and set(body)=={'email','password','remember_me'} and body['remember_me'] is False,'Unexpected login');kind='login'
            elif method=='GET':
                expected=('/console/api/apps','/console/api/workspaces/current/summary')
                require(self.counts['login']==1 and self.auth_reads<2 and path==expected[self.auth_reads] and query==({'page':['1'],'limit':['1']} if self.auth_reads==0 else {}),'Unexpected auth read');self.auth_reads+=1;kind='reads'
        elif method=='GET' and not body:
            require(self.workspace_verified,'Original workspace proof absent')
            if self.phase=='diagnose':
                prefix='/console/api/apps/'+self.t['app_id']
                expected=(prefix+'/messages/'+self.t['message_id'],prefix+'/workflow-runs/'+str(self.native),prefix+'/workflow-runs/'+str(self.native)+'/node-executions',prefix+'/workflows/publish')
                require(self.trace_reads<4 and path==expected[self.trace_reads] and not query,'Wrong/duplicate trace source');self.trace_reads+=1;kind='reads'
            elif self.phase=='metadata':
                require(self.trace_reads==4,'Trace source must be complete first')
                prefix='/console/api/datasets/'+self.t['dataset_id']
                if self.metadata_reads==0:require(path==prefix and not query,'Wrong dataset')
                elif self.metadata_reads==1:require(path==prefix+'/documents' and query=={'page':['1'],'limit':['2']},'Wrong document page/limit')
                else:
                    index=self.metadata_reads-2
                    require(index<len(self.documents) and path==prefix+'/documents/'+self.documents[index]+'/indexing-status' and not query,'Unknown/repeated document status');self.read_documents.append(self.documents[index])
                self.metadata_reads+=1;kind='reads'
        require(kind is not None and self.counts[kind]<(1 if kind=='login' else 10),'Unapproved request/count')
        self.counts[kind]+=1;entry={'method':method,'path':path,'kind':kind,'phase':self.phase,'status':None};self.record['dispatches'].append(entry);self.save();return entry
    def observed(self,entry,response):
        entry['status']=response.status_code;require(response.status_code in (200,201),'HTTP failure stops whole read batch');v=response.json();path=entry['path']
        if entry['kind']=='login':
            cookies={c.name:c.value for c in response.cookies.jar};prefix='__Host-' if '__Host-access_token' in cookies else '';self.tokens={'console_token':cookies.get(prefix+'access_token'),'csrf_token':cookies.get(prefix+'csrf_token')};require(all(isinstance(x,str) and x for x in self.tokens.values()),'Login tokens missing')
        elif path=='/console/api/workspaces/current/summary':require(v.get('id')==self.t['workspace_id'],'Wrong workspace');self.workspace_verified=True
        elif '/messages/' in path:
            require(v.get('id')==self.t['message_id'] and v.get('conversation_id')==self.t['conversation_id'] and uuid(v.get('workflow_run_id')),'Message/cid/run mismatch');self.native=v['workflow_run_id']
        elif path.endswith('/workflow-runs/'+str(self.native)):require(v.get('id')==self.native,'Native run mismatch')
        elif path=='/console/api/datasets/'+self.t['dataset_id']:require(v.get('id')==self.t['dataset_id'],'Dataset mismatch')
        elif self.phase=='metadata' and path.endswith('/documents'):
            require(('page' not in v or type(v['page']) is int and v['page']==1) and ('limit' not in v or type(v['limit']) is int and v['limit']==2),'Wrong returned document page/limit')
            rows=v.get('data');require(isinstance(rows,list) and len(rows)<=2 and all(isinstance(x,dict) and uuid(x.get('id')) for x in rows),'Document response invalid')
            self.documents=[x['id'] for x in rows];require(len(set(self.documents))==len(self.documents),'Duplicate document identity')
        self.save()
    async def dispatch(self,send,request):
        response=None
        try:
            entry=self.admit(request);response=await send(request);response.request=request;await response.aread();entry['response_body_read']=True;self.observed(entry,response);return response
        except BaseException:
            self.halted=True;self.record['stopped']=True
            if response is not None:
                try:await response.aclose()
                except Exception:pass
            self.save();raise


def metadata(value,fields):
    """Only controlled state/count fields; no names, content, errors, URLs or credentials."""
    statuses={'waiting','pending','parsing','cleaning','splitting','indexing','completed','error','paused','economy','economic','high_quality','only_me','all_team_members','partial_members'}
    result={}
    for key in fields:
        v=value.get(key)
        if v is None or type(v) is bool or type(v) is int and 0<=v<=10**12:result[key]=v
        elif isinstance(v,str) and v in statuses:result[key]=v
        else:result[key]=None
    result['error_present']=bool(value.get('error'));return result


def protected(base,initial_task,initial_env,b,old):
    from support import digest,require
    from app.run_diagnostics import source_hash
    target=b.t;rid=target['run_id'];initial=next(r for r in initial_task['runs'] if r['id']==rid)
    def normal(task):
        t=copy.deepcopy(task);t.pop('updated_at',None);t.pop('state_sequence',None)
        for r in t['runs']:
            if r['id']==rid:r.pop('diagnostics',None)
        return t
    class Guarded(base):
        reconnects=set();task_saves=0
        def _put_object(self,conn,states,kind,item,value):
            if kind=='task':
                require(item==target['task_id'] and normal(value)==normal(initial_task),'Other Task/business mutation')
                run=next(r for r in value['runs'] if r['id']==rid);reports=run.get('diagnostics',[]);prior=initial.get('diagnostics',[])
                require(self.task_saves==0 and len(reports)==len(prior)+1 and reports[:-1]==prior and reports[-1].get('source_hash')==source_hash(initial),'Unexpected diagnostic append');self.task_saves+=1
            elif kind=='environment':
                require(item==initial_env['id'],'Other environment')
                mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','capabilities'}
                require({k:v for k,v in value.items() if k not in mutable}=={k:v for k,v in initial_env.items() if k not in mutable},'Environment binding changed')
                require({k:v for k,v in value.get('capabilities',{}).items() if k!='console'}=={k:v for k,v in initial_env.get('capabilities',{}).items() if k!='console'},'Other capability change')
            elif kind in {'console_saved_reconnect','saved_console_reconnect','console_connection_failure'}:
                require(kind+':'+item not in old['objects'] and value.get('environment_id')==initial_env['id'],'Old/other auth receipt')
                if kind!='console_connection_failure':self.reconnects.add(item);require(len(self.reconnects)<=1,'Second reconnect')
            else:require(False,'Unexpected object write')
            return super()._put_object(conn,states,kind,item,value)
        def secret(self,item,key):require(item==initial_env['id'] and key in {'console_token','csrf_token','console_login_email','console_login_password','service_api_key','dataset_api_key'},'Unrelated credential read');return super().secret(item,key)
        def check_secrets(self,sets):
            require(b.workspace_verified and b.tokens,'Workspace proof before tokens')
            for item,values in sets.items():
                require(item==initial_env['id'] and set(values)<=set(b.tokens) and all(value==b.tokens[key] for key,value in values.items()),'Service/saved-login credential mutation')
        def set_secret(self,item,key,value):self.check_secrets({item:{key:value}});return super().set_secret(item,key,value)
        def put_with_secrets(self,kind,item,value,sets):self.check_secrets({item:sets});return super().put_with_secrets(kind,item,value,sets)
        def put_many_with_secrets(self,rows,item,sets):self.check_secrets({item:sets});return super().put_many_with_secrets(rows,item,sets)
        def put_many_with_secret_sets(self,rows,sets):self.check_secrets(sets);return super().put_many_with_secret_sets(rows,sets)
        def delete(self,*a):raise RuntimeError('Deletion forbidden')
    return Guarded,normal
