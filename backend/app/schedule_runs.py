"""Readonly platform schedule evidence; no run invocation or business acceptance."""
import asyncio,copy,uuid
from fastapi import HTTPException,Query
from .schedule_observation import CredentialSnapshot,local_source
from .schedule_stop import binding
from .diagnostic_graph_source import fingerprint
from .dify import DifyError

STATUSES={'running','succeeded','failed','stopped','partial-succeeded','paused'}
NOTE='只读最近20条App日志中最多3条schedule来源的已登记运行；空列表不排除排队／未完成／更早运行。只核对ID、版本文字和核心图，不保存原图／输入输出／错误原文／身份；平台成功不等于业务验收，也不能证明同一发布版本ID。没有发起运行、发布或启停。'


def candidates(value):
    if not isinstance(value,dict) or not isinstance(value.get('data'),list) or len(value['data'])>20:raise DifyError('App日志须为最多20项明确数组，不截断或猜来源。')
    result=[];seen=set();other=0
    for row in value['data']:
        if not isinstance(row,dict):raise DifyError('App日志含未知结构。')
        run=row.get('workflow_run')
        if not isinstance(run,dict) or run.get('triggered_from')!='schedule':other+=1;continue
        try:rid=str(uuid.UUID(run['id']))
        except (ValueError,KeyError,TypeError,AttributeError):raise DifyError('schedule日志缺少可信运行UUID。') from None
        if rid in seen:raise DifyError('schedule日志的运行ID重复，不按重复记录充数。')
        seen.add(rid);result.append(run)
    return result[:3],len(result)>3,other


def evidence(summary,detail,published,source):
    rid=str(uuid.UUID(summary['id']))
    try:actual=str(uuid.UUID(detail['id'])) if isinstance(detail,dict) else None
    except (ValueError,KeyError,TypeError,AttributeError):actual=None
    versions=[summary.get('version'),detail.get('version') if isinstance(detail,dict) else None,published.get('version') if isinstance(published,dict) else None]
    version_match=all(isinstance(v,str) and 0<len(v)<=256 for v in versions) and len(set(versions))==1
    remote=fingerprint(published.get('graph')) if isinstance(published,dict) else None
    executed=fingerprint(detail.get('graph')) if isinstance(detail,dict) else None
    graph_match=bool(remote and executed and source['graph']['digest']==remote['digest']==executed['digest'])
    summary_status=summary.get('status');status=detail.get('status') if isinstance(detail,dict) else None
    known=status if isinstance(status,str) and status in STATUSES else 'unknown'
    status_match=known!='unknown' and summary_status==status
    matched=bool(actual==rid and version_match and graph_match and status_match)
    state='matched_platform_success' if matched and known=='succeeded' else 'matched_platform_non_success' if matched else 'source_not_proved'
    timestamp=detail.get('created_at') if isinstance(detail,dict) else None
    return {'run_id':rid,'triggered_from':'schedule','state':state,'status':known,'id_matched':actual==rid,'version_text_matched':version_match,'core_graph_matched':graph_match,'status_consistent':status_match,'execution_graph_digest':executed['digest'] if executed else None,'published_graph_digest':remote['digest'] if remote else None,'created_at_epoch':timestamp if type(timestamp)is int and timestamp>=0 else None,'business_verified':False,'same_published_workflow_id_verified':False}


class ScheduleRuns:
    def __init__(self,host):self.h=host

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/schedule-runs')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('schedule_runs') if r.get('task_id')==item_id]
            rows.sort(key=lambda r:r.get('created_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':rows[:10],'history_truncated':len(rows)>10,'note':NOTE}

        @h.app.get('/api/tasks/{item_id}/schedule-runs/read')
        async def read(item_id:str,app_id:str,revision:int=Query(ge=1)):
            try:target=str(uuid.UUID(app_id))
            except (ValueError,TypeError,AttributeError):raise HTTPException(422,'请明确有效App UUID，未请求日志。') from None
            with h.store.lock:
                task=copy.deepcopy(h.get_task(item_id));h.require_revision(task,revision)
                source=local_source(h,task);env=copy.deepcopy(h.environment(task));stamp=binding(env);credentials=CredentialSnapshot(h.store,env['id'])
            client=h.DifyClient(env,credentials)
            def context():
                with h.store.lock:
                    current=h.get_task(item_id);h.require_revision(current,revision)
                    if binding(h.environment(current))!=stamp or not credentials.unchanged(h.store) or local_source(h,current)!=source:raise HTTPException(409,'日志读取期间来源、环境或凭据改变，没有保存旧证据。')
            try:
                async def fetch():
                    context();published=await client.published_workflow(target);context()
                    logs=await client.workflow_app_logs(target);context();rows,truncated,other=candidates(logs)
                    items=[]
                    for row in rows:
                        context();detail=await client.workflow_run_detail(target,str(uuid.UUID(row['id'])));context()
                        items.append(evidence(row,detail,published,source))
                    return items,truncated,other,logs.get('has_more') is True
                items,truncated,other,has_more=await asyncio.wait_for(fetch(),timeout=60)
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except asyncio.TimeoutError:raise HTTPException(504,'调度日志只读采集超过60秒，未保存半条报告，不自动重试。') from None
            report={'id':str(uuid.uuid4()),'task_id':item_id,'revision':revision,'app_id':target,'environment_id':env['id'],'environment_binding_sha256':stamp,'artifact_sha256':source['artifact_sha256'],'entry_id':source['entry_id'],'runs':items,'schedule_detail_truncated':truncated,'log_page_has_more':has_more,'other_log_count':other,'created_at':h.now(),'verification':'readonly_schedule_platform_evidence','business_verified':False,'note':NOTE}
            with h.store.lock:context();h.store.put('schedule_runs',report['id'],report)
            return report
