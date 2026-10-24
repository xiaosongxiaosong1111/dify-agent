"""Explicit local scalar input copy; never a replay permission or dispatch."""
import hashlib
import json
import math

from fastapi import APIRouter, HTTPException, Query, Response
from .dsl import _contains_secret_key
from .plan_drafts import _SECRET, _ASSIGNMENT
from .run_diagnostics import safe_text


def preview(task, run_id):
    rows=[r for r in task.get('runs',[]) if isinstance(r,dict) and r.get('id')==run_id]
    if len(rows)!=1 or rows[0].get('kind')!='run':
        raise HTTPException(404,'本任务没有这条唯一普通试跑记录，未读取其它任务。')
    run=rows[0];case=run.get('test_case') or {};result=run.get('result') or {}
    if run.get('status') not in {'success','failed'}:
        raise HTTPException(422,'原请求仍在执行、结果未知或待核对；先处理原记录，不能据此准备再次派发。')
    if run.get('app_type') not in {'workflow','advanced-chat','agent'} or run['app_type']!=task.get('app_type'):
        raise HTTPException(422,'原记录类型缺失或与当前任务不同，不能推断输入格式或更换类型。')
    if ('conversation_context' in run or run.get('file_case') is not None
            or isinstance(case,dict) and case.get('followups')
            or isinstance(result,dict) and result.get('conversation_case') is True):
        raise HTTPException(422,'这里只载入普通单轮标量输入；多轮、复用会话及文件记录不能丢弃上下文后复制。')
    value=run.get('input')
    if not isinstance(value,dict) or len(value)>100 or 'conversation_id' in value:
        raise HTTPException(422,'保存输入须为最多100字段的完整对象且不含会话标识，未删字段或猜测补齐。')
    if any(type(k) is not str or v is not None and type(v) not in (str,int,float,bool)
            or type(v) is float and not math.isfinite(v) for k,v in value.items()):
        raise HTTPException(422,'本入口仅支持文字、数值、布尔和null标量；文件、数组及对象须按各自原入口核对。')
    try:
        text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
        if len(text.encode())>128000:raise ValueError()
        if _contains_secret_key(value) or _SECRET.search(text) or _ASSIGNMENT.search(text) or safe_text(text,limit=128000)!=text:
            raise HTTPException(422,'原输入疑似含明文凭据，未复制或回显，请保留原记录并单独核对。')
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        raise HTTPException(422,'保存输入编码无效或超过128KB复制范围，未截断或转换数值。') from None
    numeric=any(type(v) is int and abs(v)>9007199254740991 or type(v) is float and v.is_integer() and abs(v)>9007199254740991 for v in value.values())
    warnings=['只准备自由试跑输入文字，不复制旧样例选择、预期、通过结论或会话ID，不保存任务或派发请求。',
        '尚未核对当前成果入口、发布图、凭据、资源和费用；请按新版本重新检查并明确确认。']
    if run.get('revision')!=task['revision'] or run.get('environment_id')!=task.get('environment_id') or run.get('app_id')!=task.get('dify_app_id'):
        warnings.append('原修订、环境或App与当前不同；复制输入不代表可以复用原资源授权或运行上下文。')
    if numeric:warnings.append('含浏览器不能安全发送的数值；仅无损保留文字，实际试跑仍会按既有规则拒绝，须先人工核对数值表示。')
    return {'schema_version':1,'task_id':task['id'],'revision':task['revision'],'run_id':run_id,
        'source_revision':run.get('revision'),'source_status':run['status'],'input_text':text,
        'input_sha256':hashlib.sha256(text.encode()).hexdigest(),'numeric_review_required':numeric,
        'warnings':warnings,'verification':'saved_scalar_input_draft_only',
        'task_changed':False,'network_requested':False,'automatic_execution':False,'business_verified':False,
        'case_copied':False,'conversation_copied':False,'current_schema_checked':False}


def register(h):
    router=APIRouter()
    @router.get('/api/tasks/{item_id}/runs/{run_id}/input-copy-preview')
    def read(item_id:str,run_id:str,response:Response,revision:int=Query(ge=1)):
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision);h.require_idle(task)
            response.headers['Cache-Control']='no-store'
            return preview(task,run_id)
    h.app.include_router(router)
