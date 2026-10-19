"""Explicit per-node retrieval choices for the bounded multiple-query adapter."""
import math

FIELDS = {'query_variable_selector','dataset_ids','dataset_source','top_k','score_threshold','reranking_enable','reranking_model'}


def dataset_ids(config, configuration):
    source=config.get('dataset_source')
    if source=='node':return config.get('dataset_ids')
    if source=='task':return configuration.get('dataset_ids',[])
    return config.get('dataset_ids') or configuration.get('dataset_ids',[])


def validate(config, configuration):
    errors=[]
    if set(config)-FIELDS:errors.append('知识检索配置包含未适配字段；单库模型路由、权重重排、元数据过滤和附件尚未适配，不能忽略后通过。')
    source=config.get('dataset_source')
    if 'dataset_source' in config and source not in ('node','task'):errors.append('dataset_source 须明确为 node／task。')
    if source=='task' and 'dataset_ids' in config:errors.append('继承任务知识库不能携带未生效的节点 dataset_ids，请明确移除。')
    ids=dataset_ids(config,configuration)
    if not isinstance(ids,list) or not ids or any(not isinstance(v,str) or not v.strip() for v in ids):errors.append('必须明确选择非空知识库 ID；独立选择为空时不会回退到任务默认库。')
    elif len(ids)!=len(set(ids)):errors.append('知识库 ID 不能重复。')
    threshold=config.get('score_threshold')
    if threshold is not None and (type(threshold) not in (int,float) or not math.isfinite(threshold) or not 0<=threshold<=1):errors.append('score_threshold 须为 null（关闭）或 0—1 的有限数值。')
    enabled=config.get('reranking_enable',False)
    if type(enabled) is not bool:errors.append('reranking_enable 须为明确布尔值。')
    model=config.get('reranking_model')
    if enabled is True:
        if not isinstance(model,dict) or set(model)!={'provider','model'} or any(not isinstance(model[k],str) or not model[k] or model[k]!=model[k].strip() or len(model[k])>256 or any(ord(c)<32 for c in model[k]) for k in ('provider','model')):
            errors.append('启用模型重排须完整指定 reranking_model 的 provider／model；不能猜测、携带凭据或继承 LLM 型号。')
    elif model is not None:errors.append('关闭重排时不能携带未生效的 reranking_model；请明确移除，不静默忽略。')
    warnings=['知识库权限、索引状态和跨库索引／Embedding 兼容性仍需实际核对；不同索引策略的多库查询可能需要模型重排，不能由静态图推断可用。']
    if threshold is not None:warnings.append('已配置分数阈值，可能过滤全部结果；不同库／模型分数不可直接类比，需确认无命中行为并纳入试跑。')
    if enabled is True:warnings.append('模型重排会增加延迟、供应商依赖和可能的费用，未计入 Sierra 助手预算；目录声明可用不等于真实重排验证。')
    return errors,warnings


def native(config,configuration):
    result={'top_k':config.get('top_k',configuration.get('retrieval_top_k',3)),
            'score_threshold':config.get('score_threshold'), 'reranking_enable':config.get('reranking_enable',False)}
    if result['reranking_enable']:
        result.update(reranking_mode='reranking_model',reranking_model=dict(config['reranking_model']))
    return result


def validate_query_source(selector,nodes,mode,scope_types=None):
    """Check known declarations only; never coerce data into a query."""
    if not isinstance(selector,list) or len(selector)!=2 or not all(isinstance(v,str) for v in selector):return [],[]
    from .iteration import output_type
    source,field=selector;node=nodes.get(source,{})
    actual='string' if selector==['sys','query'] and mode=='advanced-chat' else output_type(nodes,selector)
    if node.get('type')=='knowledge-retrieval' and field=='result':actual='array[object]'
    elif node.get('type')=='http-request':actual={'body':'string','status_code':'number','files':'array[file]'}.get(field)
    elif node.get('type')=='llm':actual={'text':'string','usage':'object','finish_reason':'string','files':'array[file]','structured_output':'object'}.get(field)
    if scope_types and tuple(selector) in scope_types:
        actual=scope_types[tuple(selector)]
    if isinstance(actual,str) and actual!='string':
        return ['知识检索的问题来源已声明为非文字类型；Dify 需要 string。请明确如何提取或转换为问题文字，不会自动字符串化、改选变量或删除检索。'],[]
    if not isinstance(actual,str) and scope_types is not None:return ['容器知识检索须明确文字问题来源类型，不能按虚拟输入默认文字或未知声明通过。'],[]
    if not isinstance(actual,str):return [],['知识检索问题来源的文字类型无法静态确定；须核对实际上游输出，不能按引用存在就算验证可用。']
    return [],[]


def preserved(data):
    if data.get('retrieval_mode')!='multiple':raise ValueError('保留知识检索目前只支持明确的 multiple；single 模型路由不能移除后算通过。')
    if data.get('single_retrieval_config') is not None:raise ValueError('保留知识检索尚未适配 single 备用配置，请先明确范围，不会偷偷移除。')
    if data.get('query_attachment_selector'):raise ValueError('保留知识检索暂不支持附件。')
    selector=data.get('query_variable_selector')
    if not isinstance(selector,list) or len(selector)!=2 or any(not isinstance(v,str) or not v for v in selector):
        raise ValueError('原生知识检索缺少明确的两段问题来源；空来源可使节点不检索，不能把它当作计划继承默认输入。请核对实际 DSL，不会自动补来源。')
    if (data.get('vision') or {}).get('enabled'):raise ValueError('保留知识检索暂不支持视觉输入。')
    if data.get('metadata_filtering_mode') not in (None,'disabled') or data.get('metadata_model_config') is not None or data.get('metadata_filtering_conditions') is not None:
        raise ValueError('保留知识检索尚未适配元数据过滤／模型条件，不会忽略后通过。')
    multi=data.get('multiple_retrieval_config')
    if not isinstance(multi,dict):raise ValueError('保留知识检索须有实际 multiple_retrieval_config。')
    if multi.get('reranking_mode','reranking_model')!='reranking_model' or multi.get('weights') is not None:
        raise ValueError('保留知识检索暂不支持权重重排或未知策略，不能改成模型重排后通过。')
    return {'query_variable_selector':data.get('query_variable_selector'),'dataset_source':'node','dataset_ids':data.get('dataset_ids'),
            'top_k':multi.get('top_k'),'score_threshold':multi.get('score_threshold'),
            'reranking_enable':multi.get('reranking_enable',True), 'reranking_model':multi.get('reranking_model')}
