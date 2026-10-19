"""Exact per-node mapping into a stateless, explicitly unverified target DSL draft."""
import copy,re,uuid,yaml
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from .agent_environment_mapping import MappingRoute,target_public,target_model
from .dsl_roundtrip import digest,parse,validate_preserved
from .workflow_resource_inventory import inventory,valid_uuid,identifier
from .parallel_preservation import candidates as parallel_candidates
from .preserved_loop import candidates as loop_candidates

MARKER='Sierra：跨环境目标草稿；模型、知识库、插件及保留的外部设置尚未在目标验证，未导入或试跑。'
PLUGIN=re.compile(r'^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+:[^\s:]+$')


def source_summary(root):
    observed=inventory(root,digest(root))
    if not observed['available'] or observed['blockers']:
        return {'available':False,'reason':'来源资源清单仍有未适配条件，保留全部原文；不准备部分目标模板。'}
    nodes=root['workflow']['graph']['nodes'];models={};rerankers={};datasets=[]
    for node in nodes:
        ident=node['id'];data=node['data']
        if data['type'] in {'llm','question-classifier','parameter-extractor'}:models[ident]=json_text(data['model'])
        if data['type']=='knowledge-retrieval':
            datasets.extend(i for i in data['dataset_ids'] if i not in datasets)
            if data['multiple_retrieval_config'].get('reranking_enable',True):rerankers[ident]=copy.deepcopy(data['multiple_retrieval_config']['reranking_model'])
    return {'available':True,'node_models_json':models,'dataset_ids':datasets,'node_rerankers':rerankers,
            'dependencies':[d['value']['marketplace_plugin_unique_identifier'] for d in root.get('dependencies',[])],
            'retained_settings':any(e['category'] in {'http','code_runtime','environment_variable','schedule','human_review'} for e in observed['entries']),
            'note':'来源模板只供明确复制后编辑，不能据此认定目标资源已存在；每个实际模型节点、知识库及重排须分别选择。'}


def json_text(value):
    import json
    return json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)


