"""Explicit approval for enabling one already-published schedule; never publish."""
import asyncio,copy,uuid
from fastapi import APIRouter,HTTPException
from .plan_drafts import DraftRoute
from .schedule_stop import Prepare,Execute,binding,digest
from .schedule_observation import CredentialSnapshot,local_source,triggers
from .schedule_trigger import preserved
from .dsl_roundtrip import parse
from .diagnostic_graph_source import fingerprint
from .dify import DifyError
from .conversation_state import safe_text

NOTE='启用后按所列时区与频次持续调度，可能产生模型、检索和接口费用；Sierra单次试跑预算不限制平台后续定时运行。没有自动到期停用，不发布或覆盖应用，不手动运行。只尝试一次启用；结果未知不自动重试。停用不取消已入队请求。'
PUBLIC={'id','task_id','revision','observation_id','resource_token','state','app_id','trigger_id','entry_id','environment_id','environment_label','published_workflow_id','schedule','node_types','max_write_attempts','max_remote_reads','action','automatic_retry','recurring','automatic_stop','business_verified','created_at','approved_at','completed_at','write_attempted','result','message','note','reconciled_at','reconciled_state'}


def configuration_digest(workflow):
    """No missing fields, masked secrets or implicit default equivalence."""
    keys=('features','environment_variables','conversation_variables')
    if not isinstance(workflow,dict) or any(k not in workflow for k in keys) or not isinstance(workflow['features'],dict) or any(not isinstance(workflow[k],list) for k in keys[1:]):raise ValueError('发布特性与变量未完整提供，不能猜测默认值或受保护变量。')
    return digest({k:workflow[k] for k in keys})


def pending_operations(store,target,exclude=None):
    return any(r.get('id')!=exclude and (r.get('environment_binding_sha256'),r.get('app_id'),r.get('trigger_id'))==target and r.get('state') in {'executing','unknown','not_confirmed'} for kind in ('schedule_enable','schedule_stop') for r in store.list(kind))


