"""Optimistic, ordered single-case dispatch proofs; no worker or auto resume."""
import hashlib
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from .run_input_transport import RunInputRoute
from .run_case_input_check import saved_case, encoded_case


class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    case_ids:list[StrictStr]=Field(min_length=1,max_length=10)


class SequenceProof(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_ids:list[StrictStr]=Field(min_length=1,max_length=10)
    start_count:StrictInt=Field(ge=0)
    index:StrictInt=Field(ge=0,le=9)
    token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')


def fingerprint(value):
    try:
        raw=json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
        if len(raw)>8_000_000:raise ValueError()
        return hashlib.sha256(raw).hexdigest()
    except (ValueError,TypeError,RecursionError,OverflowError):
        raise HTTPException(422,'样例批次来源超过8MB或不是有限JSON；未准备或派发。') from None


class CaseSequence:
    def __init__(self,host):self.h=host

    def source(self,task,case_ids,start_count):
        h=self.h
        if task.get('status')=='paused':raise HTTPException(409,'任务已暂停，不准备或继续顺序试跑。')
        if len(set(case_ids))!=len(case_ids) or any(not x or len(x)>256 for x in case_ids):
            raise HTTPException(422,'请选择1到10个互不重复的已保存样例。')
        if task['app_type'] not in {'workflow','advanced-chat','agent'}:
            raise HTTPException(422,'当前应用类型尚不支持顺序样例试跑。')
        if not task['requirements_confirmed'] or not task['configuration_confirmed'] or task.get('plan_stale'):
            raise HTTPException(422,'请先保存、复核并确认当前需求、配置与计划。')
        h.require_manual_entry_runtime(task);h.require_dsl_preservation(task)
        h.require_coverage(task);h.require_conflicts(task);h.require_intake(task)
        env=h.environment(task)
        if not task.get('dify_app_id') or env.get('service_app_id')!=task['dify_app_id'] or not h.store.has_secret(env['id'],'service_api_key'):
            raise HTTPException(422,'请先核对当前App已发布，且环境已保存与当前App配对的运行Key。')
        path=h.artifact_path(task)
        try:content=path.read_bytes()
        except OSError:raise HTTPException(422,'成果文件无法读取，请重新核对后准备批次。') from None
        if len(content)>2_000_000:raise HTTPException(422,'成果超过2MB，不能准备此批样例。')
        rows=[saved_case(task,x) for x in case_ids]
        from .evaluation import validate_test_cases
        from .start_inputs import preflight
        root=None
        if task['app_type']!='agent':
            from .dsl_roundtrip import parse
            try:root=parse(content.decode('utf-8'),task['app_type'])
            except (ValueError,UnicodeError):raise HTTPException(422,'当前成果无法核对入口，未准备批次。') from None
        for row in rows:
            encoded_case(row)
            values=row.get('input')
            if row.get('followups') or not isinstance(values,dict) or not values or len(values)>100 or 'conversation_id' in values or any(type(v) not in {str,int,float,bool,type(None)} for v in values.values()):
                raise HTTPException(422,'顺序试跑仅支持普通单轮标量样例；多轮、会话与文件请用原专用入口。')
            valid=validate_test_cases([row],task['app_type'])
            if not valid['valid']:raise HTTPException(422,'选定样例规则无效，请先在样例编辑器核对。')
            try:
                if root is not None:preflight(root,values)
                elif set(values)!={'query'} or not isinstance(values.get('query'),str) or not values['query'].strip():raise ValueError()
            except ValueError:raise HTTPException(422,'选定样例与当前成果入口不匹配；未派发任何样例。') from None
        # Ciphertext only: detect a same-App key replacement without decrypting it.
        with h.store.connect() as conn:
            secret=conn.execute('SELECT value FROM secrets WHERE id=?',(env['id']+':service_api_key',)).fetchone()
        secret_sha=hashlib.sha256(bytes(secret[0])).hexdigest() if secret else None
        # Normal run checkpoints increment state_sequence without changing the
        # reviewed source. Exact run count/prefix/ownership is checked below.
        base={k:v for k,v in task.items() if k not in {'runs','status','updated_at','state_sequence'}}
        binding={'task':base,'environment':env,'key_cipher_sha':secret_sha,'artifact_bytes_sha':hashlib.sha256(content).hexdigest(),
                 'policy':h.store.get('execution_limits',task['id']),'settings':h.get_settings(),
                 'case_ids':case_ids,'start_count':start_count,'prior_records':task['runs'][:start_count]}
        return fingerprint(binding),rows

    def check(self,task,proof,case):
        """Called under the original run's lock immediately before its record append."""
        h=self.h
        if proof.index>=len(proof.case_ids) or not case or case.get('id')!=proof.case_ids[proof.index]:
            raise HTTPException(409,'当前样例与已预览的批次顺序不一致，未派发。')
        if len(task['runs'])!=proof.start_count+proof.index:
            raise HTTPException(409,'批次历史已改变或此样例已启动；不重复派发，请核对原记录。')
        token,rows=self.source(task,proof.case_ids,proof.start_count)
        if token!=proof.token or encoded_case(case)!=encoded_case(rows[proof.index]):
            raise HTTPException(409,'批次来源、环境、Key、策略或成果已改变；请重新预览，不沿用原批。')
        for i,run in enumerate(task['runs'][proof.start_count:]):
            if run.get('case_sequence')!={'token':proof.token,'start_count':proof.start_count,'index':i,'case_ids':list(proof.case_ids)} or run.get('kind')!='run' or run.get('status')!='success' or run.get('evaluation',{}).get('status')!='passed' or encoded_case(run.get('test_case'))!=encoded_case(rows[i]):
                raise HTTPException(409,'前例未明确通过或记录不属于本批；停止后续，不自动重试。')

    def register(self):
        h=self.h;router=APIRouter(route_class=RunInputRoute)
        @router.post('/api/tasks/{item_id}/case-sequence-preview')
        def preview(item_id:str,payload:Selection):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
                token,rows=self.source(task,payload.case_ids,len(task['runs']))
                capacity=h.execution_limits.preflight(task,len(rows))
                if capacity['limits']['policy']['max_started_runs'] is None:
                    raise HTTPException(422,'顺序批次须先明确保存有限累计次数上限；不会自动设置或扩大。')
                if not capacity['limits_allow_requested_runs']:
                    raise HTTPException(409,' '.join(capacity['blockers']))
                return {'task_id':item_id,'revision':payload.revision,'case_ids':payload.case_ids,
                        'start_count':len(task['runs']),'token':token,'requested_runs':len(rows),
                        'started_runs':capacity['started_runs'],'max_started_runs':capacity['limits']['policy']['max_started_runs'],
                        'app_id':task['dify_app_id'],'environment_id':task['environment_id'],
                        'network_requested':False,'task_changed':False,'start_slots_reserved':0,'resource_permission_granted':False,
                        'note':'主动启动才依次调用当前App，最多每样例一次；失败、未知或需人工判断即停止。刷新/离开不续跑，不取消已派发请求。原外部资源和费用批准仍须满足，此预览不提供新授权或费用硬上限。'}
        h.app.include_router(router)
