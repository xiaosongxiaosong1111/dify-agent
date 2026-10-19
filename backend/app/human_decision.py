"""Explicit human action approval, one submission, no automatic decision or rerun."""
import asyncio,copy,json,logging,re,time,uuid
import httpx
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .plan_drafts import DraftRoute
from .human_runtime_plan import source
from .schedule_observation import CredentialSnapshot
from .run_diagnostics import binding
from .workflow_waiting import canonical,stamp
from .schedule_stop import digest
from .diagnostic_graph_source import fingerprint
from .dify import DifyError,DifyClient

NOTE='这次批准只向原人工表单提交所选动作一次，不创建应用、不重新运行。首个提交生效；接受回执不等于恢复或业务通过，未知结果不重试。身份未强制限制，不发送通知；Dify侧URL日志策略须另行处理，Sierra不公开或记录表单令牌。'
PUBLIC={'id','task_id','run_id','revision','environment_url','app_id','workflow_run_id','form_id','node_id','content','action','action_title','expiration_time','resource_token','state','write_attempted','created_at','approved_at','completed_at','message','note','max_remote_reads','max_write_attempts','business_verified'}


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    action:str

class Execute(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    resource_token:str=Field(min_length=64,max_length=64)
    approve_human_action:StrictBool


class SensitiveLogFilter(logging.Filter):
    def filter(self,record):
        record.msg='Dify人工表单通信（敏感地址与凭据已隐藏）';record.args=();record.exc_info=None;record.exc_text=None
        return True


class FormClient:
    def __init__(self,env,key,token):
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}',key) or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}',token):raise DifyError('原应用Key或表单凭据不可信，未派发。')
        self.base=DifyClient(env,None).base;self.key=key;self.token=token
    async def request(self,method,payload=None):
        log_filter=SensitiveLogFilter();names={'httpx','httpcore.connection','httpcore.http11','httpcore.http2','httpcore.proxy','httpcore.socks5'}|{n for n in logging.Logger.manager.loggerDict if n.startswith(('httpx.','httpcore.'))}
        loggers=[logging.getLogger(n) for n in names]
        for logger in loggers:logger.addFilter(log_filter)
        try:
            async with httpx.AsyncClient(timeout=30,follow_redirects=False) as http:
                response=await http.request(method,self.base+'/v1/form/human_input/'+self.token,headers={'Authorization':'Bearer '+self.key},**({'json':payload} if payload is not None else {}))
            if response.is_error:raise DifyError(f'原人工表单返回HTTP {response.status_code}，可能已提交、已过期或权限不足；不会自动重试。',http_status=response.status_code)
            if len(response.content)>100000:raise DifyError('表单回执超过本机上限，未采纳原文。')
            try:return response.json()
            except (ValueError,RecursionError):raise DifyError('表单回执格式不可信，未保存原文。') from None
        except (httpx.RequestError,TimeoutError):raise DifyError('人工表单连接中断或超时，派发结果需核对，不重试。') from None
        finally:
            for logger in loggers:logger.removeFilter(log_filter)


