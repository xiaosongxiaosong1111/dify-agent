"""Opt-in source-bound policy for the single curated planning rule tool."""
import copy,hashlib,json
from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StrictStr
from .plan_drafts import DraftRoute
from .provider_tool_probe import identity,strict_json,specification as probe_specification
from .planning_tool_protocol import TOOL,NODE_TYPES,MAX_INPUT_BYTES,MAX_RESULT_BYTES,encoded
from .node_guidance import lookup,TARGET_DIFY_VERSION,provenance

SCOPE_VERSION=1
SCOPE='仅Workflow/Chatflow完整规划，可由固定当前主模型请求一次sierra_lookup_node_rules，只读当前类型和Dify 1.17.1的检索/条件/Python/文字LLM公共规则及合成示例。不读任意文件、URL、客户资料或密钥，不执行代码/资源/网络。原规划上下文最多2MB，加规则结果最多32KB，模型最多2次HTTP、各请求最多6000输出tokens/120秒，共用一次规划总时间/费用和任务累计账本，不额外修复或换模型。未知用量、非法/多工具、来源/修订/暂停或预算失效即停；示例不是当前配置/批准/运行证明，重启不续派。保存策略不调用模型，轻量建议/其它助手/原生Agent不使用本策略。'


class PolicyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    policy_revision:StrictInt=Field(ge=0)
    scope_version:StrictInt
    enabled:StrictBool
    source_token:StrictStr|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    acknowledge_scope:StrictBool
    note:StrictStr=Field(max_length=2000)