class ScheduleEnable:
    def __init__(self,host):self.h=host

    def public(self,row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}

    def recover(self):
        for row in self.h.store.list('schedule_enable'):
            if row.get('state')=='executing':
                row.update(state='unknown' if row.get('write_attempted') else 'not_dispatched',completed_at=self.h.now(),message='启用处理中断，没有重放；请只读核对原目标。')
                self.h.store.put('schedule_enable',row['id'],row)

    def profile(self,row):
        env=self.h.store.get('environment',row['environment_id'])
        if not env or env.get('version')!='1.17.1' or binding(env)!=row['environment_binding_sha256']:raise HTTPException(409,'原环境变化或不可用，不替换管理连接。')
        return copy.deepcopy(env)

    def context(self,row,credentials=None):
        h=self.h;task=h.get_task(row['task_id']);h.require_revision(task,row['revision'])
        h.require_intake(task)
        env=self.profile(row)
        if task.get('environment_id')!=env['id'] or not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or local_source(h,task)!=row['source']:raise HTTPException(409,'需求、配置、成果或目标环境已变化，请重新核对并准备启用方案。')
        try:
            root=parse(h.artifact_path(task).read_text(encoding='utf-8'),task['app_type'])
            if configuration_digest(root['workflow'])!=row['configuration_sha256']:raise ValueError('配置改变')
        except (ValueError,OSError,KeyError,TypeError):raise HTTPException(409,'当前完整特性或变量配置无法核对，不继续启用旧方案。') from None
        if credentials and not credentials.unchanged(h.store):raise HTTPException(409,'管理凭据变化，不用新凭据继续旧启用操作。')
        return env

    def selected(self,row,value):
        records=triggers(value,row['entry_id'])['records']
        if len(records)!=1 or records[0]['trigger_id']!=row['trigger_id'] or records[0]['status'] not in {'enabled','disabled'}:raise DifyError('对应触发器缺失、重复、限流或未知，未猜选其他目标或解除限流。')
        return records[0]

    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.post('/api/tasks/{item_id}/schedule-enable/prepare')
        def prepare(item_id:str,payload:Prepare):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision)
                h.require_intake(task)
                source=local_source(h,task);env=h.environment(task)
                if env.get('version')!='1.17.1':raise HTTPException(422,'仅适配Dify 1.17.1，不猜测其他版本启用行为。')
                if not task.get('requirements_confirmed') or not task.get('configuration_confirmed'):raise HTTPException(409,'先确认当前需求与配置，再准备持续调度方案。')
                obs=h.store.get('schedule_observation',payload.observation_id)
                if not obs or obs.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该观察记录。')
                if obs.get('revision')!=payload.revision or obs.get('artifact_sha256')!=source['artifact_sha256'] or obs.get('environment_id')!=env['id'] or obs.get('environment_binding_sha256')!=binding(env) or not obs.get('core_graph_matched'):raise HTTPException(409,'观察不是当前成果与当前环境的匹配发布图，请重新只读核对。')
                records=(obs.get('trigger') or {}).get('records',[])
                if len(records)!=1 or records[0].get('status')!='disabled':raise HTTPException(422,'只对当前观察中明确停用的唯一触发器准备启用；限流／未知或已启用不猜测处理。')
                try:app_id=str(uuid.UUID(obs['app_id']));trigger_id=str(uuid.UUID(records[0]['trigger_id']));published_id=str(uuid.UUID(obs['published_workflow_id']))
                except (ValueError,KeyError,TypeError,AttributeError):raise HTTPException(422,'观察缺少可信应用／触发器／发布UUID。') from None
                root=parse(h.artifact_path(task).read_text(encoding='utf-8'),task['app_type'])
                entry=next(n for n in root['workflow']['graph']['nodes'] if n['id']==source['entry_id'])
                cfg=preserved(entry['data'])
                label=env.get('name');secrets=[h.store.secret(env['id'],key) for key in h.SECRET_FIELDS]
                row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':payload.revision,'observation_id':obs['id'],'app_id':app_id,'trigger_id':trigger_id,'entry_id':source['entry_id'],'environment_id':env['id'],'environment_binding_sha256':binding(env),'environment_label':label if safe_text(label,255) and not any(s and s in label for s in secrets) else '保存的Dify环境','source':source,'published_workflow_id':published_id,'schedule':cfg,'node_types':sorted({n['data']['type'] for n in root['workflow']['graph']['nodes']}),'action':'enable','max_write_attempts':1,'max_remote_reads':4,'automatic_retry':False,'recurring':True,'automatic_stop':False,'business_verified':False,'note':NOTE,'created_at':h.now()}
                row['configuration_sha256']=configuration_digest(root['workflow']);row['resource_token']=digest(row);row.update(state='prepared',write_attempted=False,approved_at=None)
                h.store.put('schedule_enable',row['id'],row);return self.public(row)

        @router.get('/api/tasks/{item_id}/schedule-enable')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('schedule_enable') if r.get('task_id')==item_id];rows.sort(key=lambda r:r.get('created_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':NOTE}

        @router.post('/api/tasks/{item_id}/schedule-enable/{plan_id}/execute')
        async def execute(item_id:str,plan_id:str,payload:Execute):
            with h.store.lock:
                row=h.store.get('schedule_enable',plan_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该具体启用方案。')
                h.require_revision(h.get_task(item_id),payload.revision)
                if payload.revision!=row['revision'] or payload.resource_token!=row['resource_token']:raise HTTPException(409,'批准与具体方案或修订不一致。')
                if not payload.approve_resource_plan:raise HTTPException(422,'请明确接受具体持续调度方案及费用影响。')
                if row['state']!='prepared':raise HTTPException(409,'方案已处理或结果未知，不重复启用；请只读核对。')
                target=(row['environment_binding_sha256'],row['app_id'],row['trigger_id'])
                if pending_operations(h.store,target,row['id']):raise HTTPException(409,'同一目标存在启停处理中或未知结果，先核对原操作，不追加启用。')
                env=self.context(row);credentials=CredentialSnapshot(h.store,env['id']);row.update(state='executing',approved_at=h.now());h.store.put('schedule_enable',row['id'],row)
            client=h.DifyClient(env,credentials)
            def check():
                with h.store.lock:self.context(row,credentials)
            def save():
                with h.store.lock:h.store.put('schedule_enable',row['id'],row)
            async def published():
                check();value=await client.published_workflow(row['app_id']);check()
                graph=fingerprint(value.get('graph')) if isinstance(value,dict) else None
                if not isinstance(value,dict) or value.get('id')!=row['published_workflow_id'] or not graph or graph!=row['source']['graph']:raise DifyError('实际发布版本或核心图改变，不能启用旧方案。')
                try:matched=configuration_digest(value)==row['configuration_sha256']
                except (ValueError,TypeError):matched=False
                if not matched:raise DifyError('发布特性或环境／会话变量与当前成果未证明完全一致；原生默认补充或秘密遮罩也不能猜作相等，请读取实际DSL并复核。')
            async def enable():
                await published();check();before=self.selected(row,await client.app_triggers(row['app_id']));check()
                if before['status']=='enabled':return 'already_enabled',before
                row['write_attempted']=True;save();await client.enable_app_trigger(row['app_id'],row['trigger_id']);check()
                after=self.selected(row,await client.app_triggers(row['app_id']));check();await published()
                return ('enabled' if after['status']=='enabled' else 'not_confirmed'),after
            try:
                state,result=await asyncio.wait_for(enable(),timeout=90)
                row.update(state=state,result=result,completed_at=h.now(),message='本次读取看到指定触发器已启用；持续调度无自动停用，尚未证明实际执行或业务通过。' if state in {'enabled','already_enabled'} else '已尝试启用但未证明生效，没有自动重试。');save();return self.public(row)
            except BaseException as exc:
                row.update(state='unknown' if row.get('write_attempted') else 'not_dispatched',completed_at=h.now(),message='启用结果未知，请只读核对，必要时准备明确停用；没有重试。' if row.get('write_attempted') else '启用前核对失败，未尝试启用写入。');save()
                if isinstance(exc,HTTPException):raise
                if isinstance(exc,DifyError):raise HTTPException(502,str(exc)) from None
                if isinstance(exc,asyncio.TimeoutError):raise HTTPException(504,row['message']) from None
                raise

        @router.get('/api/tasks/{item_id}/schedule-enable/{plan_id}/reconcile')
        async def reconcile(item_id:str,plan_id:str):
            with h.store.lock:
                h.get_task(item_id);row=h.store.get('schedule_enable',plan_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该启用方案。')
                if row['state']=='executing':raise HTTPException(409,'启用仍处理中，不并发核对。')
                env=self.profile(row);credentials=CredentialSnapshot(h.store,env['id']);stamp=digest(row)
            try:
                result=self.selected(row,await asyncio.wait_for(h.DifyClient(env,credentials).app_triggers(row['app_id']),timeout=60))
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except asyncio.TimeoutError:raise HTTPException(504,'原目标只读核对超时，没有追加启用。') from None
            with h.store.lock:
                if not credentials.unchanged(h.store) or binding(self.profile(row))!=binding(env) or digest(h.store.get('schedule_enable',plan_id))!=stamp:raise HTTPException(409,'连接或记录变化，不保存旧核对。')
                row.update(reconciled_at=h.now(),reconciled_state=result['status'])
                if row['state'] in {'unknown','not_confirmed'}:row.update(state='enabled_observed_later' if result['status']=='enabled' else 'disabled_observed_later',message='后续只读观察到触发器状态，不能归因于原启用，也不证明执行版本或业务成功。')
                h.store.put('schedule_enable',row['id'],row)
            return self.public(row)
        h.app.include_router(router)
