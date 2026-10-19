"""Local metadata-only index. Never query Dify or select credentials/form/DSL content."""
import sqlite3,uuid
from datetime import datetime
from fastapi import HTTPException,Query
from .schedule_stop import binding as schedule_binding
from .run_diagnostics import binding
from .providers import checked_url
from .conversation_state import safe_text
from urllib.parse import unquote

KINDS={'human_runtime_plan':'人工资源准备方案','human_runtime_run':'人工运行资源','human_decision':'人工决定','schedule_publication':'新定时应用发布','schedule_enable':'触发器启用','schedule_stop':'触发器停用','runtime_file_upload':'文件单次上传','runtime_file_run':'文件工作流单次试跑'}
STATES={'platform_failed','verifying','uploaded','uploaded_stale','discarded','prepared','prepared_unapproved','approved_executing','executing','submitting','submitting_decision','waiting_human','awaiting_resume','accepted','unknown','not_dispatched','platform_finished','published_and_disabled','stopped_unverified_publication','stop_not_confirmed','disabled_observed_later','enabled_observed_later','enabled','already_enabled','disabled','already_disabled','not_confirmed'}
ONGOING={'verifying','executing','submitting','submitting_decision','waiting_human','awaiting_resume'}
UNCERTAIN={'uploaded_stale','unknown','stop_not_confirmed','not_confirmed','stopped_unverified_publication'}
ACTIVE={'enabled','already_enabled','enabled_observed_later'}
NOTE='这里只读本机资源检查点，不查询Dify或重复写入。当前流程删除节点或改了修订，旧独立资源仍保留。平台状态可能变化；技术状态不等于自然运行或客户业务通过。原目标地址无法可靠恢复时不猜新连接；正文、DSL、输入和凭据不进入摘要。'
FIELDS=('id','revision','state','app_id','workflow_run_id','form_id','trigger_id','environment_id','environment_url','environment_binding','environment_binding_sha256','created_at','approved_at','updated_at','completed_at','run_id','plan_id','human_submission_attempted')
OBS_FIELDS=('observed_status','observed_at','reconciled_status','reconciled_state','reconciled_at','resume_evidence.platform_status','resume_evidence.checked_at')
STATUS={'enabled','disabled','rate_limited','unknown','missing','ambiguous','paused','running','succeeded','failed','stopped','partial-succeeded'}

def canonical(value):
    try:return str(uuid.UUID(value)) if isinstance(value,str) else None
    except (ValueError,TypeError,AttributeError):return None
def timestamp(value):
    try:
        if not isinstance(value,str) or len(value)>80:return None
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.isoformat() if parsed.tzinfo else None
    except ValueError:return None
def address(value):
    try:return checked_url(value) if isinstance(value,str) and safe_text(unquote(value),2048) else None
    except ValueError:return None

def observation(row):
    candidates=[]
    for status,at in ((row.get('observed_status'),row.get('observed_at')),(row.get('reconciled_status') or row.get('reconciled_state'),row.get('reconciled_at')),(row.get('resume_evidence.platform_status'),row.get('resume_evidence.checked_at'))):
        date=timestamp(at)
        if isinstance(status,str) and status in STATUS and date:candidates.append((datetime.fromisoformat(date),status,date))
    if not candidates:return None,None
    latest=max(c[0] for c in candidates);same=[c for c in candidates if c[0]==latest]
    return ('conflicting_observations' if len({c[1] for c in same})>1 else same[0][1],same[0][2])

def flags(state,latest,kind):
    ongoing=state in ONGOING
    enabled=state in ACTIVE
    if kind=='human_runtime_run' and latest:ongoing=latest in {'paused','running','conflicting_observations'} or state in {'executing','submitting_decision'}
    if kind in {'schedule_publication','schedule_enable','schedule_stop'} and latest:enabled=latest=='enabled'
    return ongoing,state in UNCERTAIN or state not in STATES or latest in {'unknown','missing','ambiguous','rate_limited','conflicting_observations'},enabled


