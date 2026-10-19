"""Paused platform runs: bounded receipts, no form tokens or implicit resubmission."""
import asyncio,copy,hashlib,json,uuid
from fastapi import HTTPException
from .dify import DifyError
from .run_diagnostics import binding
from .schedule_observation import CredentialSnapshot

NOTE='平台运行暂停，不是业务通过或执行失败。表单正文、提交令牌和其它暂停原文不保存；请到原Dify应用处理。Sierra没有提交决定、恢复、取消或重跑。只读看到终态仍不证明原方案或业务验收通过。'
TERMINAL={'succeeded','failed','stopped','partial-succeeded'}


def canonical(value):
    try:return str(uuid.UUID(value)) if isinstance(value,str) else None
    except (ValueError,AttributeError):return None


def receipt(value):
    data=value.get('data') if isinstance(value,dict) else None
    rid=canonical(data.get('id')) if isinstance(data,dict) else None
    top=canonical(value.get('workflow_run_id')) if isinstance(value,dict) else None
    workflow=canonical(data.get('workflow_id')) if isinstance(data,dict) else None
    safe={'workflow_run_id':rid,'data':{'id':rid,'workflow_id':workflow,'status':'paused','outputs':{}},'waiting_state':{'state':'platform_paused','business_verified':False,'source_verified':False,'form_credentials_retained':False,'pause_details_retained':False,'note':NOTE}}
    if not isinstance(data,dict) or data.get('status')!='paused' or not rid or not top or top!=rid or not workflow:raise DifyError('平台返回暂停但运行标识不可信，结果可能未知；未保存表单凭据，不自动重跑。',result=safe)
    nodes=data.get('paused_nodes')
    safe['waiting_state']['paused_node_count']=len(nodes) if isinstance(nodes,list) and len(nodes)<=200 else None
    return safe


class DifyPaused(DifyError):pass


def stamp(row):return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class WorkflowWaiting:
    def __init__(self,host):self.h=host

    def require_no_waiting(self,task,env):
        if any(r.get('kind')=='run' and (r.get('status')=='waiting_platform' or r.get('status')=='unknown' and isinstance(r.get('result'),dict) and isinstance(r['result'].get('waiting_state'),dict)) and r.get('environment_id')==env['id'] and r.get('app_id')==task.get('dify_app_id') for r in task.get('runs',[])):raise HTTPException(409,'原目标还有平台运行等待处理或暂停标识未知，请到Dify处理并只读核对原运行；不能用再次试跑替代恢复或取消。')

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/runs/{run_id}/waiting-state')
        async def check(item_id:str,run_id:str):
            with h.store.lock:
                task=h.get_task(item_id);row=next((r for r in task.get('runs',[]) if r.get('id')==run_id),None)
                if not row or row.get('kind')!='run' or row.get('app_type')!='workflow' or row.get('status') not in {'waiting_platform','platform_finished'}:raise HTTPException(422,'仅主动核对本任务已保存的平台等待记录，不派发新运行。')
                saved=copy.deepcopy(row);rid=canonical((saved.get('result') or {}).get('workflow_run_id'));app_id=canonical(saved.get('app_id'))
                env=copy.deepcopy(h.store.get('environment',saved.get('environment_id')))
                if not rid or not app_id or not env or env.get('version')!='1.17.1' or binding(env)!=saved.get('environment_binding'):raise HTTPException(409,'原等待运行、应用或环境不可可靠核对，不改用当前任务的新连接。')
                credentials=CredentialSnapshot(h.store,env['id']);original_stamp=stamp(saved)
            def context():
                with h.store.lock:
                    current=h.store.get('environment',env['id']);task=h.get_task(item_id);record=next((r for r in task.get('runs',[]) if r.get('id')==run_id),None)
                    if not current or binding(current)!=binding(env) or not credentials.unchanged(h.store) or not record or stamp(record)!=original_stamp:raise HTTPException(409,'只读期间原连接或等待记录改变，未保存旧状态；没有重发运行。')
            try:
                context();value=await asyncio.wait_for(h.DifyClient(env,credentials).workflow_run_detail(app_id,rid),timeout=60);context()
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except asyncio.TimeoutError:raise HTTPException(504,'原运行只读核对超时，没有重复运行或提交决定。') from None
            status=value.get('status') if isinstance(value,dict) else None
            if not isinstance(value,dict) or canonical(value.get('id'))!=rid or not isinstance(status,str) or status not in TERMINAL|{'paused','running'}:raise HTTPException(502,'原运行ID或状态不可信，未猜测终态或保存原文。')
            observation={'platform_status':status,'checked_at':h.now(),'business_verified':False,'source_verified':False,'form_credentials_retained':False,'pause_details_retained':False,'note':NOTE}
            with h.store.lock:
                context();task=h.get_task(item_id);row=next(r for r in task['runs'] if r['id']==run_id)
                row['waiting_state']=observation
                if status in TERMINAL:
                    row.update(status='platform_finished',platform_finished_observed_at=h.now())
                    if task.get('status')=='waiting_platform' and task.get('environment_id')==env['id'] and task.get('dify_app_id')==app_id and not any(r.get('status')=='waiting_platform' for r in task.get('runs',[])):task['status']='imported'
                h.save_task(task)
            return {'task_id':item_id,'run_id':run_id,'workflow_run_id':rid,'app_id':app_id,'environment_id':env['id'],'record_status':row['status'],'observation':observation}
