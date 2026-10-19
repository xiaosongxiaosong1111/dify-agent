"""Explicit readonly schedule observations. No publish/enable/disable/model calls."""
import asyncio,copy,hashlib,json,uuid
from fastapi import HTTPException,Query
from .dsl_roundtrip import parse,validate_preserved
from .diagnostic_graph_source import fingerprint
from .dify import DifyError

NOTE='只读所选App的发布核心图和触发器状态，两次远端读取不是原子快照，状态可能已经变化；不证明应用归属、完整特性、定时实际运行或未来不会变化。disabled仅阻止未来轮询派发，不取消已入队请求；没有发布、启用、停用或模型调用。'


class CredentialSnapshot:
    """Transient same-environment credentials; never persist or cross owners."""
    def __init__(self,store,owner):
        self.owner=owner
        self.values={key:store.secret(owner,key) for key in ('console_token','csrf_token')}

    def secret(self,owner,key):return self.values.get(key) if owner==self.owner else None

    def unchanged(self,store):return all(store.secret(self.owner,key)==value for key,value in self.values.items())


def local_source(h,task):
    if task['app_type']!='workflow':raise HTTPException(422,'调度状态核对只适配Workflow，不改变应用类型。')
    try:
        uuid.UUID(task['id']);path=h.artifact_path(task).resolve();folder=(h.DATA_ROOT/task['id']).resolve()
        if path.parent!=folder:raise ValueError('成果文件不在本任务目录。')
        with path.open('rb') as stream:raw=stream.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('成果超过2MB，不截断核对。')
        root=parse(raw.decode('utf-8'),task['app_type']);check=validate_preserved(root)
        if not check['valid']:raise ValueError('最终成果静态检查未通过，请先核对。')
        entries=[n for n in root['workflow']['graph']['nodes'] if n['data']['type']=='trigger-schedule']
        if len(entries)!=1:raise ValueError('最终成果须有唯一已适配的定时入口。')
        graph=fingerprint(root['workflow']['graph'])
        if not graph:raise ValueError('成果核心图无法可靠核对。')
        return {'entry_id':entries[0]['id'],'artifact_sha256':hashlib.sha256(raw).hexdigest(),'graph':graph}
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:raise HTTPException(422,'无法核对定时成果：'+str(exc)) from None


def triggers(value,entry_id):
    if not isinstance(value,dict) or not isinstance(value.get('data'),list) or len(value['data'])>200:raise DifyError('触发器响应不是最多200项的明确数组，不截断或猜测。')
    selected=[];others=0
    for row in value['data']:
        if not isinstance(row,dict):raise DifyError('触发器响应含未知结构。')
        if row.get('trigger_type')!='trigger-schedule' or row.get('node_id')!=entry_id:others+=1;continue
        try:rid=str(uuid.UUID(row['id']))
        except (ValueError,TypeError,KeyError,AttributeError):raise DifyError('定时触发记录缺少可信UUID，未替换为其他记录。') from None
        status=row.get('status');status=status if isinstance(status,str) and status in {'enabled','disabled','rate_limited'} else 'unknown'
        selected.append({'trigger_id':rid,'entry_id':entry_id,'status':status})
    return {'records':selected,'other_record_count':others,'state':selected[0]['status'] if len(selected)==1 else 'missing' if not selected else 'ambiguous'}


class ScheduleObservation:
    def __init__(self,host):self.h=host

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/schedule-observations')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('schedule_observation') if r.get('task_id')==item_id]
            rows.sort(key=lambda r:r.get('created_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':rows[:10],'history_truncated':len(rows)>10,'note':NOTE}

        @h.app.get('/api/tasks/{item_id}/schedule-observe')
        async def observe(item_id:str,app_id:str,revision:int=Query(ge=1)):
            try:target=str(uuid.UUID(app_id))
            except (ValueError,TypeError,AttributeError):raise HTTPException(422,'请明确输入目标App的有效UUID，不请求任意路径。') from None
            with h.store.lock:
                task=copy.deepcopy(h.get_task(item_id));h.require_revision(task,revision)
                source=local_source(h,task);env=copy.deepcopy(h.environment(task));binding=[env['id'],env['base_url'],env['version']]
                credentials=CredentialSnapshot(h.store,env['id'])
            client=h.DifyClient(env,credentials)
            def check_context():
                with h.store.lock:
                    current=h.get_task(item_id);h.require_revision(current,revision)
                    now_env=h.environment(current)
                    if [now_env['id'],now_env['base_url'],now_env['version']]!=binding or not credentials.unchanged(h.store) or local_source(h,current)!=source:raise HTTPException(409,'只读期间成果、环境或凭据发生变化，未使用新连接继续旧读取或保存旧状态；请重新核对。')
            try:
                async def read():
                    check_context()
                    published=await client.published_workflow(target)
                    check_context()
                    status=triggers(await client.app_triggers(target),source['entry_id'])
                    return published,status
                published,status=await asyncio.wait_for(read(),timeout=60)
            except DifyError as exc:raise HTTPException(502,str(exc)) from None
            except asyncio.TimeoutError:raise HTTPException(504,'调度只读核对超过60秒，未保存完整观察；没有自动重试或调度操作。') from None
            try:published_id=str(uuid.UUID(published['id'])) if isinstance(published,dict) else None
            except (ValueError,KeyError,TypeError,AttributeError):published_id=None
            remote=fingerprint(published.get('graph')) if isinstance(published,dict) and published_id else None
            matched=bool(remote and remote['digest']==source['graph']['digest'])
            record={'id':str(uuid.uuid4()),'task_id':item_id,'revision':revision,'app_id':target,'environment_id':env['id'],'environment_binding_sha256':hashlib.sha256(json.dumps(binding).encode()).hexdigest(),'entry_id':source['entry_id'],'artifact_sha256':source['artifact_sha256'],'local_graph_digest':source['graph']['digest'],'published_workflow_id':published_id,'published_graph_digest':remote['digest'] if remote else None,'source_state':'matched' if matched else 'different_graph' if remote else 'published_unavailable','core_graph_matched':matched,'trigger':status,'created_at':h.now(),'verification':'readonly_observation','ownership_verified':False,'activation_verified':False,'note':NOTE}
            with h.store.lock:
                check_context()
                h.store.put('schedule_observation',record['id'],record)
            return record