class HumanDecision:
    def __init__(self,host):self.h=host
    def public(self,row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}
    def recover(self):
        h=self.h
        for row in h.store.list('human_decision'):
            if row.get('state')=='submitting':
                row.update(state='unknown' if row.get('write_attempted') else 'not_dispatched',completed_at=h.now(),message='人工提交处理中断，没有重放；请到原平台核对。')
                run=h.store.get('human_runtime_run',row['run_id'])
                records=[('human_decision',row['id'],row)]
                if run and run.get('state')=='submitting_decision':
                    run['state']='unknown' if row.get('write_attempted') else 'waiting_human';records.append(('human_runtime_run',run['id'],run))
                h.store.put_many(records)

    def original(self,task,run,ready=True):
        h=self.h;h.require_revision(task,run['revision']);h.require_intake(task)
        env=h.store.get('environment',run['environment_id']);form=run.get('form')
        if not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or task.get('environment_id')!=run['environment_id'] or not env or env.get('version')!='1.17.1' or binding(env)!=run.get('environment_binding') or source(h,task)['artifact_sha256']!=run.get('artifact_sha256'):raise HTTPException(409,'原任务确认、成果或环境已改变，不向旧表单提交决定。')
        if not canonical(run.get('app_id')) or not canonical(run.get('workflow_run_id')) or not isinstance(form,dict) or not canonical(form.get('form_id')) or form.get('workflow_run_id')!=run['workflow_run_id'] or not form.get('source_verified'):raise HTTPException(409,'原等待表单来源不完整，不猜另一表单。')
        if ready and (run.get('state')!='waiting_human' or run.get('human_submission_attempted') or type(form.get('expiration_time'))is not int or form['expiration_time']<=time.time()):raise HTTPException(409,'原表单已处理、过期、提交未知或非待审状态，不追加动作。')
        return copy.deepcopy(env),copy.deepcopy(form)

    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.post('/api/tasks/{item_id}/human-runtime/runs/{run_id}/decision/prepare')
        def prepare(item_id:str,run_id:str,payload:Prepare):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                run=h.store.get('human_runtime_run',run_id)
                if not run or run.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该原人工运行。')
                env,form=self.original(task,run)
                actions=[a for a in form['actions'] if a.get('id')==payload.action]
                if payload.action not in {'approve','reject'} or len(actions)!=1:raise HTTPException(422,'请选择原表单明确的approve或reject，不默认决定。')
                if any(r.get('run_id')==run_id and (r.get('write_attempted') or r.get('state')=='submitting') for r in h.store.list('human_decision')):raise HTTPException(409,'此原表单已有一次提交或处理记录，不追加提交。')
                row={'id':str(uuid.uuid4()),'task_id':item_id,'run_id':run_id,'revision':payload.revision,'environment_url':env['base_url'],'app_id':run['app_id'],'workflow_run_id':run['workflow_run_id'],'form_id':form['form_id'],'node_id':form['node_id'],'content':form['content'],'action':payload.action,'action_title':actions[0]['title'],'expiration_time':form['expiration_time'],'run_stamp':stamp(run),'max_remote_reads':2,'max_write_attempts':1,'business_verified':False,'created_at':h.now(),'note':NOTE}
                row['resource_token']=digest(row);row.update(state='prepared_unapproved',write_attempted=False);h.store.put('human_decision',row['id'],row);return self.public(row)

        @router.get('/api/tasks/{item_id}/human-runtime/runs/{run_id}/decisions')
        def history(item_id:str,run_id:str):
            h.get_task(item_id);run=h.store.get('human_runtime_run',run_id)
            if not run or run.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该原人工运行。')
            rows=[r for r in h.store.list('human_decision') if r.get('task_id')==item_id and r.get('run_id')==run_id]
            return {'task_id':item_id,'run_id':run_id,'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':NOTE}

        @router.post('/api/tasks/{item_id}/human-decisions/{decision_id}/submit')
        async def submit(item_id:str,decision_id:str,payload:Execute):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);row=h.store.get('human_decision',decision_id)
                if not row or row.get('task_id')!=item_id:raise HTTPException(404,'本任务没有该具体人工动作方案。')
                if row.get('revision')!=payload.revision or row.get('resource_token')!=payload.resource_token or row.get('state')!='prepared_unapproved':raise HTTPException(409,'具体动作批准不匹配或方案已处理，不能重发。')
                if not payload.approve_human_action:raise HTTPException(422,'请明确确认向原表单提交这一动作，不继承资源创建批准。')
                run=copy.deepcopy(h.store.get('human_runtime_run',row['run_id']))
                if not run or run.get('task_id')!=item_id:raise HTTPException(404,'原人工运行记录缺失。')
                env,form=self.original(task,run)
                if stamp(run)!=row['run_stamp'] or any(r.get('run_id')==run['id'] and (r.get('write_attempted') or r.get('state')=='submitting') for r in h.store.list('human_decision')):raise HTTPException(409,'原记录改变或同表单已有提交，请先核对，不重复。')
                credentials=CredentialSnapshot(h.store,env['id']);key=h.store.secret(run['id'],'service_api_key');token=h.store.secret(run['id'],'form_token');client=FormClient(env,key,token)
                root=source(h,task)['root'];row.update(state='submitting',approved_at=h.now());run['state']='submitting_decision'
                h.store.put_many([('human_decision',row['id'],row),('human_runtime_run',run['id'],run)])
            def save():h.store.put_many([('human_decision',row['id'],row),('human_runtime_run',run['id'],run)])
            def check():
                with h.store.lock:
                    self.original(h.get_task(item_id),run,ready=False)
                    if not credentials.unchanged(h.store) or key!=h.store.secret(run['id'],'service_api_key') or token!=h.store.secret(run['id'],'form_token') or stamp(h.store.get('human_runtime_run',run['id']))!=stamp(run):raise HTTPException(409,'原凭据或运行记录改变，没有改用新来源继续提交。')
            async def perform():
                check();detail=await h.DifyClient(env,credentials).workflow_run_detail(run['app_id'],run['workflow_run_id']);check()
                if not isinstance(detail,dict) or canonical(detail.get('id'))!=run['workflow_run_id'] or detail.get('status')!='paused' or fingerprint(detail.get('graph'))!=fingerprint(root['workflow']['graph']):raise DifyError('原暂停运行状态或实际执行核心图改变，不提交旧决定。')
                definition=await client.request('GET');check()
                if not isinstance(definition,dict) or set(definition)!={'form_content','inputs','resolved_default_values','user_actions','expiration_time'} or definition['form_content']!=form['content'] or definition['inputs']!=[] or definition['resolved_default_values']!={} or definition['user_actions']!=form['actions'] or type(definition['expiration_time'])is not int or definition['expiration_time']!=form['expiration_time'] or definition['expiration_time']<=time.time():raise DifyError('实际原表单正文、动作、输入或有效时间不匹配，不提交旧决定。')
                with h.store.lock:
                    check();row['write_attempted']=True;run['human_submission_attempted']=True;save()
                result=await client.request('POST',{'action':row['action'],'inputs':{},'user':'sierra-human-'+run['id']});check()
                if result!={}:raise DifyError('人工提交回执不符合原生空对象契约，结果需核对，不重试。')
                row.update(state='accepted',completed_at=h.now(),message='接口接受一次所选动作；原运行仍需主动核对，不代表恢复完成或业务通过。');run.update(state='awaiting_resume',human_decision_id=row['id'],message=row['message']);run['form']['active']=False;save();return self.public(row)
            try:return await asyncio.wait_for(perform(),timeout=60)
            except BaseException as exc:
                row.update(state='unknown' if row['write_attempted'] else 'not_dispatched',completed_at=h.now(),message='提交结果未知，不重试，请核对原平台；不能凭另一次运行证明恢复。' if row['write_attempted'] else '提交前核对未通过，未派发决定。')
                run.update(state='unknown' if row['write_attempted'] else 'waiting_human',message=row['message']);save()
                if isinstance(exc,HTTPException):raise
                if isinstance(exc,DifyError):raise HTTPException(502,str(exc)) from None
                if isinstance(exc,(TimeoutError,asyncio.CancelledError)):raise HTTPException(504,row['message']) from None
                raise HTTPException(500,'人工提交本机处理异常，检查点已保存，没有重复提交。') from None
        h.app.include_router(router)