class Reranker(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:str=Field(min_length=1,max_length=256)
    model:str=Field(min_length=1,max_length=256)


class WorkflowMappingRoute(MappingRoute):
    field_error='流程映射字段无效，请核对修订、逐节点完整模型JSON、知识库、重排、插件和目标容器复核；不回显输入，未改任务或生成成果。'


class WorkflowMappingRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(gt=0)
    reference_id:str=Field(min_length=1,max_length=100)
    merge_token:str=Field(pattern='^[0-9a-f]{64}$')
    document_token:str=Field(pattern='^[0-9a-f]{64}$')
    choices:dict[str,str]=Field(default_factory=dict,max_length=1000)
    parallel_reviews:dict[str,dict]=Field(default_factory=dict,max_length=1000)
    loop_reviews:dict[str,dict]=Field(default_factory=dict,max_length=1000)
    target_document_token:str|None=Field(default=None,pattern='^[0-9a-f]{64}$')
    target_parallel_reviews:dict[str,dict]=Field(default_factory=dict,max_length=1000)
    target_loop_reviews:dict[str,dict]=Field(default_factory=dict,max_length=1000)
    target_environment_id:str=Field(min_length=1,max_length=100)
    expected_target_connection_revision:str|None=Field(default=None,max_length=100)
    node_models_json:dict[str,str]=Field(default_factory=dict,max_length=1000)
    dataset_mapping:dict[str,str]=Field(default_factory=dict,max_length=100)
    node_rerankers:dict[str,Reranker]=Field(default_factory=dict,max_length=1000)
    dependency_mapping:dict[str,str]=Field(default_factory=dict,max_length=100)
    additional_dependencies:list[str]=Field(default_factory=list,max_length=100)
    acknowledge_unverified_target:StrictBool=False
    acknowledge_retained_external_settings:StrictBool=False
    acknowledge_dependency_consolidation:StrictBool=False


def plugin_for(provider):
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+',provider):
        raise ValueError('目标模型供应商须完整声明author/plugin/provider，不猜测插件身份。')
    return '/'.join(provider.split('/')[:2])


def dependency_identifier(value):
    if not identifier(value) or not PLUGIN.fullmatch(value):raise ValueError('目标市场依赖须为明确author/plugin:版本标识，不接受占位名称或控制字符。')
    return value.split(':',1)[0]


def build(task,source,target,payload):
    if task['app_type'] not in {'workflow','advanced-chat'}:raise ValueError('该入口只映射Workflow或Chatflow，不转换原生Agent。')
    if source.get('unresolved') or source.get('validation',{}).get('valid') is not True:raise ValueError('来源仍有未选择冲突或静态阻止项，请先处理；不省略功能后准备目标文件。')
    public=target_public(target)
    if public['id']==task.get('environment_id'):raise ValueError('请明确选择不同的目标环境；同环境调整使用原保留流程。')
    root=parse(source['content'],task['app_type']);observed=inventory(root,digest(root))
    if observed['available'] is not True or observed['blockers']:raise ValueError('来源资源尚不能完整整理，不能生成部分映射；请查看来源资源清单。')
    if payload.acknowledge_unverified_target is not True:raise ValueError('请明确知悉目标资源尚未验证；本次仅生成待验证DSL，不批准导入或运行。')
    retained=[e for e in observed['entries'] if e['category'] in {'http','code_runtime','environment_variable','schedule','human_review'}]
    if retained and payload.acknowledge_retained_external_settings is not True:
        raise ValueError('来源含代码、HTTP、变量或触发/人审设置；请先明确接受保留原值且目标尚未核对，不复制凭据或默认改地址。')
    nodes={n['id']:n for n in root['workflow']['graph']['nodes']}
    model_ids={ident for ident,n in nodes.items() if n['data']['type'] in {'llm','question-classifier','parameter-extractor'}}
    retrieval_nodes={ident:n for ident,n in nodes.items() if n['data']['type']=='knowledge-retrieval'}
    source_ids={v for n in retrieval_nodes.values() for v in n['data']['dataset_ids']}
    reranker_ids={ident for ident,n in retrieval_nodes.items() if n['data']['multiple_retrieval_config'].get('reranking_enable',True) is True}
    if set(payload.node_models_json)!=model_ids:raise ValueError('必须逐节点明确所有LLM/分类/参数提取的完整目标模型；不能漏节点、增加节点或用任务默认统一覆盖。')
    if set(payload.dataset_mapping)!=source_ids or any(not valid_uuid(v) for v in payload.dataset_mapping.values()) or len(set(payload.dataset_mapping.values()))!=len(source_ids):
        raise ValueError('必须逐一明确全部源知识库对应的小写UUID，且保持一一对应，不漏库或合并资料范围。')
    if set(payload.node_rerankers)!=reranker_ids:raise ValueError('必须分别明确所有启用重排节点的目标供应商和型号；不能沿用LLM映射或添加已关闭重排。')
    output=copy.deepcopy(root);out_nodes={n['id']:n for n in output['workflow']['graph']['nodes']};changes=[];plugins=set()
    for ident in sorted(model_ids):
        text=payload.node_models_json[ident]
        try:oversize=len(text.encode('utf-8'))>30000
        except UnicodeError:raise ValueError('目标模型JSON编码无效，不回显输入。') from None
        if oversize:raise ValueError('单个目标模型JSON超过30KB，不截断后处理。')
        chosen=target_model(text);plugins.add(plugin_for(chosen['provider']))
        out_nodes[ident]['data']['model']=copy.deepcopy(chosen)
        changes.append({'kind':'model','node_id':ident,'source':copy.deepcopy(nodes[ident]['data']['model']),'target':chosen})
    for ident,n in retrieval_nodes.items():
        ids=n['data']['dataset_ids'];mapped=[payload.dataset_mapping[v] for v in ids]
        out_nodes[ident]['data']['dataset_ids']=mapped
        changes.append({'kind':'datasets','node_id':ident,'source':list(ids),'target':mapped})
    for ident in sorted(reranker_ids):
        chosen=payload.node_rerankers[ident].model_dump()
        if not all(identifier(v) for v in chosen.values()):raise ValueError('目标重排供应商/型号格式不明确，不填默认值。')
        plugins.add(plugin_for(chosen['provider']))
        original=nodes[ident]['data']['multiple_retrieval_config']['reranking_model']
        out_nodes[ident]['data']['multiple_retrieval_config']['reranking_model']=chosen
        changes.append({'kind':'reranker','node_id':ident,'source':copy.deepcopy(original),'target':chosen})
    dependencies=root.get('dependencies',[]);original_ids=[];target_dependencies=[]
    for dep in dependencies:
        if not isinstance(dep,dict) or set(dep)-{'type','value','current_identifier'} or dep.get('type')!='marketplace' or not isinstance(dep.get('value'),dict) or set(dep['value'])-{'marketplace_plugin_unique_identifier','version'} or dep['value'].get('version') is not None:
            raise ValueError('源固定依赖含未适配字段/版本设置，不删除额外信息后通过。')
        ident=dep['value'].get('marketplace_plugin_unique_identifier');dependency_identifier(ident)
        if ident in original_ids:raise ValueError('源市场依赖重复，请先核对；不静默合并。')
        original_ids.append(ident)
    if set(payload.dependency_mapping)!=set(original_ids):raise ValueError('须逐项声明全部源固定插件的目标对应，不可删掉未使用依赖后假定功能不变。')
    mapped=[payload.dependency_mapping[ident] for ident in original_ids]
    for value in mapped:dependency_identifier(value)
    groups=[{'target_identifier':value,'source_identifiers':[ident for ident in original_ids if payload.dependency_mapping[ident]==value]} for value in dict.fromkeys(mapped) if mapped.count(value)>1]
    if groups and payload.acknowledge_dependency_consolidation is not True:
        raise ValueError('多个源固定依赖对应同一完整目标插件标识；请先明确接受合并目标依赖清单，不会自动去重或假定功能等价。')
    target_ids=list(dict.fromkeys(mapped))+payload.additional_dependencies
    target_plugins=[dependency_identifier(value) for value in target_ids]
    if len(set(target_plugins))!=len(target_plugins):raise ValueError('同一目标插件有重复或冲突的版本标识，请明确唯一版本，不自动去重。')
    if not plugins<=set(target_plugins):raise ValueError('全部目标对话/重排模型须有明确的目标市场插件依赖，不能猜测版本或只保留源插件。')
    for ident in target_ids:
        target_dependencies.append({'type':'marketplace','value':{'marketplace_plugin_unique_identifier':ident,'version':None},'current_identifier':None})
    # All dropped/normalized local identifiers are visible in the complete dependency diff.
    output['dependencies']=target_dependencies
    changes.append({'kind':'dependencies','source':copy.deepcopy(dependencies),'target':target_dependencies})
    if groups:changes.append({'kind':'dependency_consolidation','groups':copy.deepcopy(groups),'acknowledged':True,'note':'仅合并已明确对应同一完整标识的目标声明；没有证明原插件功能已全部等价替代，也未安装或调用目标插件。'})
    description=output['app'].get('description') or ''
    if not isinstance(description,str):raise ValueError('源应用说明不是文字，不转换后附加标记。')
    if not description.splitlines() or description.splitlines()[-1]!=MARKER:description+=('\n\n' if description else '')+MARKER
    if len(description)>10000:raise ValueError('源应用说明过长，无法完整附加待验证标记，不截断原说明。')
    changes.append({'kind':'description','source':root['app'].get('description'),'target':description});output['app']['description']=description
    output_token=digest(output)
    if (payload.target_parallel_reviews or payload.target_loop_reviews) and payload.target_document_token!=output_token:
        raise ValueError('目标文件已变化，目标容器复核摘要不匹配；请重新预览，不能复用来源或旧目标声明。')
    validation=validate_preserved(output,payload.target_parallel_reviews,payload.target_loop_reviews)
    # Source declarations never transfer. A candidate remains blocked until target-specific review.
    parallel=parallel_candidates(output);loops=loop_candidates(output)
    content=yaml.safe_dump(output,allow_unicode=True,sort_keys=False);parse(content,task['app_type'])
    target_context=digest({'environment':public,'connection_revision':target.get('connection_revision')})
    token=digest({'revision':task['revision'],'source_document_token':source['document_token'],'merge_token':source['merge_token'],'reference_id':source['reference_id'],'target_context_token':target_context,'output':output,'target_parallel_reviews':payload.target_parallel_reviews,'target_loop_reviews':payload.target_loop_reviews})
    return {'revision':task['revision'],'reference_id':source['reference_id'],'source_document_token':source['document_token'],'source_environment_id':task.get('environment_id'),
            'target_environment':public,'target_context_token':target_context,'preview_token':token,'document_token':output_token,'content':content,'changes':changes,
            'target_parallel_candidates':parallel,'target_loop_candidates':loops,'can_download':validation['valid'],
            'dependency_consolidation':groups,
            'retained_conditions':retained,'validation':validation,'verification':'static_workflow_mapping_preview','task_modified':False,'can_apply':False,
            'platform_verified':False,'business_verified':False,'target_resources_verified':False,
            'warnings':['目标资料等价、索引、模型规则、插件安装及费用未验证；每个节点的检索参数、提示词、代码、连线和容器均保留。',
                        'HTTP、环境变量、代码与平台设置保持原文件值；秘密变量仅允许空值，实际凭据须在目标独立配置。',
                        '当前仅返回可下载草稿，不保存任务/进度、不发布/导入/运行、不沿用来源批准或运行绑定。'],
            'note':'来源是当前本机合并预览，不声明源应用此刻最新；目标版本来自本机声明，资源及业务仍须实际验收。'}


class WorkflowEnvironmentMapping:
    def __init__(self,h):self.h=h

    def prepare(self,task,payload,*,require_idle=True):
        h=self.h
        if require_idle:h.require_idle(task)
        h.require_revision(task,payload.revision)
        if task['app_type'] not in {'workflow','advanced-chat'}:raise HTTPException(422,'请使用原生Agent对应入口，不转换应用类型。')
        source=h.dsl_preview(task,payload.choices,payload.parallel_reviews,payload.loop_reviews)
        if any(source[k]!=getattr(payload,k) for k in ('reference_id','merge_token','document_token')):raise HTTPException(409,'来源合并预览已变化，请重新核对逐节点资源映射。')
        target=h.store.get('environment',payload.target_environment_id)
        if not target:raise HTTPException(404,'目标环境不存在，请先配置独立连接。')
        if target.get('id')!=payload.target_environment_id or target.get('version')!=h.TARGET_DIFY_VERSION:raise HTTPException(422,'目标环境身份或声明版本不符合当前适配基线。')
        if target.get('connection_revision')!=payload.expected_target_connection_revision:raise HTTPException(409,'目标连接已变化，请刷新后重新核对映射。')
        try:return build(task,source,target,payload)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        except (KeyError,TypeError,AttributeError,OverflowError):raise HTTPException(422,'资源映射结构无法完整核对，原文件和任务保持；不回显输入。') from None


    def register(self):
        h=self.h;router=APIRouter(route_class=WorkflowMappingRoute)
        @router.post('/api/tasks/{item_id}/workflow-environment-mapping/preview')
        def preview(item_id:str,payload:WorkflowMappingRequest):
            with h.store.lock:return self.prepare(h.get_task(item_id),payload)
        h.app.include_router(router)
