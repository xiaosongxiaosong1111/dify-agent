"""Reuse the local metadata index for handoff; never infer completion or read secrets."""
from fastapi import HTTPException

NOTE='这部分导出六类独立资源元数据，不含审核正文、客户输入、完整DSL或凭据。历史属于原修订与原目标；本机观察不是平台实时状态，不证明费用已结清、资源已取消、自然触发、审核归属或客户验收。未知结果不盲目重试；请在原Dify按原标识核对。'


def snapshot(h,task):
    try:value=h.resource_progress.snapshot(task['id'],limit=25,expected_revision=task['revision'])
    except HTTPException as exc:
        if exc.status_code==409:raise
        return {'task_revision':task['revision'],'captured_at':h.now(),'state':'local_index_unavailable','platform_checked':False,'business_verified':False,'records':None,'totals':None,'handoff_clearance_verified':False,'blockers':['本机独立资源摘要暂未安全读取，不能用缺失或空列表证明没有外部资源待办。'],'note':NOTE}
    blockers=[]
    totals=value['totals']
    if totals['ongoing']:blockers.append(f"本机记录含{totals['ongoing']}条处理／等待阶段，请核对原App／Run／Form；当前方案变更不代表原流程取消。")
    if totals['uncertain']:blockers.append(f"本机记录含{totals['uncertain']}条未知／未确认操作，不重复创建、发布、启停或提交，先核对原目标。")
    if totals['enabled_observed']:blockers.append(f"本机记录含{totals['enabled_observed']}条观察启用阶段，可能仍持续调度；停用及费用仍需核对。")
    if value['history_truncated']:blockers.append('每类仅导出最近25条，但总数覆盖完整本机所属历史；更早记录未删除，不能排除旧等待／未知目标。')
    if value['unattributable_corrupt_record_present']:blockers.append('本机索引存在无法安全归属的损坏记录，待修复；不能据此给出完整外部资源结清结论。')
    if any(not r['original_profile_matches'] for r in value['records']):blockers.append('部分原环境已变化或不可核对，不将旧App ID交给当前新连接；按已保存原地址和标识处理。')
    return {'task_revision':task['revision'],'captured_at':value['captured_at'],'state':'saved_metadata_snapshot','verification':'local_metadata_not_platform_or_business_acceptance','platform_checked':False,'business_verified':False,'handoff_clearance_verified':False,'groups':value['groups'],'totals':totals,'limit_per_kind':25,'history_truncated':value['history_truncated'],'unattributable_corrupt_record_present':value['unattributable_corrupt_record_present'],'records':value['records'],'blockers':blockers,'note':NOTE}
