"""Local concrete preparation for a limited HITL run; no external execution."""
import copy,hashlib,json,uuid
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,Field
from .plan_drafts import DraftRoute
from .dsl_roundtrip import parse,validate_preserved
from .human_review import preserved
from .diagnostic_graph_source import fingerprint
from .schedule_stop import digest
from .run_diagnostics import binding
from .conversation_state import safe_text
from .console_connection import summary as connection_summary

LIMITATION='准备只在本机冻结方案，不请求Dify。用户另行批准后，专用执行入口最多新建一个纯模板根审核App、发布一次、生成专属Key、试跑一次并采集等待表单；最多4次只读核对、总处理180秒（采集80秒）。不强制指定审核人，不通知或提交决定，不覆盖原应用／Key，失败不重试或清理；实际平台联调尚未验收。'
PUBLIC={'id','task_id','revision','environment_id','environment_label','environment_url','environment_version','connection_state','artifact_sha256','graph_digest','application_name','input','review','resource_counts','paid_dependencies','role_restriction_enforced','automatic_retry','overwrites_existing_apps','leftovers_possible','data_destination','execution_available','state','resource_token','created_at','note','outbound_dsl','max_remote_reads','max_seconds','stream_seconds'}


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    input:dict


def contains_saved_secret(value,secrets):
    """Check decoded scalar text, including YAML escapes, without retaining secrets."""
    if isinstance(value,str):return any(s and s in value for s in secrets)
    if isinstance(value,list):return any(contains_saved_secret(v,secrets) for v in value)
    if isinstance(value,dict):return any(contains_saved_secret(k,secrets) or contains_saved_secret(v,secrets) for k,v in value.items())
    return False


def source(h,task):
    if task['app_type']!='workflow':raise HTTPException(422,'人工运行资源方案首批仅Workflow，不改变类型。')
    try:
        uuid.UUID(task['id'])
        path=h.artifact_path(task).resolve();folder=(h.DATA_ROOT/task['id']).resolve()
        if path.parent!=folder:raise ValueError('成果不在当前任务目录。')
        with path.open('rb') as stream:raw=stream.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('成果超过2MB，不截断。')
        root=parse(raw.decode('utf-8'),task['app_type']);check=validate_preserved(root)
        if not check['valid']:raise ValueError('最终成果静态检查未通过。')
        workflow=root['workflow'];nodes=workflow['graph']['nodes'];kinds=[n['data']['type'] for n in nodes]
        if set(kinds)-{'start','human-input','template-transform','end'} or kinds.count('start')!=1 or kinds.count('human-input')!=1:raise ValueError('首批运行方案仅一个根审核、开始、纯文字模板与终点，不包含模型／知识库／HTTP／代码／文件／容器／定时或多个审核。')
        if any(n.get('parentId') for n in nodes) or root.get('dependencies') or workflow.get('environment_variables') or workflow.get('conversation_variables') or workflow.get('rag_pipeline_variables'):raise ValueError('首批不接依赖、容器或环境／会话／管道变量，不删字段后通过。')
        features=workflow.get('features')
        allowed={'file_upload','opening_statement','retriever_resource','sensitive_word_avoidance','suggested_questions','suggested_questions_after_answer','speech_to_text','text_to_speech','more_like_this'}
        if not isinstance(features,dict) or set(features)-allowed or features.get('opening_statement') not in (None,'') or features.get('suggested_questions') not in (None,[]):raise ValueError('首批不接额外应用特性或开场白／建议问题，不猜是否引发外部服务。')
        for key,value in features.items():
            if key not in {'opening_statement','suggested_questions'} and (not isinstance(value,dict) or value.get('enabled') is not False):raise ValueError('首批附加应用特性须明确关闭，不补默认。')
        start=next(n for n in nodes if n['data']['type']=='start')
        if any(v.get('type') not in {'text-input','paragraph','select'} for v in start['data'].get('variables',[])):raise ValueError('首批开始输入仅已声明文字，不接文件或其它类型。')
        for field in start['data'].get('variables',[]):
            if field.get('variable','').lower() in {'api_key','apikey','password','token','secret','authorization'} or 'default' in field and field['default'] is not None and not safe_text(field['default'],10000):raise ValueError('首批不接凭据字段或含凭据／未知结构的默认输入，不将秘密打包出站。')
        for node in nodes:
            if node['data']['type']=='template-transform':
                data=node['data'];text=data.get('template')
                if not isinstance(text,str) or not safe_text(text,16000) or data.get('variables')!=[] or any(mark in text for mark in ('{{','{%','{#')):raise ValueError('首批下游只允许无变量／表达式的固定文字模板，不执行动态Jinja内容。')
        review=next(n for n in nodes if n['data']['type']=='human-input');cfg=preserved(review['data'])
        name=root['app'].get('name')
        if not safe_text(name,100) or not name.strip():raise ValueError('应用名称不可信或含凭据，请先复核。')
        graph=fingerprint(workflow['graph'])
        if not graph:raise ValueError('完整核心图无法可靠冻结。')
        return {'artifact_sha256':hashlib.sha256(raw).hexdigest(),'graph_digest':graph['digest'],'application_name':name,'root':root,'outbound_dsl':raw.decode('utf-8'),'review':{'node_id':review['id'],'object_template':cfg['form_content'],'actions':cfg['user_actions'],'timeout':cfg['timeout'],'timeout_unit':cfg['timeout_unit'],'delivery_methods':cfg['delivery_methods'],'rendered_form_available':False}}
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:raise HTTPException(422,'无法准备人工运行资源方案：'+str(exc)) from None