class ResourceProgress:
    def __init__(self,host):self.h=host
    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/resource-progress')
        def read(item_id:str,limit:int=Query(default=10,ge=1,le=25)):
            return self.snapshot(item_id,limit)

    def snapshot(self,item_id,limit=10,expected_revision=None):
        h=self.h
        if type(limit)is not int or not 1<=limit<=25:raise HTTPException(422,'资源索引展示上限须为1—25真正整数。')
        with h.store.lock:
            task=h.get_task(item_id)
            if expected_revision is not None:h.require_revision(task,expected_revision)
            groups=[];entries=[];totals={'total':0,'ongoing':0,'uncertain':0,'enabled_observed':0}
            try:
                with h.store.connect() as conn:
                    corrupt=bool(conn.execute('SELECT 1 FROM objects WHERE kind IN ('+','.join('?' for _ in KINDS)+') AND NOT json_valid(value) LIMIT 1',tuple(KINDS)).fetchone())
                    for kind,label in KINDS.items():
                        where="kind=? AND json_valid(value) AND CASE WHEN json_valid(value) THEN json_extract(value,'$.task_id') END=?"
                        count=conn.execute('SELECT count(*) FROM objects WHERE '+where,(kind,item_id)).fetchone()[0]
                        projections=','.join("coalesce(json_extract(value,'$.form_id'),json_extract(value,'$.form.form_id'))" if field=='form_id' else "json_extract(value,'$."+field+"')" for field in FIELDS+OBS_FIELDS)
                        rows=conn.execute("SELECT id,json_type(value,'$.revision'),"+projections+' FROM objects WHERE '+where+' ORDER BY rowid DESC LIMIT ?',(kind,item_id,limit)).fetchall()
                        status_fields=('state',)+OBS_FIELDS
                        statuses=[dict(zip(status_fields,r)) for r in conn.execute('SELECT '+','.join("json_extract(value,'$."+f+"')" for f in status_fields)+' FROM objects WHERE '+where,(kind,item_id))]
                        # Totals cover full owned history; presentation is bounded separately.
                        counters=[flags(r['state'],observation(r)[0],kind) for r in statuses]
                        stats={'total':count,'ongoing':sum(r[0] for r in counters),'uncertain':sum(r[1] for r in counters),'enabled_observed':sum(r[2] for r in counters)}
                        for key,value in stats.items():totals[key]+=value
                        groups.append({'kind':kind,'label':label,**stats,'shown':len(rows),'history_truncated':count>limit})
                        for raw in rows:
                            row=dict(zip(FIELDS+OBS_FIELDS,raw[2:]));rid=canonical(raw[0]);valid_id=rid and canonical(row['id'])==rid;state=row['state'] if row['state'] in STATES and valid_id else 'unrecognized_record'
                            env_id=canonical(row['environment_id']);env=h.store.get('environment',env_id) if env_id else None
                            original_url=address(row['environment_url'])
                            if not original_url and env and schedule_binding(env)==row['environment_binding_sha256']:original_url=address(env.get('base_url'))
                            current_matches=bool(env and (binding(env)==row['environment_binding'] or schedule_binding(env)==row['environment_binding_sha256']))
                            rev=row['revision'] if raw[1]=='integer' and type(row['revision'])is int and row['revision']>0 else None
                            parent_id=canonical(row['run_id']) if kind=='human_decision' else None
                            if parent_id:
                                parent=conn.execute("SELECT json_extract(value,'$.task_id'),json_extract(value,'$.app_id'),json_extract(value,'$.workflow_run_id') FROM objects WHERE kind='human_runtime_run' AND id=? AND json_valid(value)",(parent_id,)).fetchone()
                                if not parent or parent[0]!=item_id or not canonical(parent[1]) or canonical(parent[1])!=canonical(row['app_id']) or not canonical(parent[2]) or canonical(parent[2])!=canonical(row['workflow_run_id']):parent_id=None
                            latest,observed_at=observation(row);ongoing,uncertain,enabled=flags(state,latest,kind)
                            entries.append({'id':rid if valid_id else None,'kind':kind,'label':label,'state':state,'revision':rev,'current_revision':rev==task['revision'],'ongoing':ongoing,'uncertain':uncertain,'enabled_observed':enabled,'latest_observed_status':latest,'latest_observed_at':observed_at,'app_id':canonical(row['app_id']),'workflow_run_id':canonical(row['workflow_run_id']),'parent_run_id':parent_id,'form_id':canonical(row['form_id']),'trigger_id':canonical(row['trigger_id']),'environment_id':env_id,'environment_url':original_url,'original_profile_matches':current_matches,'current_task_target':current_matches and task.get('environment_id')==env_id,'created_at':timestamp(row['created_at']) or timestamp(row['approved_at']),'updated_at':timestamp(row['updated_at']) or timestamp(row['completed_at']),'business_verified':False})
            except (sqlite3.Error,ValueError,TypeError):raise HTTPException(503,'本机资源索引暂时无法安全读取，原记录未改动；没有平台请求。') from None
            return {'task_id':item_id,'revision':task['revision'],'captured_at':h.now(),'groups':groups,'records':entries,'totals':totals,'limit_per_kind':limit,'history_truncated':any(g['history_truncated'] for g in groups),'unattributable_corrupt_record_present':corrupt,'platform_checked':False,'business_verified':False,'note':NOTE}
