"""Concrete, explicitly approved one-trigger stop. Never enable/publish/retry."""
import asyncio,copy,hashlib,json,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt,StrictStr,Field
from .plan_drafts import DraftRoute
from .conversation_state import safe_text
from .schedule_observation import CredentialSnapshot,triggers
from .dify import DifyError

NOTE='仅停用方案中指定的一个触发器，不删除／覆盖应用，不启用或发布。停用只阻止未来轮询派发；已入队或执行中的请求及其费用可能继续。失败／未知不自动重试写入。'
PUBLIC_FIELDS={'id','task_id','revision','observation_id','source_revision','source_observed_at','app_id','trigger_id','entry_id','environment_id','environment_binding_sha256','environment_label','action','max_write_attempts','max_remote_reads','automatic_retry','ownership_verified','note','created_at','resource_token','state','write_attempted','approved_at','result','completed_at','message','reconciled_at','reconciled_state'}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def binding(env):return hashlib.sha256(json.dumps([env['id'],env['base_url'],env['version']]).encode()).hexdigest()


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    observation_id:StrictStr=Field(min_length=1,max_length=64)


class Execute(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    resource_token:StrictStr=Field(min_length=64,max_length=64)
    approve_resource_plan:StrictBool


class ScheduleStop:
    def __init__(self,host):self.h=host

    def recover(self):
        for row in self.h.store.list('schedule_stop'):
            if row.get('state')=='executing':
                row.update(state='unknown' if row.get('write_attempted') else 'not_dispatched',message='上次停用处理中断，请只读核对原目标；没有重放停用请求。',completed_at=self.h.now())
                self.h.store.put('schedule_stop',row['id'],row)

    def profile(self,plan):
        env=self.h.store.get('environment',plan['environment_id'])
        if not env or env.get('version')!='1.17.1' or binding(env)!=plan['environment_binding_sha256']:raise HTTPException(409,'原观察环境已变化或不可用，未改用当前任务的新环境停用；请先核对原环境。')
        return copy.deepcopy(env)

    def public(self,row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC_FIELDS}

    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.post('/api/tasks/{item_id}/schedule-stop/prepare')
        def prepare(item_id:str,payload:Prepare):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision)
                if task['app_type']!='workflow':raise HTTPException(422,'定时停用只适配Workflow，不自动改变类型。')
                observation=h.store.get('schedule_observation',payload.observation_id)
                if not observation or observation.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该只读观察。')
                records=(observation.get('trigger') or {}).get('records',[])
                if not observation.get('core_graph_matched') or len(records)!=1 or records[0].get('status') not in {'enabled','disabled','rate_limited'}:raise HTTPException(422,'来源未匹配或触发记录不唯一／未知，不能猜选停用目标，请先明确核对。')
                try:app_id=str(uuid.UUID(observation['app_id']));trigger_id=str(uuid.UUID(records[0]['trigger_id']))
                except (ValueError,KeyError,TypeError,AttributeError):raise HTTPException(422,'观察缺少可信App／触发器UUID。') from None
                plan={'id':str(uuid.uuid4()),'task_id':item_id,'revision':payload.revision,'observation_id':observation['id'],'source_revision':observation['revision'],'source_observed_at':observation['created_at'],'app_id':app_id,'trigger_id':trigger_id,'entry_id':observation['entry_id'],'environment_id':observation['environment_id'],'environment_binding_sha256':observation['environment_binding_sha256'],'action':'disable','max_write_attempts':1,'max_remote_reads':2,'automatic_retry':False,'ownership_verified':False,'note':NOTE,'created_at':h.now()}
                env=self.profile(plan);label=env.get('name')
                secrets=[h.store.secret(env['id'],key) for key in h.SECRET_FIELDS]
                plan['environment_label']=label if safe_text(label,255) and not any(secret and secret in label for secret in secrets) else '保存的Dify环境'
                plan['resource_token']=digest(plan);plan.update(state='prepared',write_attempted=False,approved_at=None,result=None)
                h.store.put('schedule_stop',plan['id'],plan)
                return self.public(plan)

        @router.get('/api/tasks/{item_id}/schedule-stop')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('schedule_stop') if r.get('task_id')==item_id]
            rows.sort(key=lambda r:r.get('created_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':NOTE}

        @router.post('/api/tasks/{item_id}/schedule-stop/{plan_id}/execute')
        async def execute(item_id:str,plan_id:str,payload:Execute):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision)
                row=h.store.get('schedule_stop',plan_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该具体停用方案。')
                if row['revision']!=payload.revision or payload.resource_token!=row['resource_token']:raise HTTPException(409,'停用方案／修订已变化，未批准其他资源。')
                if not payload.approve_resource_plan:raise HTTPException(422,'请明确接受已展示的具体停用资源方案，未发停用请求。')
                if row['state']!='prepared':raise HTTPException(409,'该方案已经处理或结果未确定，不重复写入；请只读核对原目标。')
                target=(row['environment_binding_sha256'],row['app_id'],row['trigger_id'])
                if any(r['id']!=row['id'] and (r.get('environment_binding_sha256'),r.get('app_id'),r.get('trigger_id'))==target and r.get('state') in {'executing','unknown','not_confirmed'} for r in h.store.list('schedule_stop')):raise HTTPException(409,'同一目标已有停用处理中或结果未确定，请只读核对原方案，不另发写入。')
                if any((r.get('environment_binding_sha256'),r.get('app_id'),r.get('trigger_id'))==target and r.get('state')=='executing' for r in h.store.list('schedule_enable')):raise HTTPException(409,'同一目标启用仍处理中，先等待结果，不并发启停。')
                env=self.profile(row);credentials=CredentialSnapshot(h.store,env['id'])
                row.update(state='executing',approved_at=h.now());h.store.put('schedule_stop',row['id'],row)
            client=h.DifyClient(env,credentials)
            def context():
                with h.store.lock:
                    current=self.profile(row)
                    if not credentials.unchanged(h.store) or binding(current)!=binding(env):raise HTTPException(409,'停用期间管理连接已变化，不用新凭据继续旧目标。')
            def selected(value):
                parsed=triggers(value,row['entry_id']);matched=[r for r in parsed['records'] if r['trigger_id']==row['trigger_id']]
                if len(matched)!=1 or matched[0]['status']=='unknown':raise DifyError('原目标触发器缺失、重复或状态未知，未改停用其他记录。')
                return matched[0]
            def save():
                with h.store.lock:h.store.put('schedule_stop',row['id'],row)
            try:
                async def stop():
                    context();before=selected(await client.app_triggers(row['app_id']));context()
                    if before['status']=='disabled':return 'already_disabled',before
                    row['write_attempted']=True;save()
                    await client.disable_app_trigger(row['app_id'],row['trigger_id'])
                    context();after=selected(await client.app_triggers(row['app_id']));context()
                    return ('disabled' if after['status']=='disabled' else 'not_confirmed'),after
                state,result=await asyncio.wait_for(stop(),timeout=60)
                row.update(state=state,result=result,completed_at=h.now(),message='本次核对目标触发器已停用，已入队请求未取消。' if state in {'disabled','already_disabled'} else '请求已尝试，但核对未证明停用；没有自动重试。');save()
                return self.public(row)
            except BaseException as exc:
                row.update(state='unknown' if row.get('write_attempted') else 'not_dispatched',completed_at=h.now(),message='本次停用结果未确定，请只读核对原目标，不自动重试。' if row.get('write_attempted') else '停用前核对失败，未尝试停用写入。');save()
                if isinstance(exc,HTTPException):raise
                if isinstance(exc,DifyError):raise HTTPException(502,str(exc)) from None
                if isinstance(exc,asyncio.TimeoutError):raise HTTPException(504,row['message']) from None
                raise

        @router.get('/api/tasks/{item_id}/schedule-stop/{plan_id}/reconcile')
        async def reconcile(item_id:str,plan_id:str):
            with h.store.lock:
                h.get_task(item_id);row=h.store.get('schedule_stop',plan_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该具体停用方案。')
                if row['state']=='executing':raise HTTPException(409,'停用仍在处理，先等待本次结果，不并发核对或重发。')
                env=self.profile(row);credentials=CredentialSnapshot(h.store,env['id'])
                stamp=digest(row)
            try:value=await asyncio.wait_for(h.DifyClient(env,credentials).app_triggers(row['app_id']),timeout=60)
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except asyncio.TimeoutError:raise HTTPException(504,'原目标只读核对超时，没有重发停用。') from None
            try:parsed=triggers(value,row['entry_id'])
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            matches=[r for r in parsed['records'] if r['trigger_id']==row['trigger_id']]
            state=matches[0]['status'] if len(matches)==1 else 'missing' if not matches else 'ambiguous'
            with h.store.lock:
                if not credentials.unchanged(h.store) or binding(self.profile(row))!=binding(env) or digest(h.store.get('schedule_stop',plan_id))!=stamp:raise HTTPException(409,'只读核对期间连接或停用记录变化，未写入旧观察。')
                row.update(reconciled_at=h.now(),reconciled_state=state)
                if state=='disabled' and row['state'] in {'unknown','not_confirmed'}:
                    row.update(state='disabled_observed_later',message='后续只读看到指定触发器已停用，不能归因于原停用请求，也不取消已入队执行。')
                h.store.put('schedule_stop',row['id'],row)
            return self.public(row)
        h.app.include_router(router)
