"""Pure public protocol for existing-record diagnosis; not a new business trial."""
import copy
from uuid import uuid4
from support import require

class Synthetic:
    def __init__(self,h,b,mode):
        self.h=h;self.b=b;self.mode=mode;self.native=str(uuid4());self.docs=[str(uuid4()),str(uuid4())]
    async def __call__(self,request):
        from app.dsl_roundtrip import parse
        import httpx,json
        class Stream(httpx.AsyncByteStream):
            def __init__(self,value):self.value=json.dumps(value,ensure_ascii=False).encode()
            async def __aiter__(self):yield self.value
        def response(value,status=200,headers=()):return httpx.Response(status,headers=[('content-type','application/json'),*headers],stream=Stream(value))
        path=request.url.path;b=self.b;t=b.t
        if path=='/console/api/login':return response({'result':'success'},503 if self.mode=='fail_login' else 200,[('set-cookie','access_token=PUBLIC_TRACE_ACCESS12345; Path=/'),('set-cookie','csrf_token=PUBLIC_TRACE_CSRF12345; Path=/')])
        if path=='/console/api/apps':return response({'data':[]})
        if path=='/console/api/workspaces/current/summary':return response({'id':str(uuid4()) if self.mode=='wrong_workspace' else t['workspace_id']})
        task=self.h.get_task(t['task_id']);native=parse(self.h.artifact_path(task).read_text('utf-8'),'advanced-chat')['workflow']
        if '/messages/' in path:return response({'id':t['message_id'],'conversation_id':str(uuid4()) if self.mode=='wrong_message' else t['conversation_id'],'workflow_run_id':self.native})
        if path.endswith('/workflow-runs/'+self.native):return response({'id':self.native,'status':'succeeded','graph':native['graph']})
        if path.endswith('/node-executions'):
            if self.mode=='fail_nodes':return response({'error':'PUBLIC_FAILURE'},502)
            if self.mode=='late_source':
                # Simulate an independent concurrent editor, outside worker's guarded Store.
                from app.storage import Store
                store=Store(self.h.DATA_ROOT);changed=store.get('task',t['task_id']);changed['runs'][0]['result']['answer']='CONCURRENT_PUBLIC_CHANGE';store.put('task',changed['id'],changed)
            ids={'start','intent','retrieve','collect_docs','check_hit','no_hit','no_hit_answer'}
            nodes=[{'id':str(uuid4()),'node_id':n['id'],'node_type':n['data']['type'],'title':n['data']['title'],'status':'succeeded','error':None,**({'outputs':{'result':[]}} if n['id']=='retrieve' else {})} for n in native['graph']['nodes'] if n['id'] in ids]
            return response({'data':nodes})
        if path.endswith('/workflows/publish'):
            value=copy.deepcopy(native)|{'id':str(uuid4())}
            if self.mode=='changed_published':value['graph']['nodes'][0]['data']['title']='different'
            return response(value)
        if path=='/console/api/datasets/'+t['dataset_id']:return response({'id':t['dataset_id'],'indexing_technique':'economy','document_count':2,'available_document_count':1,'permission':'only_me','name':'PRIVATE_NAME_DO_NOT_SAVE','api_key':'PRIVATE_KEY_DO_NOT_SAVE'})
        if path.endswith('/documents'):
            if self.mode=='duplicate_document':self.docs[1]=self.docs[0]
            return response({'data':[{'id':i,'name':'PRIVATE_NAME_DO_NOT_SAVE','indexing_status':'completed','enabled':True,'archived':False} for i in self.docs],'has_more':self.mode=='more_documents','total':3 if self.mode=='more_documents' else 2})
        if path.endswith('/indexing-status'):
            if self.mode=='fail_index_status':return response({'error':'PUBLIC_FAILURE'},502)
            return response({'indexing_status':'error' if self.mode=='index_error' else 'completed','completed_segments':1,'total_segments':1,'error':'PRIVATE_KEY_DO_NOT_SAVE' if self.mode=='index_error' else None,'text':'PRIVATE_CONTENT_DO_NOT_SAVE'})
        raise RuntimeError('Unexpected public path')
