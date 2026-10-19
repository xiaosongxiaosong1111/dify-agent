"""Concrete new pure-text scheduled app publication, with approved one-stop mitigation."""
import asyncio,copy,hashlib,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .plan_drafts import DraftRoute
from .dsl_roundtrip import parse,validate_preserved
from .schedule_observation import local_source,CredentialSnapshot,triggers
from .schedule_trigger import preserved
from .schedule_enable import configuration_digest
from .schedule_stop import digest
from .run_diagnostics import binding
from .diagnostic_graph_source import fingerprint
from .workflow_waiting import canonical,stamp
from .conversation_state import safe_text
from .dify import DifyError
from .human_runtime_plan import contains_saved_secret

NOTE='发布新定时App可能直接启用调度。此方案含一次原新App唯一触发器停用尝试；发布到停用之间可能已有自然派发，停用失败可能继续调度，已入队不能取消。主操作180秒＋停用核对60秒，不保证零运行／停用／宿主免费，试跑预算不限制调度费用。无Key或手动run，不覆盖旧应用，未知不重试或自动删除；后续持续启用须另确认。'
PUBLIC={'id','task_id','revision','resource_token','state','application_name','environment_id','environment_label','environment_url','environment_version','connection_state','artifact_sha256','graph_digest','entry_id','schedule','fixed_result','outbound_dsl','resource_counts','max_remote_reads','max_seconds','automatic_retry','paid_nodes','host_cost_guaranteed_zero','possible_natural_activation','business_verified','created_at','approved_at','completed_at','app_id','published_workflow_id','trigger_id','attempts','reads_attempted','publication_matched','stop_observed','stage','message','note','reconciled_at','reconciled_status','reconciled_core_matched'}


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
class Execute(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    resource_token:str=Field(min_length=64,max_length=64)
    approve_resource_plan:StrictBool
    accept_possible_activation:StrictBool


def source(h,task):
    baseline=local_source(h,task)
    try:
        with h.artifact_path(task).open('rb') as stream:payload=stream.read(2_000_001)
        if len(payload)>2_000_000 or hashlib.sha256(payload).hexdigest()!=baseline['artifact_sha256']:raise ValueError('读取间成果改变或超过2MB，不混用版本。')
        raw=payload.decode('utf-8');root=parse(raw,task['app_type']);workflow=root['workflow'];nodes=workflow['graph']['nodes'];edges=workflow['graph']['edges']
        if not validate_preserved(root)['valid'] or len(nodes)!=3 or sorted(n['data']['type'] for n in nodes)!=['end','template-transform','trigger-schedule']:raise ValueError('首批发布只接定时入口→固定文字模板→文字终点三节点，不静默删掉模型／知识库／HTTP／代码／人审／容器。')
        timer=next(n for n in nodes if n['data']['type']=='trigger-schedule');template=next(n for n in nodes if n['data']['type']=='template-transform');end=next(n for n in nodes if n['data']['type']=='end')
        if len(edges)!=2 or {(e['source'],e['target']) for e in edges}!={(timer['id'],template['id']),(template['id'],end['id'])} or any(n.get('parentId') for n in nodes):raise ValueError('首批仅明确三节点直连，不接其它路径。')
        text=template['data'].get('template')
        if not safe_text(text,16000) or template['data'].get('variables')!=[] or any(s in text for s in ('{{','{%','{#')) or end['data'].get('outputs')!=[{'variable':'result','value_selector':[template['id'],'output']}]:raise ValueError('首批模板须无变量／表达式，终点只返回明确result文字，不猜动态输出。')
        if root.get('dependencies') or any(workflow.get(k) for k in ('environment_variables','conversation_variables','rag_pipeline_variables')):raise ValueError('首批不接插件依赖或附加变量。')
        features=workflow.get('features');allowed={'file_upload','opening_statement','retriever_resource','sensitive_word_avoidance','suggested_questions','suggested_questions_after_answer','speech_to_text','text_to_speech','more_like_this'}
        if not isinstance(features,dict) or set(features)-allowed or features.get('opening_statement') not in (None,'') or features.get('suggested_questions') not in (None,[]):raise ValueError('首批不接额外应用特性／开场白／建议问题。')
        if any(k not in {'opening_statement','suggested_questions'} and (not isinstance(v,dict) or v.get('enabled') is not False) for k,v in features.items()):raise ValueError('首批附加特性须明确关闭。')
        name=root['app'].get('name')
        if not safe_text(name,100) or not name.strip():raise ValueError('应用名称无效或含凭据。')
        return {**baseline,'root':root,'outbound_dsl':raw,'application_name':name,'schedule':preserved(timer['data']),'fixed_result':text,'configuration_sha256':configuration_digest(workflow)}
    except (ValueError,KeyError,TypeError,OSError) as exc:raise HTTPException(422,'定时发布方案无法准备：'+str(exc)) from None


class SchedulePublication:
    def __init__(self,host):self.h=host
    def public(self,row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}
    def recover(self):
        for row in self.h.store.list('schedule_publication'):
            if row.get('state')=='executing':
                row.update(state='unknown',completed_at=self.h.now(),message='定时发布处理中断，没有重放或自动停用；可能仍在调度，请核对原新App并处理。')
                self.h.store.put('schedule_publication',row['id'],row)

    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.post('/api/tasks/{item_id}/schedule-publication/prepare')
        def prepare(item_id:str,payload:Prepare):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);h.require_intake(task)
                if not task.get('requirements_confirmed') or not task.get('configuration_confirmed'):raise HTTPException(409,'请先确认当前定时需求与配置。')
                frozen=source(h,task);env=h.environment(task)
                if env.get('version')!='1.17.1':raise HTTPException(422,'仅适配Dify 1.17.1，不猜其它版本发布与激活行为。')
                secrets=[h.store.secret(env['id'],k) for k in h.SECRET_FIELDS];provider=task.get('configuration',{}).get('assistant_provider_id')
                if provider:secrets.append(h.store.secret(provider,'api_key'))
                if not safe_text(frozen['outbound_dsl'],2000000) or contains_saved_secret(frozen['root'],secrets):raise HTTPException(422,'成果包含当前已保存凭据或密钥形式，不打包出站。')
                from .console_connection import summary
                connection=summary(h.store.secret(env['id'],'console_token'),bool(h.store.secret(env['id'],'csrf_token')));label=env.get('name')
                row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':payload.revision,'application_name':frozen['application_name'],'environment_id':env['id'],'environment_label':label if safe_text(label,255) and not any(s and s in label for s in secrets) else '所选Dify环境','environment_url':env['base_url'],'environment_version':env['version'],'environment_binding':binding(env),'connection_state':connection['state'],'artifact_sha256':frozen['artifact_sha256'],'graph_digest':frozen['graph']['digest'],'configuration_sha256':frozen['configuration_sha256'],'entry_id':frozen['entry_id'],'schedule':frozen['schedule'],'fixed_result':frozen['fixed_result'],'outbound_dsl':frozen['outbound_dsl'],'resource_counts':{'new_apps':1,'publish_attempts':1,'stop_attempts':1,'new_keys':0,'manual_runs':0},'max_remote_reads':5,'max_seconds':240,'automatic_retry':False,'paid_nodes':False,'host_cost_guaranteed_zero':False,'possible_natural_activation':True,'business_verified':False,'created_at':h.now(),'note':NOTE}
                row['resource_token']=digest(row);row.update(state='prepared_unapproved',attempts={},reads_attempted=0,publication_matched=False,stop_observed=False);h.store.put('schedule_publication',row['id'],row);return self.public(row)
        @router.get('/api/tasks/{item_id}/schedule-publication')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('schedule_publication') if r.get('task_id')==item_id]
            return {'task_id':item_id,'revision':task['revision'],'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':NOTE}

        @router.get('/api/tasks/{item_id}/schedule-publication/{plan_id}/reconcile')
        async def reconcile(item_id:str,plan_id:str):
            with h.store.lock:
                h.get_task(item_id);row=h.store.get('schedule_publication',plan_id)
                if not row or row.get('task_id')!=item_id or not canonical(row.get('app_id')):raise HTTPException(404,'本任务没有可信的新定时App目标。')
                if row.get('state')=='executing':raise HTTPException(409,'原资源操作仍处理中，不并发核对。')
                env=copy.deepcopy(h.store.get('environment',row['environment_id']))
                if not env or binding(env)!=row['environment_binding']:raise HTTPException(409,'原环境地址或版本改变，不把旧App ID交给新连接。')
                credentials=CredentialSnapshot(h.store,env['id']);original=stamp(row)
            def check():
                with h.store.lock:
                    profile=h.store.get('environment',env['id']);current=h.store.get('schedule_publication',plan_id)
                    if not profile or binding(profile)!=binding(env) or not credentials.unchanged(h.store) or not current or stamp(current)!=original:raise HTTPException(409,'原连接或记录改变，未保存旧核对。')
            async def read():
                check();client=h.DifyClient(env,credentials);published=await client.published_workflow(row['app_id']);check();selected=triggers(await client.app_triggers(row['app_id']),row['entry_id']);check();return published,selected
            try:published,selected=await asyncio.wait_for(read(),timeout=60)
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except TimeoutError:raise HTTPException(504,'原新App只读核对超时，没有重新发布或停用。') from None
            with h.store.lock:
                check();graph=fingerprint(published.get('graph')) if isinstance(published,dict) else None;records=selected['records']
                status=records[0]['status'] if len(records)==1 and (not row.get('trigger_id') or records[0]['trigger_id']==row['trigger_id']) else 'unknown'
                row.update(reconciled_at=h.now(),reconciled_status=status,reconciled_core_matched=bool(graph and graph['digest']==row['graph_digest']))
                if status=='disabled' and row['state'] in {'unknown','stop_not_confirmed'}:row.update(state='disabled_observed_later',message='后续只读看到原触发器停用，不能归因原停用尝试；仍不证明自然运行／业务通过。')
                h.store.put('schedule_publication',row['id'],row)
            return self.public(row)

        @router.post('/api/tasks/{item_id}/schedule-publication/{plan_id}/execute')
        async def execute(item_id:str,plan_id:str,payload:Execute):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);h.require_intake(task);row=h.store.get('schedule_publication',plan_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该定时发布方案。')
                if row.get('revision')!=payload.revision or row.get('resource_token')!=payload.resource_token or row.get('state')!='prepared_unapproved':raise HTTPException(409,'方案、修订或批准哈希不匹配，不能重放。')
                if not payload.approve_resource_plan or not payload.accept_possible_activation:raise HTTPException(422,'请明确接受具体新资源及发布可能激活／停用失败后持续调度的影响。')
                if any(r.get('task_id')==item_id and r.get('state') in {'executing','unknown','stop_not_confirmed'} for r in h.store.list('schedule_publication')):raise HTTPException(409,'本任务已有定时发布处理中或停用未知，请先核对原新App，不另建。')
                env=copy.deepcopy(h.environment(task));frozen=source(h,task)
                def origin():
                    current=h.store.get('environment',row['environment_id'])
                    if not current or current.get('version')!='1.17.1' or binding(current)!=row['environment_binding'] or not credentials.unchanged(h.store):raise HTTPException(409,'原环境或管理凭据改变，不改用新连接继续原资源操作。')
                def context():
                    origin();t=h.get_task(item_id);h.require_revision(t,row['revision']);h.require_intake(t)
                    if t.get('environment_id')!=env['id'] or not t.get('requirements_confirmed') or not t.get('configuration_confirmed') or source(h,t)['artifact_sha256']!=row['artifact_sha256']:raise HTTPException(409,'当前成果、确认或任务环境改变，不继续发布旧方案。')
                credentials=CredentialSnapshot(h.store,env['id']);context();row.update(state='executing',approved_at=h.now(),stage='preflight');h.store.put('schedule_publication',row['id'],row)
            client=h.DifyClient(env,credentials)
            def save():h.store.put('schedule_publication',row['id'],row)
            def mark(stage,mitigation=False):
                with h.store.lock:
                    origin() if mitigation else context()
                    if row['attempts'].get(stage):raise HTTPException(409,'此步骤已经尝试，不重复。')
                    row['attempts'][stage]=1;row['stage']=stage;save()
            async def read(call):
                with h.store.lock:
                    origin()
                    if row['reads_attempted']>=5:raise DifyError('已到方案只读次数上限，不追加请求。')
                    row['reads_attempted']+=1;save()
                value=await call()
                with h.store.lock:origin()
                return value
            async def published():
                value=await read(lambda:client.published_workflow(row['app_id']))
                try:matched=isinstance(value,dict) and canonical(value.get('id')) and fingerprint(value.get('graph'))==frozen['graph'] and configuration_digest(value)==row['configuration_sha256']
                except (ValueError,KeyError,TypeError):matched=False
                if not matched or row.get('published_workflow_id') and row['published_workflow_id']!=canonical(value['id']):raise DifyError('实际发布版本、完整核心图或特性／变量不匹配，未证明批准成果已发布。')
                row.update(published_workflow_id=canonical(value['id']),publication_matched=True);save()
            async def publish():
                context();await read(client.test);context();mark('import');value=await client.import_new(frozen['outbound_dsl'],row['application_name'])
                if isinstance(value,dict) and canonical(value.get('app_id')):row['app_id']=canonical(value['app_id']);save()
                context()
                if not isinstance(value,dict) or value.get('status')!='completed' or not row.get('app_id'):raise DifyError('导入未明确完成，可能已有遗留新App；不忽略警告或重复创建。')
                mark('publish');await client.request('POST',f"/console/api/apps/{row['app_id']}/workflows/publish",credential='console_token',json={'marked_name':'Sierra timer','marked_comment':'批准的新定时纯文字应用，随后核对并尝试停用。'});context();await published()
            async def mitigate():
                def selected(value):
                    records=triggers(value,row['entry_id'])['records']
                    if len(records)!=1 or records[0]['status'] not in {'enabled','disabled'}:raise DifyError('原新App的原触发器缺失、重复、限流或未知，不猜目标停用。')
                    if row.get('trigger_id') and row['trigger_id']!=records[0]['trigger_id']:raise DifyError('原触发器ID改变，不停用替代资源。')
                    return records[0]
                before=selected(await read(lambda:client.app_triggers(row['app_id'])));row['trigger_id']=before['trigger_id'];save()
                if before['status']=='enabled':
                    mark('stop',mitigation=True);await client.disable_app_trigger(row['app_id'],row['trigger_id']);after=selected(await read(lambda:client.app_triggers(row['app_id'])))
                else:after=before
                row['stop_observed']=after['status']=='disabled';save()
                if not row['stop_observed']:raise DifyError('一次停用后仍未观察disabled，可能继续调度，不重试。')
                if row['publication_matched']:await published()
            failure=None
            try:await asyncio.wait_for(publish(),timeout=180)
            except BaseException as exc:failure=exc
            if row['attempts'].get('publish') and row.get('app_id'):
                try:await asyncio.wait_for(mitigate(),timeout=60)
                except BaseException as exc:failure=exc
            if failure:
                row.update(state='stopped_unverified_publication' if row['stop_observed'] else 'stop_not_confirmed' if row['attempts'].get('publish') else 'unknown' if row['attempts'] else 'not_dispatched',completed_at=h.now(),message='原触发器已观察停用，但发布流程未完成或来源仍未证明；不算自然运行或业务通过。' if row['stop_observed'] else '资源操作未完成，保存已知App及尝试；可能继续调度，请核对并处理原触发器，没有重试。');save()
                # Return the concrete resource checkpoint even for failed mitigation.
                return self.public(row)
            row.update(state='published_and_disabled',completed_at=h.now(),message='本次实际发布图核对匹配，并观察原触发器停用；尚未验证自然运行／送达或业务，持续启用需另确认。');save();return self.public(row)
        h.app.include_router(router)
