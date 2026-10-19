"""Explicit independent local task from a saved target draft; no Dify writes."""
import copy,uuid,json,re
from datetime import datetime
from fastapi import APIRouter,HTTPException,Path as ApiPath
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .agent_environment_mapping import MappingRoute,MappingRequest,DRAFT_KIND
from .dsl_roundtrip import digest,parse

COPY_KIND='environment_mapping_copy'


class CopyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(gt=0)
    draft_revision:StrictInt=Field(gt=0)
    preview_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    scope_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    operation_id:str=Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
    name:str=Field(min_length=1,max_length=100)
    acknowledge_local_copy:StrictBool=False
    acknowledge_scope:StrictBool=False


class EnvironmentMappingCopy:
    def __init__(self,h):self.h=h

    def target_for_receipt(self,item_id,operation_id,receipt):
        h=self.h;key=item_id+':'+operation_id
        if not isinstance(receipt,dict) or receipt.get('id')!=key or receipt.get('source_task_id')!=item_id:raise HTTPException(409,'创建回执归属异常，不读取未知结果。')
        target_id=receipt.get('target_task_id')
        target=h.store.get('task',target_id) if isinstance(target_id,str) else None
        if not isinstance(target,dict) or target.get('id')!=target_id or target.get('app_type')!='agent':raise HTTPException(409,'创建回执的目标任务缺失或身份异常，不自动重建。')
        origin=target.get('mapping_origin')
        if not isinstance(origin,dict) or origin.get('operation_id')!=operation_id or origin.get('source_task_id')!=item_id or origin.get('verification')!='local_mapping_task_only':raise HTTPException(409,'创建回执与目标任务不一致，不读取未知结果。')
        return target

    def history(self,task):
        h=self.h;prefix=task['id']+':'
        with h.store.connect() as db:
            total=db.execute("SELECT count(*) FROM objects WHERE kind=? AND substr(id,1,?)=?",(COPY_KIND,len(prefix),prefix)).fetchone()[0]
            rows=db.execute("SELECT id,CASE WHEN length(CAST(value AS BLOB))<=16000 THEN value ELSE NULL END FROM objects WHERE kind=? AND substr(id,1,?)=? ORDER BY rowid DESC LIMIT 20",(COPY_KIND,len(prefix),prefix)).fetchall()
        result=[];invalid=0
        for key,raw in rows:
            try:
                r=json.loads(raw);operation=key[len(prefix):]
                if not isinstance(r,dict) or r.get('id')!=key or r.get('source_task_id')!=task['id'] or str(uuid.UUID(operation,version=4))!=operation or uuid.UUID(operation).version!=4:raise ValueError()
                stamp=r['created_at']
                if not isinstance(stamp,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',stamp) or datetime.fromisoformat(stamp.replace('Z','+00:00')).utcoffset() is None:raise ValueError()
                target_id=r.get('target_task_id')
                if not isinstance(target_id,str):raise ValueError()
                target=h.store.get('task',target_id)
                if not isinstance(target,dict) or target.get('id')!=target_id or target.get('app_type')!='agent':raise ValueError()
                origin=target.get('mapping_origin')
                if not isinstance(origin,dict) or origin.get('source_task_id')!=task['id'] or origin.get('operation_id')!=operation or origin.get('verification')!='local_mapping_task_only':raise ValueError()
                old=origin.get('source_revision');current=target.get('revision');name=target.get('name')
                if any(type(v) is not int or not 1<=v<=9007199254740991 for v in (old,current)) or not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError()
                result.append({'operation_id':operation,'target_task_id':target_id,'target_name':name,'target_revision':current,'source_revision':old,'created_at':stamp})
            except (ValueError,KeyError,TypeError,AttributeError):invalid+=1
        return {'total':total,'shown':len(result),'invalid_in_window':invalid,'truncated':total>len(rows),'rows':result,
                'verification':'local_mapping_copy_receipts_only','note':'最多读取最新20条来源专属回执；目标显示为当前本机任务，不证明Dify导入、运行或业务通过。损坏或已失联记录不作为可打开任务。'}

    def scope(self,task):
        h=self.h;mapper=h.agent_environment_mapping
        record=h.store.get(DRAFT_KIND,task['id']);counter=mapper.counter(record,task['id'])
        if not record:raise HTTPException(422,'请先保存完整目标映射预览，再准备独立本机任务。')
        state=mapper.state(task)
        if not state['restorable']:raise HTTPException(409,state['blocker'] or '映射进度已变化，请重新核对。')
        requirements=task.get('requirements')
        if not isinstance(requirements,dict) or set(requirements)!=set(h.REQ_KEYS) or any(not isinstance(v,str) for v in requirements.values()):raise HTTPException(422,'来源需求结构不完整，不能只复制部分内容。')
        counts={}
        for key in ('materials','test_cases','versions','runs','confirmations'):
            rows=task.get(key,[])
            if not isinstance(rows,list):raise HTTPException(422,'来源材料、样例或历史清单异常，不能猜测复制范围。')
            counts[key]=len(rows)
        scope={'source_task_id':task['id'],'source_revision':task['revision'],'draft_revision':counter,
               'preview_token':record['preview_token'],'target_environment_id':record['payload']['target_environment_id'],
               'existing_copy_receipt_count':self.history(task)['total'],'not_copied':counts,'copied':['八项需求文字（重新确认）','完整目标DSL及手动修改','目标模型配置与Agent生成建议','原模拟与待验证条件'],
               'note':'只创建独立本机任务；材料、测试样例、版本、运行和确认记录仍保留在来源任务，不复制或视为新任务证据。需求中的原材料引用及原资源方案文字未自动改写，必须重新核对。新任务无产物、Dify应用、审批或运行结果，不请求Dify，不复制凭据。'}
        scope['scope_token']=digest({'scope':scope,'requirements':requirements})
        return scope

    def register(self):
        h=self.h;router=APIRouter(route_class=MappingRoute)
        @router.get('/api/tasks/{item_id}/environment-mapping/copy-scope')
        def scope(item_id:str):
            with h.store.lock:return self.scope(h.get_task(item_id))

        @router.get('/api/tasks/{item_id}/environment-mapping/copies')
        def history(item_id:str):
            with h.store.lock:return self.history(h.get_task(item_id))

        @router.get('/api/tasks/{item_id}/environment-mapping/copies/{operation_id}')
        def result(item_id:str,operation_id:str=ApiPath(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')):
            with h.store.lock:
                h.get_task(item_id);prior=h.store.get(COPY_KIND,item_id+':'+operation_id)
                if not isinstance(prior,dict) or prior.get('source_task_id')!=item_id:raise HTTPException(404,'没有属于本任务的该次创建回执；不会自动新建。')
                target=self.target_for_receipt(item_id,operation_id,prior)
                return {'task':target,'created':False,'source_unchanged':True,'note':'已读取本次独立本机任务，没有重复创建。'}

        @router.post('/api/tasks/{item_id}/environment-mapping/copy-task',status_code=201)
        def create(item_id:str,payload:CopyRequest):
            with h.store.lock:
                original=h.get_task(item_id);name=payload.name.strip()
                if not name:raise HTTPException(422,'新任务名称不能为空。')
                if not payload.acknowledge_local_copy or not payload.acknowledge_scope:raise HTTPException(422,'请明确确认独立本机任务及材料、样例、历史不继承的范围；这不是导入或运行批准。')
                key=item_id+':'+payload.operation_id;request_digest=digest(payload.model_dump());prior=h.store.get(COPY_KIND,key)
                if prior is not None:
                    if not isinstance(prior,dict) or prior.get('source_task_id')!=item_id or prior.get('request_digest')!=request_digest:raise HTTPException(409,'本次创建标识已有不同记录，不重复创建或覆盖。')
                    target=self.target_for_receipt(item_id,payload.operation_id,prior)
                    return {'task':target,'created':False,'source_unchanged':True,'note':'已读取同次创建的本机任务，没有重复创建。'}
                h.require_idle(original);h.require_revision(original,payload.revision)
                scope=self.scope(original)
                if scope['draft_revision']!=payload.draft_revision or scope['preview_token']!=payload.preview_token or scope['scope_token']!=payload.scope_token:raise HTTPException(409,'映射或复制范围已变化，请重新读取并明确核对。')
                record=h.store.get(DRAFT_KIND,item_id);inputs=MappingRequest.model_validate(record['payload'])
                prepared=h.agent_environment_mapping.prepare(original,inputs)
                if prepared['preview_token']!=payload.preview_token:raise HTTPException(409,'目标上下文已变化，不能沿用旧映射创建任务。')
                stamp=h.now();ident=str(uuid.uuid4());ref_id=str(uuid.uuid4())
                task={'id':ident,'name':name,'app_type':'agent','revision':1,'status':'requirements','intake_required':True,
                      'requirements_confirmed':False,'configuration_confirmed':False,'environment_id':inputs.target_environment_id,
                      'requirements':copy.deepcopy(original['requirements']),'configuration':copy.deepcopy(prepared['configuration']),
                      'messages':[],'materials':[],'versions':[],'runs':[],'planning_runs':[],'test_cases':[],
                      'workflow_plan':None,'agent_plan':copy.deepcopy(prepared['agent_plan']),'plan_source':'environment_mapping_draft',
                      'plan_stale':False,'artifact':None,'dify_app_id':None,'created_at':stamp,'updated_at':stamp}
                content,validation=h.compile_current(task)
                if not validation['valid']:raise HTTPException(422,'独立目标任务不能完整编译，未保存部分任务。')
                reference={'id':ref_id,'task_id':ident,'mode':'agent','environment_id':task['environment_id'],
                           'environment_fingerprint':h.dsl_source_fingerprint(task),'source_app_id':None,'source':'mapping_draft',
                           'filename':'sierra-目标资源待验证.yml','created_at':stamp,'base':parse(content,'agent'),
                           'current':parse(prepared['content'],'agent'),'baseline_note':'本机已保存的待验证环境映射草稿；不是目标Dify实际草稿或实时源应用证据。完整手改字段仍须分析并明确保留，材料引用和资源方案须重新核对。'}
                task['dsl_reference']={k:v for k,v in reference.items() if k not in {'base','current','environment_fingerprint'}}
                task['dsl_reads']=[copy.deepcopy(task['dsl_reference'])]
                task['mapping_origin']={'source_task_id':item_id,'source_revision':original['revision'],'source_reference_id':inputs.reference_id,
                    'source_document_token':inputs.document_token,'draft_revision':payload.draft_revision,'preview_token':payload.preview_token,
                    'operation_id':payload.operation_id,'scope':scope,'verification':'local_mapping_task_only','created_at':stamp}
                task['messages']=[{'role':'assistant','source':'system','created_at':stamp,'content':'已基于明确选择的目标草稿创建独立本机任务。'+scope['note']+' 请重新核对需求、材料与样例、配置和DSL保留方案；未验证模型、知识库、插件或业务效果。'}]
                receipt={'id':key,'source_task_id':item_id,'target_task_id':ident,'request_digest':request_digest,'created_at':stamp}
                h.store.put_many([('task',ident,task),('dsl_reference',ref_id,reference),(COPY_KIND,key,receipt)])
                return {'task':task,'created':True,'source_unchanged':True,'note':'独立本机目标任务已创建；来源保持，仍需重新核对需求、配置与保留方案。'}
        h.app.include_router(router)
