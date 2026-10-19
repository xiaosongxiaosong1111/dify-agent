"""Approved, independent single-review resources. Each write is checkpointed once."""
import asyncio,copy,re,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .plan_drafts import DraftRoute
from .human_runtime_plan import source
from .human_runtime_stream import HumanStream,collect,render
from .schedule_observation import CredentialSnapshot
from .schedule_enable import configuration_digest
from .run_diagnostics import binding
from .diagnostic_graph_source import fingerprint
from .workflow_waiting import canonical
from .dify import DifyError
from .workflow_waiting import stamp,TERMINAL

NOTE='本次仅创建独立纯模板审核应用并采集等待表单；不覆盖任务已有应用或环境Key，不提交决定。实际表单来源核对不代表业务通过；指定审核人权限尚未强制限制；人工动作另行确认提交、恢复须主动核对，失败资源保留供核对，不自动重试或清理。'
PUBLIC={'id','task_id','plan_id','revision','environment_id','environment_url','application_name','app_id','published_workflow_id','workflow_run_id','state','stage','attempts','approved_at','updated_at','message','form','business_verified','note','observed_status','observed_at','human_submission_attempted','human_decision_id','resume_evidence'}


class Execute(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    resource_token:str=Field(min_length=64,max_length=64)
    approve_resource_plan:StrictBool


class OwnedCredentials:
    """Only the newly created application's service key; no environment replacement."""
    def __init__(self,env_id,credentials,key):self.env_id=env_id;self.credentials=credentials;self.key=key
    def secret(self,owner,field):
        if owner!=self.env_id:return None
        return self.key if field=='service_api_key' else self.credentials.secret(owner,field)


class HumanRuntimeExecution:
    def __init__(self,host):self.h=host
    def public(self,row):
        result={k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}
        if isinstance(result.get('form'),dict):
            allowed={'form_id','node_id','workflow_run_id','published_workflow_id','content','actions','expiration_time','inputs','source_verified','business_verified','active'}
            result['form']={k:v for k,v in result['form'].items() if k in allowed}
        return result
    def recover(self):
        for row in self.h.store.list('human_runtime_run'):
            if row.get('state')=='executing':
                row.update(state='unknown',message='执行处理中断，保留已知资源与尝试记录，没有重放；请核对原目标。',updated_at=self.h.now())
                self.h.store.put('human_runtime_run',row['id'],row)

    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.get('/api/tasks/{item_id}/human-runtime/runs')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('human_runtime_run') if r.get('task_id')==item_id];rows.sort(key=lambda r:r.get('approved_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':NOTE}

        @router.get('/api/tasks/{item_id}/human-runtime/runs/{run_id}/state')
        async def observe(item_id:str,run_id:str):
            with h.store.lock:
                h.get_task(item_id);row=h.store.get('human_runtime_run',run_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该人工运行。')
                if row.get('state') in {'executing','submitting_decision'}:raise HTTPException(409,'资源仍执行中，请等原操作返回，不并发核对。')
                env=copy.deepcopy(h.store.get('environment',row['environment_id']));rid=canonical(row.get('workflow_run_id'));appid=canonical(row.get('app_id'))
                if not env or binding(env)!=row.get('environment_binding') or not rid or not appid:raise HTTPException(409,'原环境或运行标识未可靠保存，不能猜另一个目标。')
                credentials=CredentialSnapshot(h.store,env['id']);original=stamp(row)
            def unchanged():
                with h.store.lock:
                    current=h.store.get('environment',env['id']);record=h.store.get('human_runtime_run',run_id)
                    if not current or binding(current)!=binding(env) or not credentials.unchanged(h.store) or not record or stamp(record)!=original:raise HTTPException(409,'原连接或运行记录改变，未保存旧状态。')
            try:
                unchanged();value=await asyncio.wait_for(h.DifyClient(env,credentials).workflow_run_detail(appid,rid),timeout=60);unchanged()
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except TimeoutError:raise HTTPException(504,'原人工运行状态读取超时，没有重新运行或提交决定。') from None
            status=value.get('status') if isinstance(value,dict) else None
            if not isinstance(value,dict) or canonical(value.get('id'))!=rid or not isinstance(status,str) or status not in TERMINAL|{'paused','running'}:raise HTTPException(502,'原运行状态或标识不可信，不保存原文。')
            with h.store.lock:
                unchanged();row['observed_status']=status;row['observed_at']=h.now()
                if status in TERMINAL:
                    row.update(state='platform_finished',message='只读看到原运行终态，仍未核对业务输出，不代表本次人工决定或恢复成功。')
                    if row.get('form'):row['form']['active']=False
                h.store.put('human_runtime_run',row['id'],row)
            return self.public(row)

        @router.post('/api/tasks/{item_id}/human-runtime/{plan_id}/execute')
        async def execute(item_id:str,plan_id:str,payload:Execute):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);h.require_intake(task)
                plan=h.store.get('human_runtime_plan',plan_id)
                if not plan or plan.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该人工资源方案。')
                if plan.get('revision')!=payload.revision or plan.get('resource_token')!=payload.resource_token:raise HTTPException(409,'批准与方案哈希或修订不一致。')
                if not payload.approve_resource_plan:raise HTTPException(422,'请先明确接受新应用、发布、独立Key和一次试跑的具体影响与限制。')
                if not plan.get('execution_available') or plan.get('state')!='prepared_unapproved':raise HTTPException(409,'此方案不具备当前执行能力或已处理；请重新准备，不能重放。')
                if any(r.get('task_id')==item_id and r.get('state') in {'executing','waiting_human','unknown','submitting_decision','awaiting_resume'} for r in h.store.list('human_runtime_run')):raise HTTPException(409,'本任务已有人工运行处理中、等待或未知，先核对原资源，不另建应用或重跑。')
                env=copy.deepcopy(h.environment(task));frozen=source(h,task)
                def local_context():
                    current=h.get_task(item_id);h.require_revision(current,plan['revision']);h.require_intake(current)
                    original=h.store.get('environment',plan['environment_id'])
                    if not current.get('requirements_confirmed') or not current.get('configuration_confirmed') or current.get('environment_id')!=plan['environment_id'] or not original or original.get('version')!='1.17.1' or binding(original)!=plan['environment_binding'] or source(h,current)['artifact_sha256']!=plan['artifact_sha256']:raise HTTPException(409,'确认、成果或原环境已改变，不执行旧人工运行方案。')
                local_context();credentials=CredentialSnapshot(h.store,env['id'])
                row={'id':str(uuid.uuid4()),'task_id':item_id,'plan_id':plan_id,'revision':plan['revision'],'environment_id':env['id'],'environment_url':env['base_url'],'environment_binding':binding(env),'application_name':plan['application_name'],'artifact_sha256':plan['artifact_sha256'],'state':'executing','stage':'preflight','attempts':{},'approved_at':h.now(),'updated_at':h.now(),'business_verified':False,'note':NOTE}
                plan['state']='approved_executing'
                h.store.put_many([('human_runtime_plan',plan_id,plan),('human_runtime_run',row['id'],row)])
            client=h.DifyClient(env,credentials)
            def save():row['updated_at']=h.now();h.store.put('human_runtime_run',row['id'],row)
            def check():
                with h.store.lock:
                    local_context()
                    if not credentials.unchanged(h.store):raise HTTPException(409,'原管理凭据改变，不改用新连接继续旧操作。')
            def mark(stage):
                check()
                with h.store.lock:
                    if row['attempts'].get(stage):raise HTTPException(409,'该写入已经尝试，不重复。')
                    row['stage']=stage;row['attempts'][stage]=1;save()
            async def published():
                check();value=await client.published_workflow(row['app_id']);check()
                try:matched=isinstance(value,dict) and canonical(value.get('id')) and fingerprint(value.get('graph'))==fingerprint(frozen['root']['workflow']['graph']) and configuration_digest(value)==configuration_digest(frozen['root']['workflow'])
                except (ValueError,KeyError,TypeError):matched=False
                if not matched or row.get('published_workflow_id') and canonical(value['id'])!=row['published_workflow_id']:raise DifyError('实际发布ID、完整核心图或特性变量未证明与批准成果一致，不创建运行。')
                row['published_workflow_id']=canonical(value['id']);save()
            async def perform():
                check();await client.test();check()
                mark('import');result=await client.import_new(frozen['outbound_dsl'],plan['application_name'])
                if isinstance(result,dict) and canonical(result.get('app_id')):row['app_id']=canonical(result['app_id']);save()
                check()
                if not isinstance(result,dict) or result.get('status')!='completed' or not row.get('app_id'):raise DifyError('新应用导入未明确完成，可能已有遗留资源；不确认警告、不重复导入。')
                mark('publish');await client.request('POST',f"/console/api/apps/{row['app_id']}/workflows/publish",credential='console_token',json={'marked_name':'Sierra review','marked_comment':'用户批准的独立纯模板审核运行。'})
                await published();mark('create_key');item=await client.request('POST',f"/console/api/apps/{row['app_id']}/api-keys",credential='console_token',json={})
                key=item.get('token') if isinstance(item,dict) else None
                if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}',key) or not canonical(item.get('id')):raise DifyError('新应用Key回执不可信，可能已有Key；不重复创建或替换环境Key。')
                row['key_id']=canonical(item['id']);h.store.put_with_secrets('human_runtime_run',row['id'],row,{'service_api_key':key});check()
                await published()
                secret_client=h.DifyClient(env,OwnedCredentials(env['id'],credentials,key))
                parser=HumanStream(row['published_workflow_id'],plan['review'],render(frozen['root'],plan['input']),[key,*credentials.values.values()])
                mark('run')
                try:form,token=await collect(secret_client,plan['input'],'sierra-human-'+row['id'],parser)
                except DifyError:
                    if parser.run_id:row['workflow_run_id']=parser.run_id;save()
                    raise
                row['workflow_run_id']=form['workflow_run_id'];save();check()
                detail=await client.workflow_run_detail(row['app_id'],row['workflow_run_id']);check()
                if not isinstance(detail,dict) or canonical(detail.get('id'))!=row['workflow_run_id'] or detail.get('status')!='paused' or fingerprint(detail.get('graph'))!=fingerprint(frozen['root']['workflow']['graph']):raise DifyError('等待运行的实际执行核心图或状态无法核对，表单未采纳，不提交或重跑。')
                row.update(form=form,state='waiting_human',stage='waiting_human',message='实际返回单个审核等待表单，发布标识、执行核心图与对象已核对；尚未提交决定或验收业务。')
                h.store.put_with_secrets('human_runtime_run',row['id'],row,{'form_token':token})
                check();return self.public(row)
            try:return await asyncio.wait_for(perform(),timeout=180)
            except BaseException as exc:
                row.update(state='unknown' if row['attempts'] else 'not_dispatched',updated_at=h.now(),message='人工资源操作未完成，保留已知App／Run与单次尝试；结果需核对，没有自动重试、提交或清理。' if row['attempts'] else '派发前连接或方案核对失败，未创建资源。');save()
                if isinstance(exc,HTTPException):raise
                if isinstance(exc,DifyError):raise HTTPException(502,str(exc)) from None
                if isinstance(exc,(TimeoutError,asyncio.CancelledError)):raise HTTPException(504,row['message']) from None
                raise HTTPException(500,'人工资源处理遇到本机异常，已保存安全检查点；不重试。') from None
        h.app.include_router(router)
