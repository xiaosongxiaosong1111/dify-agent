"""Public protocol responses only, never evidence of real model/business quality."""
import copy
import json
from uuid import uuid4
import httpx

class Stream(httpx.AsyncByteStream):
    def __init__(self,body):self.body=body
    async def __aiter__(self):yield self.body

def response(value,status=200,headers=()):
    return httpx.Response(status,headers=[('content-type','application/json'),*headers],stream=Stream(json.dumps(value,ensure_ascii=False).encode()))

class Synthetic:
    def __init__(self,b,mode):self.b=b;self.mode=mode;self.apps={};self.messages={};self.runs={}
    async def __call__(self,request):
        b=self.b;path=request.url.path;method=request.method;body=json.loads(request.content) if request.content else {}
        if path=='/console/api/login':return response({'result':'success'},503 if self.mode=='fail_login' else 200,[('set-cookie','access_token=PUBLICCONSOLETOKEN123456789; Path=/'),('set-cookie','csrf_token=PUBLICCSRFTOKEN123456789; Path=/')])
        if path=='/console/api/workspaces/current/summary':return response({'id':str(uuid4()) if self.mode=='wrong_workspace' else b.env['console_workspace_id']})
        if path=='/console/api/apps':return response({'data':[]})
        if path=='/console/api/apps/imports':
            if self.mode=='fail_import':return response({'error':'PUBLIC_FAILURE'},502)
            from app.dsl_roundtrip import parse
            app=str(uuid4());self.apps[app]={'draft':parse(body['yaml_content'],'advanced-chat')['workflow']|{'hash':'public-'+app},'published':None,'keys':[]};return response({'status':'completed','app_id':app})
        app=path.split('/')[4] if path.startswith('/console/api/apps/') else b.current
        if app in self.apps:
            row=self.apps[app]
            if path==f'/console/api/apps/{app}':return response({'id':app,'mode':'advanced-chat'})
            if path.endswith('/workflows/draft'):return response(copy.deepcopy(row['draft']))
            if path.endswith('/workflows/publish'):
                if method=='POST':
                    if self.mode=='fail_publish':return response({'error':'PUBLIC_FAILURE'},502)
                    row['published']=copy.deepcopy(row['draft'])|{'id':str(uuid4())};return response({'result':'success','created_at':1700000000})
                if row['published'] is None:return response(None,404)
                result=copy.deepcopy(row['published'])
                if self.mode=='changed_published':result['graph']['nodes'][0]['data']['title']='changed'
                return response(result)
            if path.endswith('/api-keys'):
                if method=='POST':
                    if self.mode=='fail_key':return response({'error':'PUBLIC_FAILURE'},502)
                    row['keys']=[{'id':str(uuid4()),'token':'app-PUBLIC-'+str(uuid4())}];return response(row['keys'][0])
                return response({'data':row['keys']})
        if path=='/v1/chat-messages':
            if self.mode=='fail_service':return response({'error':'PUBLIC_FAILURE'},502)
            case=b.f['cases'][b.case_index];second='conversation_id' in body
            turn=case['followups'][0] if second else case
            expected=turn['expectation']['expected'];answer=' '.join(expected) if isinstance(expected,list) else expected
            if b.version=='modified' and b.case_index==1:answer=b.f['changed_no_hit_reply']
            if self.mode in {'business_failure','failure_diagnostic_error'}:answer='公开替身错误答案'
            if self.mode=='second_turn_business_failure' and second:answer=b.f['inputs']['clarify_reply']
            cid=body.get('conversation_id') or str(uuid4())
            if second and self.mode=='changed_session':cid=str(uuid4())
            mid,rid=str(uuid4()),str(uuid4());self.messages[mid]={'id':mid,'conversation_id':cid,'workflow_run_id':rid}
            ids={'start','intent'};i=b.case_index
            if i in (0,1):ids|={'retrieve','collect_docs','check_hit'}|({'grounded_answer','faq_answer'} if i==0 or self.mode=='nonempty_no_answer' else {'no_hit','no_hit_answer'})
            elif i==2:ids|={'clarify','clarify_answer'}
            elif i in (3,4) or second:
                ids|={'extract_order','check_order','validate_order','check_order_value','order_lookup','order_answer'}
                if self.mode=='bypass_order_value':ids-={'validate_order','check_order_value'}
            else:
                ids|={'extract_order','check_order','missing_order','missing_order_answer'}
                if self.mode=='blank_order':ids|={'validate_order','check_order_value'}
            if self.mode=='second_turn_business_failure' and second:ids={'start','intent','clarify','clarify_answer'}
            graph=copy.deepcopy(self.apps[b.current]['published']['graph']);nodes=[]
            for n in graph['nodes']:
                if n['id'] in ids:
                    row={'id':str(uuid4()),'node_id':n['id'],'node_type':n['data']['type'],'title':n['data']['title'],'status':'succeeded','error':None}
                    if n['id']=='extract_order':row['outputs']={'__is_success':0 if i==5 and not second and self.mode!='blank_order' else 1,'order_no':'' if i==5 and not second else 'DEMO-001'}
                    if n['id']=='validate_order':row['outputs']={'has_order':not (i==5 and not second)}
                    if n['id']=='retrieve':row['outputs']={'result':[{'content':'公开资料'}] if i==0 or self.mode=='nonempty_no_answer' else []}
                    nodes.append(row)
            # Console detail schema intentionally has no workflow_id: Dify1.17.1.
            self.runs[rid]={'detail':{'id':rid,'status':'succeeded','graph':graph},'trace':{'data':nodes}}
            return response({'event':'message','mode':'advanced-chat','id':mid,'message_id':mid,'conversation_id':cid,'answer':answer,'metadata':{'usage':{'total_tokens':10,'total_price':'0.0001','currency':'USD'}}})
        if '/messages/' in path:
            value=copy.deepcopy(self.messages[path.rsplit('/',1)[-1]])
            if self.mode=='wrong_message_source':value['conversation_id']=str(uuid4())
            return response(value)
        for rid,items in self.runs.items():
            if path.endswith('/'+rid):return response(items['detail'])
            if path.endswith('/'+rid+'/node-executions'):
                if self.mode=='failure_diagnostic_error':return response({'error':'PUBLIC_DIAGNOSTIC_FAILURE'},502)
                return response(items['trace'])
        raise RuntimeError('Unexpected public fixture path')
