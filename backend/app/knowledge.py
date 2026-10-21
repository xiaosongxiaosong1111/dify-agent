"""Confirmed, durable knowledge provisioning. No automatic destructive cleanup."""
from __future__ import annotations
import asyncio
import copy
import hashlib
import math
import re
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from .dify import DifyClient, DifyError
from .dsl import TARGET_DIFY_VERSION
from .resources import models_metadata


def now():return datetime.now(timezone.utc).isoformat()
def remote_id(value):
    if not isinstance(value,str):raise DifyError('Dify 未返回可核对的资源 ID，结果可能未知。')
    try:uuid.UUID(value)
    except ValueError:raise DifyError('Dify 返回的资源 ID 不兼容，结果可能未知。') from None
    return value


def document_ready(document):
    status=document.get('indexing',{})
    done,total=status.get('completed_segments'),status.get('total_segments')
    return status.get('indexing_status')=='completed' and type(done) is int and type(total) is int and total>=done>0


class StopProvision(Exception):pass


class KnowledgeManager:
    def __init__(self, host):self.host=host
    @property
    def store(self):return self.host.store
    def job(self, job_id):
        job=self.store.get('knowledge_job',job_id)
        if not job:raise HTTPException(404,'知识库准备记录不存在。')
        return job
    def public(self,job):
        out=copy.deepcopy(job)
        out['has_dataset_key']=self.store.has_secret(job['id'],'dataset_api_key')
        return out
    def busy(self,task_id):return any(j['task_id']==task_id and (j['status']=='running' or any(o['status']=='pending' for o in j['operations'])) for j in self.store.list('knowledge_job'))
    def checkpoint(self,job_id,change,secrets=None):
        with self.store.lock:
            job=self.job(job_id);change(job);job['updated_at']=now()
            if secrets is not None:self.store.put_with_secrets('knowledge_job',job_id,job,secrets)
            else:self.store.put('knowledge_job',job_id,job)
            return job
    def bound(self,job, *, allow_pause=False, check_time=False, read_applied=False):
        task=self.host.get_task(job['task_id']);env=self.store.get('environment',job['environment_id'])
        applied_read = (read_applied and job['status']=='applied'
                        and type(job.get('applied_revision')) is int
                        and task['revision']>=job['applied_revision']
                        and job.get('dataset_id') in task['configuration']['dataset_ids'])
        if (task['revision']!=job['task_revision'] and not applied_read) or task.get('environment_id')!=job['environment_id']:raise StopProvision('任务修订或目标环境已变化；旧方案不继续派发或自动加入配置。')
        if not env or any(env.get(k)!=job['connection'].get(k) for k in ('base_url','version','connection_revision')):raise StopProvision('目标连接已变化，请复核资源方案；未自动迁移到新环境。')
        if task['status'] in self.host.BUSY or any(x.get('status')=='pending' for x in task.get('runs',[])):raise StopProvision('任务正在进行其他外部操作，知识库准备暂停。')
        if not allow_pause and job['status']=='paused':raise StopProvision('已按用户要求暂停后续派发；Dify 已接收的索引可能仍在执行。')
        if check_time and job.get('started_at') and (datetime.now(timezone.utc)-datetime.fromisoformat(job['started_at'])).total_seconds() >= job['max_minutes']*60:raise StopProvision('达到本次知识库准备时间上限。停止后续派发；已提交的 Dify 索引不会被自动取消。')
        return task,env
    async def identity(self,env):
        result=await DifyClient(env,self.store).workspace()
        if not isinstance(result,dict) or not isinstance(result.get('id'),str) or not result['id']:raise DifyError('不能读取目标工作空间身份，不开始资源写入。')
        return {'id':result['id'],'name':result.get('name') if isinstance(result.get('name'),str) else result['id']}
    def safe_error(self,text,job):
        text=str(text)
        for owner in (job['environment_id'],job['id']):
            for key in ('console_token','csrf_token','service_api_key','dataset_api_key'):
                secret=self.store.secret(owner,key)
                if secret:text=text.replace(secret,'[已脱敏]')
        for provider in self.store.list('provider'):
            secret=self.store.secret(provider['id'],'api_key')
            if secret:text=text.replace(secret,'[已脱敏]')
        return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b','[已脱敏]',text)[:1500]
    async def propose(self,task_id,payload):
        allowed={'revision','name','purpose','description','indexing_technique','embedding_provider','embedding_model','material_ids','text','document_name','max_minutes'}
        if not isinstance(payload,dict) or set(payload)-allowed:raise HTTPException(422,'未知知识库准备字段。')
        with self.store.lock:
            task=copy.deepcopy(self.host.get_task(task_id));self.host.require_idle(task)
            if type(payload.get('revision')) is not int:raise HTTPException(422,'任务修订须为整数。')
            self.host.require_revision(task,payload.get('revision'))
            env=copy.deepcopy(self.host.environment(task))
        name=payload.get('name');purpose=payload.get('purpose');description=payload.get('description','');strategy=payload.get('indexing_technique','economy');minutes=payload.get('max_minutes',5)
        if not isinstance(name,str) or not 1<=len(name.strip())<=40 or not isinstance(description,str) or len(description)>400:raise HTTPException(422,'知识库名称须为 1—40 字，描述最多 400 字。')
        if not isinstance(purpose,str) or not purpose.strip() or len(purpose)>2000:raise HTTPException(422,'须明确知识库用途，最多 2000 字。')
        if strategy not in {'economy','high_quality'}:raise HTTPException(422,'索引方式只支持 economy 或 high_quality；不会静默替换。')
        if isinstance(minutes,bool) or not isinstance(minutes,(int,float)) or not math.isfinite(minutes) or not 0<minutes<=60:raise HTTPException(422,'本次准备时间上限须为 0—60 分钟内的有限正数。')
        ids=payload.get('material_ids',[]);text=payload.get('text','');title=payload.get('document_name','粘贴资料')
        if not isinstance(ids,list) or len(ids)>10 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids) or not isinstance(text,str):raise HTTPException(422,'资料 ID 须为不重复的文本列表；正文须为文本。')
        if not isinstance(title,str) or not title.strip() or len(title)>200:raise HTTPException(422,'资料标题须为 1—200 字。')
        documents=[]
        for material_id in ids:
            material=next((m for m in task['materials'] if m['id']==material_id),None)
            if not material or material.get('status')!='parsed' or not material.get('text','').strip():raise HTTPException(422,'选中资料尚无可读取的完整文本，请先处理解析问题。')
            documents.append({'source':'material','material_id':material_id,'name':material['name'],'text':material['text']})
        if text.strip():documents.append({'source':'pasted','name':title.strip(),'text':text})
        if not documents or len(documents)>10 or any(len(d['text'])>100000 for d in documents) or sum(len(d['text'].encode('utf-8')) for d in documents)>1000000:raise HTTPException(422,'须提供 1—10 份可读资料，每份最多 10 万字，合计最多 1 MB；超限不截断。')
        if any(not isinstance(d['name'],str) or not 1<=len(d['name'])<=200 for d in documents):raise HTTPException(422,'资料标题最多 200 字，未自动截断。')
        for d in documents:d.update(id=str(uuid.uuid4()),sha256=hashlib.sha256(d['text'].encode()).hexdigest(),characters=len(d['text']))
        ep=payload.get('embedding_provider','');em=payload.get('embedding_model','')
        if not isinstance(ep,str) or not isinstance(em,str):raise HTTPException(422,'Embedding 模型标识须为文本。')
        if strategy=='economy' and (ep or em):raise HTTPException(422,'经济索引不使用 Embedding，请明确清除选择后再提交，不自动忽略。')
        try:
            workspace=await self.identity(env)
            if strategy=='high_quality':
                rows=models_metadata(await DifyClient(env,self.store).models('text-embedding'),'text-embedding')
                if not any(m['provider']==ep and m['model']==em and m['selectable'] for m in rows):raise HTTPException(422,'高质量索引缺少可用 Embedding 模型。可在 Dify 配置后重试，或明确选择经济索引；未自动降级。')
        except DifyError as exc:raise HTTPException(502,str(exc)) from exc
        with self.store.lock:
            current=self.host.get_task(task_id);self.host.require_idle(current);self.host.require_revision(current,task['revision'])
            current_env=self.store.get('environment',env['id'])
            if not current_env or self.host.env_snapshot(current_env)!=self.host.env_snapshot(env):raise HTTPException(409,'读取期间环境变化，方案未保存，请重新生成。')
            if any(j['environment_id']==env['id'] and j['name']==name.strip() and j['status']=='unknown' for j in self.store.list('knowledge_job')):raise HTTPException(409,'同名资源有结果未知的准备记录，请先核对，不能盲目重建。')
            job={'id':str(uuid.uuid4()),'task_id':task_id,'task_revision':task['revision'],'environment_id':env['id'],'connection':{k:env.get(k) for k in ('base_url','version','connection_revision')},'workspace':workspace,'name':name.strip(),'purpose':purpose.strip(),'description':description,'indexing_technique':strategy,'embedding_provider':ep,'embedding_model':em,'documents':documents,'max_minutes':minutes,'status':'draft','operations':[],'dataset_id':None,'message':'仅生成方案，尚未创建资源。','created_at':now(),'updated_at':now(),'cost_note':'经济关键词索引不调用 Embedding 模型；仍占用 Dify 的存储与计算资源。' if strategy=='economy' else '会调用所选 Embedding 模型。此流程没有供应商账单硬上限和可靠费用估算，须明确接受未知模型费用后才派发；时间上限不能取消已提交索引。'}
            self.store.put('knowledge_job',job['id'],job)
        return self.public(job)
    def confirm(self,job_id,payload):
        with self.store.lock:
            job=self.job(job_id)
            if job['status']!='draft':raise HTTPException(409,'只能确认未执行的知识库方案。')
            try:self.bound(job)
            except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
            if type(payload.get('task_revision')) is not int or payload.get('task_revision')!=job['task_revision']:raise HTTPException(409,'方案修订不一致。')
            if job['indexing_technique']=='high_quality' and payload.get('accept_unknown_embedding_cost') is not True:raise HTTPException(422,'高质量索引费用未明确接受；可以补齐条件或重新选择经济索引，不自动代选。')
            job.update(status='approved',confirmation={'task_revision':job['task_revision'],'workspace_id':job['workspace']['id'],'accepted_unknown_embedding_cost':payload.get('accept_unknown_embedding_cost') is True,'created_at':now()},message='方案已确认，执行仍需主动启动。',updated_at=now());self.store.put('knowledge_job',job_id,job)
            return self.public(job)
    def remaining(self,job):
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(job['started_at'])).total_seconds()
        return max(.1,min(90,job['max_minutes']*60-elapsed))
    async def step(self,job_id,kind,call,commit,document_id=None,secret=False):
        job=self.job(job_id);_,env=self.bound(job,check_time=True)
        if (await self.identity(env))['id']!=job['workspace']['id']:
            raise StopProvision('写入前工作空间已变化，停止后续派发。')
        self.bound(self.job(job_id),check_time=True)
        op={'id':str(uuid.uuid4()),'kind':kind,'document_local_id':document_id,'status':'pending','created_at':now()}
        self.checkpoint(job_id,lambda j:j['operations'].append(op))
        try:
            result=await call(self.remaining(job));result_data=commit(result)
            if (await self.identity(env))['id']!=job['workspace']['id']:
                raise DifyError('写入期间工作空间变化，结果可能未知；请核对实际资源，不自动绑定到已确认空间。')
        except BaseException as exc:
            status='rejected' if isinstance(exc,DifyError) and exc.http_status in {401,403,404,422} else 'unknown'
            message=self.safe_error(str(exc),job) if isinstance(exc,DifyError) else '请求或返回处理被中断，结果可能未知，请在 Dify 核对，不重复创建。'
            def failed(j):
                target=next(x for x in j['operations'] if x['id']==op['id']);target.update(status=status,error=message,completed_at=now())
                j.update(status='paused' if status=='rejected' else 'unknown',message=message)
            self.checkpoint(job_id,failed)
            if isinstance(exc,asyncio.CancelledError):raise
            raise StopProvision(message) from exc
        secrets={'dataset_api_key':result_data.pop('token')} if secret else None
        def done(j):
            target=next(x for x in j['operations'] if x['id']==op['id']);target.update(status='success',completed_at=now())
            if kind=='create_dataset':j['dataset_id']=result_data['id'];target['resource_id']=result_data['id']
            elif kind=='upload_document':
                doc=next(d for d in j['documents'] if d['id']==document_id);doc.update(remote_id=result_data['id'],indexing={'indexing_status':'submitted'});target['resource_id']=result_data['id']
        self.checkpoint(job_id,done,secrets)
    async def execute(self,job_id, *, replace_unknown_key=False):
        with self.store.lock:
            job=self.job(job_id)
            if job['status']=='running':raise HTTPException(409,'该准备作业正在执行。')
            if not job.get('confirmation') or job['status'] in {'draft','ready','applied','canceled','indexing'}:raise HTTPException(409,'须先确认未执行方案；已提交索引请刷新状态，不重复执行。')
            unknown=[op for op in job['operations'] if op['status'] in {'pending','unknown'}]
            if unknown:
                if replace_unknown_key and len(unknown)==1 and unknown[0]['kind']=='create_key' and not job.get('replacement_key_requested'):
                    unknown[0].update(status='unknown_acknowledged',message='用户明确接受旧 Key 可能仍存在并创建一次替代 Key。');job['replacement_key_requested']=True
                else:raise HTTPException(409,'写入结果未知，须先在 Dify 核对并绑定已创建资源；不盲目重试。')
            try:task,env=self.bound(job,allow_pause=True)
            except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
            self.host.require_idle(task)
            job.update(status='running',started_at=now(),message='正在核对工作空间并执行已确认方案。',updated_at=now());self.store.put('knowledge_job',job_id,job)
        try:
            adapter=DifyClient(env,self.store)
            workspace=await self.identity(env)
            if workspace['id']!=job['workspace']['id']:raise StopProvision('当前登录工作空间已变化，不向新空间创建资源。')
            if job['indexing_technique']=='high_quality':
                rows=models_metadata(await adapter.models('text-embedding'),'text-embedding')
                if not any(x['provider']==job['embedding_provider'] and x['model']==job['embedding_model'] and x['selectable'] for x in rows):raise StopProvision('已确认 Embedding 模型当前不可用；未自动替换索引方式。')
            if not job.get('dataset_id'):
                await self.step(job_id,'create_dataset',lambda timeout:adapter.create_dataset(job['name'],job['description'],job['indexing_technique'],timeout=timeout),lambda r:{'id':remote_id(r.get('id') if isinstance(r,dict) else None)})
            job=self.job(job_id);dataset=job['dataset_id']
            if not self.store.has_secret(job_id,'dataset_api_key'):
                def key_result(r):
                    token=r.get('token') if isinstance(r,dict) else None
                    if not isinstance(token,str) or not token or len(token)>16384 or any(c.isspace() for c in token):raise DifyError('Dify 未返回有效的单库 Key，结果可能未知。')
                    return {'token':token}
                await self.step(job_id,'create_key',lambda timeout:adapter.create_scoped_dataset_key(dataset,timeout=timeout),key_result,secret=True)
            for document in self.job(job_id)['documents']:
                if document.get('remote_id'):continue
                await self.step(job_id,'upload_document',lambda timeout,d=document:adapter.create_text_document(dataset,d,job['indexing_technique'],job_id,embedding_provider=job['embedding_provider'],embedding_model=job['embedding_model'],timeout=timeout),lambda r:{'id':remote_id((r.get('document') or {}).get('id') if isinstance(r,dict) else None)},document_id=document['id'])
            self.bound(self.job(job_id),check_time=True)
            self.checkpoint(job_id,lambda j:j.update(status='indexing',message='资料已提交 Dify；索引尚未完成，请读取实际状态。'))
            return await self.refresh(job_id)
        except (DifyError,StopProvision) as exc:
            current=self.job(job_id)
            if current['status'] not in {'unknown','paused'}:self.checkpoint(job_id,lambda j:j.update(status='paused',message=self.safe_error(str(exc),j)))
            return self.public(self.job(job_id))
        except HTTPException as exc:
            self.checkpoint(job_id,lambda j:j.update(status='paused',message=self.safe_error(exc.detail,j)))
            return self.public(self.job(job_id))
        except BaseException:
            current=self.job(job_id)
            if any(x['status']=='pending' for x in current['operations']):
                def interrupt(j):
                    for op in j['operations']:
                        if op['status']=='pending':op.update(status='unknown',error='执行中断，需核对实际结果。')
                    j.update(status='unknown',message='执行中断，结果可能未知。')
                self.checkpoint(job_id,interrupt)
            elif not any(x['status']=='unknown' for x in current['operations']):self.checkpoint(job_id,lambda j:j.update(status='paused',message='准备流程中断，已有资源保留。'))
            raise
    async def refresh(self,job_id):
        job=self.job(job_id)
        if job['status'] not in {'indexing','paused','ready','applied','needs_input'} or not job.get('dataset_id'):raise HTTPException(409,'尚无可核对的索引记录，或存在结果未知的写入。')
        try:_,env=self.bound(job,allow_pause=True,read_applied=True)
        except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
        adapter=DifyClient(env,self.store)
        try:
            if (await self.identity(env))['id']!=job['workspace']['id']:raise HTTPException(409,'当前工作空间不同，未读取其他空间的状态。')
            observations={}
            for doc in job['documents']:
                if not doc.get('remote_id'):continue
                result=await adapter.document_status(job['dataset_id'],doc['remote_id'])
                if not isinstance(result,dict) or result.get('id')!=doc['remote_id'] or not isinstance(result.get('indexing_status'),str):raise DifyError('索引状态格式不兼容，不标记完成。')
                observations[doc['id']]={k:result[k] for k in ('indexing_status','completed_segments','total_segments','error_code') if k in result}
                observations[doc['id']]['error']=self.safe_error(result.get('error') or '',job)
        except DifyError as exc:
            self.checkpoint(job_id,lambda j:j.update(message=self.safe_error(str(exc),j)))
            raise HTTPException(502,str(exc)) from exc
        try:self.bound(self.job(job_id),allow_pause=True,read_applied=True)
        except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
        def update(j):
            for doc in j['documents']:
                if doc['id'] in observations:doc['indexing']=observations[doc['id']]
            j['observed_at']=now()
            complete=all(document_ready(d) for d in j['documents'])
            if j['status']=='applied':return
            if complete:j.update(status='ready',message='所有资料的实际索引已完成且有可用片段；尚未加入任务配置，也不等于检索效果已验收。')
            elif any(d.get('indexing',{}).get('indexing_status') not in {'submitted','waiting','parsing','cleaning','splitting','indexing','completed','paused','error'} for d in j['documents']):j.update(status='needs_input',message='Dify 返回未识别的索引状态，不确认可用，请核对实例。')
            elif any(d.get('indexing',{}).get('indexing_status') in {'error','paused','completed'} and (d['indexing']['indexing_status']!='completed' or not document_ready(d)) for d in j['documents']):j.update(status='needs_input',message='存在索引错误、暂停或无可用片段，请核对 Dify 状态；不切换索引方式或冒充完成。')
            elif j['status']!='paused':
                try:self.bound(j,check_time=True)
                except StopProvision as exc:j.update(status='paused',message=str(exc))
        return self.public(self.checkpoint(job_id,update))
    def pause(self,job_id):
        job=self.job(job_id)
        if job['status'] in {'ready','applied','canceled'}:raise HTTPException(409,'此阶段不需要暂停。')
        return self.public(self.checkpoint(job_id,lambda j:j.update(status='paused',message='暂停后续派发；已经提交给 Dify 的索引可能仍在执行，外部资源保留。')))
    async def reconcile(self,job_id,payload):
        job=self.job(job_id);unknown=[x for x in job['operations'] if x['status'] in {'pending','unknown'}]
        if job['status']=='running' or len(unknown)!=1 or payload.get('verified_in_dify') is not True:raise HTTPException(409,'须停止执行并明确在 Dify 核对唯一未知操作，才可绑定结果。')
        op=unknown[0]
        if op['kind']=='create_key':raise HTTPException(422,'Key 创建结果不能通过资源 ID 恢复；可明确接受旧 Key 可能存在后创建一次替代 Key。')
        try:_,env=self.bound(job,allow_pause=True)
        except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
        try:resource=remote_id(payload.get('resource_id'))
        except DifyError as exc:raise HTTPException(422,str(exc)) from exc
        adapter=DifyClient(env,self.store)
        try:
            if (await self.identity(env))['id']!=job['workspace']['id']:raise HTTPException(409,'工作空间不一致，不能绑定。')
            path=f'/console/api/datasets/{resource}' if op['kind']=='create_dataset' else f'/console/api/datasets/{job["dataset_id"]}/documents/{resource}'
            result=await adapter.request('GET',path,credential='console_token')
        except DifyError as exc:raise HTTPException(502,str(exc)) from exc
        name=job['name'] if op['kind']=='create_dataset' else next(d['name'] for d in job['documents'] if d['id']==op['document_local_id'])
        if result.get('id')!=resource or result.get('name')!=name:raise HTTPException(422,'远程资源 ID 或名称与确认方案不同，未绑定。')
        if op['kind']=='create_dataset' and result.get('indexing_technique')!=job['indexing_technique']:raise HTTPException(422,'索引方式不一致，未绑定。')
        self.bound(self.job(job_id),allow_pause=True)
        def apply(j):
            current=next(x for x in j['operations'] if x['id']==op['id']);current.update(status='success',resource_id=resource,reconciled_by='user_confirmed_console',completed_at=now())
            if op['kind']=='create_dataset':j['dataset_id']=resource
            else:next(d for d in j['documents'] if d['id']==op['document_local_id'])['remote_id']=resource
            j.update(status='paused',message='已核对并绑定现有资源；继续执行仍需主动启动。')
        return self.public(self.checkpoint(job_id,apply))
    async def apply(self,job_id,revision):
        job=self.job(job_id)
        if job['status']!='ready':raise HTTPException(409,'索引尚未实际完成，或已经加入任务。')
        if revision!=job['task_revision']:raise HTTPException(409,'任务修订不同，旧方案不会自动加入新版本。')
        job=await self.refresh(job_id)
        if job['status']!='ready':raise HTTPException(409,'重新核对后索引不是可用状态，未加入任务。')
        with self.store.lock:
            try:task,_=self.bound(job,allow_pause=True)
            except StopProvision as exc:raise HTTPException(409,str(exc)) from exc
            self.host.require_idle(task)
            self.host.invalidate(task,'加入已准备知识库前保存',preserve_requirements=True)
            task['configuration']['dataset_ids']=list(dict.fromkeys([*task['configuration']['dataset_ids'],job['dataset_id']]))
            if task.get('workflow_plan') or task.get('agent_plan'):task['plan_stale']=True
            task['updated_at']=now()
            job.update(status='applied',applied_revision=task['revision'],updated_at=now(),message='已加入默认知识库配置；确认失效，节点独立 ID 需复核后再生成。')
            self.store.put_many([('task',task['id'],task),('knowledge_job',job_id,job)])
            return task
    def recover(self):
        for job in self.store.list('knowledge_job'):
            if job['status']=='running':
                for op in job['operations']:
                    if op['status']=='pending':op.update(status='unknown',error='服务重启，写入结果需核对。')
                job.update(status='unknown' if any(x['status']=='unknown' for x in job['operations']) else 'paused',message='服务重启已保留进度；未自动重复外部写入。',updated_at=now());self.store.put('knowledge_job',job['id'],job)