class PolicyRoute(DraftRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:
                raw=await request.body()
                if request.method=='PATCH':
                    if len(raw)>8192 or not isinstance(strict_json(raw),dict):raise ValueError()
                elif raw:raise ValueError()
            except (ValueError,TypeError,UnicodeError,RecursionError):return JSONResponse(status_code=422,content={'detail':'规则工具策略须为无重复键/非有限数的明确有限JSON对象，未保存，不回显输入。'},headers={'Cache-Control':'no-store'})
            response=await original(request);response.headers['Cache-Control']='no-store';return response
        return guarded


class PlanningToolPolicy:
    def __init__(self,h):self.h=h

    def get(self,item_id):
        return self.h.store.get('planning_tool_policy',item_id) or {'id':item_id,'enabled':False,'policy_revision':0,'scope_version':SCOPE_VERSION,'source_token':None,'history':[]}

    def state(self,task,provider=None,*,policy_override=None):
        h=self.h;policy=self.get(task['id']) if policy_override is None else policy_override;blocker=None
        if task['app_type'] not in ('workflow','advanced-chat'):blocker='首批只读规则工具仅用于Workflow/Chatflow规划，不改变应用类型。'
        env=h.store.get('environment',task['environment_id']) if task.get('environment_id') else None
        declared=env.get('version') if env else TARGET_DIFY_VERSION
        if task.get('environment_id') and not env:blocker=blocker or '所选环境不存在，无法核对声明目标版本。'
        if declared!=TARGET_DIFY_VERSION:blocker=blocker or '声明目标版本与首批Dify 1.17.1规则不同，不能代用规则。'
        try:provider=provider or h.main_provider(task)
        except HTTPException:provider=None;blocker=blocker or '缺少当前任务主模型或密钥，不能准备模型工具路线。'
        if provider:
            public=h.provider_public(provider)
            if provider.get('protocol','openai-compatible')!='openai-compatible':blocker=blocker or '首批只适配OpenAI兼容工具协议。'
            elif not provider.get('pricing'):blocker=blocker or '主模型缺估算单价，不能预检两次调用。'
            check=(provider.get('checks') or {}).get('tools') or {}
            if public.get('capabilities',{}).get('tools')!='verified' or check.get('scope')!='single_function_request_only' or check.get('source_token')!=identity(provider):blocker=blocker or '当前主模型尚无有效的单次工具请求观察，请先明确测试并核对；不据文本/JSON成功猜工具能力。'
            try:probe_specification(provider)
            except ValueError:blocker=blocker or '主模型请求配置尚未适配本工具协议。'
        else:public=None
        if h.get_settings()['max_retries']<1:blocker=blocker or '全局自动修复上限为0，不允许此最多两次请求策略。'
        catalogue=lookup(task['app_type'],list(NODE_TYPES))
        catalogue_token=hashlib.sha256(encoded(catalogue)).hexdigest();schema_token=hashlib.sha256(encoded(TOOL)).hexdigest()
        source={'task_id':task['id'],'app_type':task['app_type'],'declared_target_version':declared,'provider_token':identity(provider) if provider else None,'schema_token':schema_token,'catalogue_token':catalogue_token}
        token=hashlib.sha256(encoded(source)).hexdigest()
        if policy['enabled'] and (policy.get('scope_version')!=SCOPE_VERSION or policy.get('source_token')!=token):blocker=blocker or '已确认工具范围/模型/规则库或声明版本已变化，需重新核对；不会找替代模型。'
        return {**copy.deepcopy(policy),'task_revision':task['revision'],'required_scope_version':SCOPE_VERSION,'current_source_token':token,'provider':public,'catalogue_token':catalogue_token,'tool_schema_token':schema_token,'catalogue':provenance(catalogue),'tool_name':TOOL['function']['name'],'allowed_node_types':list(NODE_TYPES),'ready':blocker is None,'blocker':blocker,'scope_note':SCOPE,'round_limits':copy.deepcopy(h.get_settings()),'max_model_http_requests':2,'max_local_queries':1,'max_input_bytes':MAX_INPUT_BYTES,'max_tool_result_bytes':MAX_RESULT_BYTES,'verification':'explicit_read_only_tool_policy_not_runtime_or_quality_proof'}

    def context(self,task,provider):
        policy=self.get(task['id'])
        if not policy['enabled']:return None
        state=self.state(task,provider)
        if not state['ready']:raise HTTPException(422,state['blocker'])
        return {key:state[key] for key in ('policy_revision','scope_version','current_source_token','catalogue_token','tool_schema_token')}

    def register(self):
        h=self.h;router=APIRouter(route_class=PolicyRoute)
        @router.get('/api/tasks/{item_id}/planning-tool-policy')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @router.patch('/api/tasks/{item_id}/planning-tool-policy')
        def save(item_id:str,payload:PolicyRequest):
            if payload.scope_version!=SCOPE_VERSION:raise HTTPException(409,'规则工具范围版本已变化，请重新读取。')
            if not payload.acknowledge_scope or not payload.note.strip():raise HTTPException(422,'请明确接受只读工具/数据/两次共享调用和费用边界，并说明原因。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);policy=self.get(item_id)
                if policy['policy_revision']!=payload.policy_revision:raise HTTPException(409,'规则工具策略已变化，请重新读取。')
                # Fresh confirmation may replace an obsolete enabled source.
                fresh={**policy,'enabled':False};original=policy
                if payload.enabled:
                    current=self.state(task,policy_override=fresh)
                    if not current['ready']:raise HTTPException(422,current['blocker'])
                    if payload.source_token!=current['current_source_token']:raise HTTPException(409,'主模型/规则库来源已变化，请重新核对，未保存。')
                elif payload.source_token is not None:raise HTTPException(422,'关闭时须清除来源指向。')
                before={key:copy.deepcopy(original.get(key)) for key in ('enabled','scope_version','source_token')};after={'enabled':payload.enabled,'scope_version':SCOPE_VERSION,'source_token':payload.source_token}
                policy['history'].append({'before':before,'after':after,'task_revision':task['revision'],'created_at':h.now(),'source':'user_confirmed','note':payload.note.strip()})
                policy.update(after);policy['policy_revision']+=1;h.store.put('planning_tool_policy',item_id,policy)
                return self.state(task)
        h.app.include_router(router)


def register(h):
    h.planning_tool_policy=PlanningToolPolicy(h);h.planning_tool_policy.register()
