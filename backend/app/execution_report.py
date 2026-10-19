"""Delivery snapshot of saved stop policies; no dispatch or free-text audit."""
def snapshot(h,task):
 with h.store.lock:
  limits=h.execution_limits.state(task);watch=h.failure_watch.state(task)
  decisions=[r for r in h.store.list('failure_decision') if r['task_id']==task['id']]
  groups=[{k:g[k] for k in ('run_ids','latest_run_id','consecutive_failures','nodes','permission')} for g in watch['paused_groups']]
  return {'task_revision':task['revision'],'captured_at':h.now(),'verification':'saved_controls_not_business_acceptance',
          'policy':{k:limits['policy'][k] for k in ('policy_revision','max_started_runs','max_total_minutes','max_reported_cost_usd')},
          'usage':{k:limits[k] for k in ('started_runs','known_elapsed_seconds','unknown_duration_runs','known_reported_usd','unavailable_usd_executions','cost_summary_truncated')},
          'can_start_by_limits':limits['can_start'],'limit_blockers':limits['blockers'],'limit_note':limits['note'],
          'repeated_failures':groups,'repeated_failure_note':watch['note'],
          'decision_count':len(decisions),'decision_audit':[{k:r.get(k) for k in ('revision','action','status','created_at','used_at')} for r in decisions[:500]],'audit_truncated':len(decisions)>500,
          'note':'本报告快照中的策略与重复失败处理，不是资源许可、可运行或业务验收证明。许可使用后不会自动续期；处理原因全文与重现输入不在本分区导出。审计超过500条时只列最新500条，明确保留总数。'}