class HumanRuntimePlan:
    def __init__(self,host):self.h=host
    def public(self,row):return {k:copy.deepcopy(v) for k,v in row.items() if k in PUBLIC}
    def register(self):
        h=self.h;router=APIRouter(route_class=DraftRoute)
        @router.post('/api/tasks/{item_id}/human-runtime/prepare')
        def prepare(item_id:str,payload:Prepare):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);h.require_intake(task)
                if not task.get('requirements_confirmed') or not task.get('configuration_confirmed'):raise HTTPException(409,'请先确认当前需求及配置，再准备运行资源方案。')
                frozen=source(h,task);env=h.environment(task)
                if env.get('version')!='1.17.1':raise HTTPException(422,'仅适配Dify 1.17.1，不猜其他版本资源和人工表单行为。')
                try:
                    encoded=json.dumps(payload.input,ensure_ascii=False,allow_nan=False).encode()
                    if len(encoded)>20000 or any(not isinstance(k,str) or not safe_text(v,10000) or k.lower() in {'api_key','apikey','password','token','secret','authorization'} for k,v in payload.input.items()):raise ValueError('输入仅最多20KB已声明文字，不填写凭据或未支持结构。')
                    from .start_inputs import form_schema,check_values
                    fields=form_schema(frozen['root'])['fields']
                    check_values(fields,payload.input)
                except (ValueError,TypeError) as exc:raise HTTPException(422,'试跑输入未通过：'+str(exc)) from None
                label=env.get('name');secrets=[h.store.secret(env['id'],key) for key in h.SECRET_FIELDS]
                provider_id=task.get('configuration',{}).get('assistant_provider_id')
                if provider_id:secrets.append(h.store.secret(provider_id,'api_key'))
                outgoing=frozen['outbound_dsl']+json.dumps(payload.input,ensure_ascii=False)
                if not safe_text(outgoing,2020000) or contains_saved_secret(frozen['root'],secrets) or contains_saved_secret(payload.input,secrets):raise HTTPException(422,'成果或输入包含当前连接凭据，不能打包到人工运行方案；请先移除秘密。')
                from .human_runtime_stream import render
                try:render(frozen['root'],payload.input)
                except ValueError as exc:raise HTTPException(422,str(exc)) from None
                connection=connection_summary(h.store.secret(env['id'],'console_token'),bool(h.store.secret(env['id'],'csrf_token')))
                row={'id':str(uuid.uuid4()),'task_id':item_id,'revision':payload.revision,'environment_id':env['id'],'environment_label':label if safe_text(label,255) and not any(s and s in label for s in secrets) else '所选Dify环境','environment_url':env['base_url'],'environment_version':env['version'],'environment_binding':binding(env),'connection_state':connection['state'],'artifact_sha256':frozen['artifact_sha256'],'graph_digest':frozen['graph_digest'],'application_name':frozen['application_name'],'input':copy.deepcopy(payload.input),'review':frozen['review'],'resource_counts':{'new_apps':1,'publish_attempts':1,'new_app_keys':1,'workflow_run_attempts':1,'expected_human_forms':1,'human_submissions':0},'paid_dependencies':{'model':False,'embedding':False,'rerank':False,'http':False,'code':False,'notification':False,'host_cost_guaranteed_zero':False},'role_restriction_enforced':False,'automatic_retry':False,'overwrites_existing_apps':False,'leftovers_possible':True,'data_destination':env['base_url'],'execution_available':True,'outbound_dsl':frozen['outbound_dsl'],'max_remote_reads':4,'max_seconds':180,'stream_seconds':80,'created_at':h.now(),'note':LIMITATION}
                row['resource_token']=digest(row);row['state']='prepared_unapproved';h.store.put('human_runtime_plan',row['id'],row);return self.public(row)
        @router.get('/api/tasks/{item_id}/human-runtime')
        def history(item_id:str):
            task=h.get_task(item_id);rows=[r for r in h.store.list('human_runtime_plan') if r.get('task_id')==item_id];rows.sort(key=lambda r:r.get('created_at',''),reverse=True)
            return {'task_id':item_id,'revision':task['revision'],'records':[self.public(r) for r in rows[:10]],'history_truncated':len(rows)>10,'note':LIMITATION}
        h.app.include_router(router)
