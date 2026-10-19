"""Read a stopped planner candidate as exact text; never adopt or execute it."""
import hashlib
import json
from fastapi import HTTPException
from .plan_drafts import inspect_text


def candidate(task, run_id):
    matches=[r for r in task.get('planning_runs',[]) if isinstance(r,dict) and r.get('id')==run_id]
    if len(matches)!=1:raise HTTPException(404,'没有找到唯一的规划记录，未读取候选。')
    run=matches[0]
    if run.get('kind') not in (None,'plan'):
        raise HTTPException(422,'这不是流程规划记录，不能当流程候选载入。')
    if run.get('status') not in ('paused','interrupted'):
        raise HTTPException(409,'仅可读取已暂停或中断的规划候选，请先核对记录状态。')
    revision=run.get('revision');current=task.get('revision')
    if type(revision) is not int or revision<1 or type(current) is not int or current<1:
        raise HTTPException(422,'规划修订记录无效，未读取候选。')
    plan=run.get('last_candidate')
    if not isinstance(plan,dict) or not plan:
        raise HTTPException(422,'本记录没有保留完整计划对象；不会从截断响应或澄清文字猜测补齐。')
    try:
        text=json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False)
    except (ValueError,TypeError,RecursionError,OverflowError):
        raise HTTPException(422,'保留候选的编码或结构无效，未读取；不回显原文。') from None
    size,state=inspect_text(text)
    if state!='json_object':raise HTTPException(422,'保留候选不是可读取的完整JSON对象。')
    return {'task_id':task['id'],'planning_run_id':run_id,'input_revision':revision,'current_revision':current,
            'is_current_revision':revision==current,'app_type':task['app_type'],'plan_text':text,
            'source_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'byte_count':size,
            'verification':'retained_candidate_unverified','formal_plan_changed':False,
            'network_requested':False,'platform_checked':False,'business_verified':False}


def register(h):
    @h.app.get('/api/tasks/{item_id}/planning/{run_id}/candidate')
    def read(item_id:str,run_id:str):
        with h.store.lock:return candidate(h.get_task(item_id),run_id)
