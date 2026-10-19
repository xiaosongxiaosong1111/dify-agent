"""Observed structural resource uses in a merged workflow; no target lookups/writes."""
import uuid,re

PURE={'start','end','answer','code','template-transform','if-else','variable-aggregator','list-operator',
      'assigner','document-extractor','iteration','iteration-start','loop','loop-start','loop-end'}
MODELS={'llm','question-classifier','parameter-extractor'}
KNOWN=PURE|MODELS|{'knowledge-retrieval','http-request','trigger-schedule','human-input'}


def identifier(value):
    return isinstance(value,str) and 0<len(value)<=256 and value==value.strip() and all(ord(c)>=32 for c in value)


def inventory(root,document_token):
    """Never returns prompts, code, URLs, parameters, variable values or credentials."""
    try:
        mode=root['app']['mode']
        if mode not in {'workflow','advanced-chat'}:raise ValueError('该清单只适配Workflow与Chatflow，不转换应用类型。')
        workflow=root['workflow'];nodes=workflow['graph']['nodes']
        if not isinstance(nodes,list) or len(nodes)>1000:raise ValueError('来源节点结构或数量超出清单范围，不把部分清单当完整结果。')
        entries=[];blockers=[];seen=set()
        def add(category,label,location,identifiers,requirement,impact):
            entries.append(dict(category=category,label=label,location=location,identifiers=identifiers,requirement=requirement,impact=impact))
        def model_use(value,location,category='chat_model'):
            if not isinstance(value,dict) or not identifier(value.get('provider')) or not identifier(value.get('name' if category=='chat_model' else 'model')):
                blockers.append(location+'：模型标识不完整，不推测目标对应关系。');return
            if category=='chat_model' and value.get('mode')!='chat':blockers.append(location+'：不是已适配的chat模型模式，不转换后通过。')
            add(category,'对话模型' if category=='chat_model' else '重排模型',location,[value['provider'],value['name' if category=='chat_model' else 'model']],
                '逐节点明确目标供应商、型号和完整参数；不把任务默认型号覆盖所有独立模型。' if category=='chat_model' else '单独核对目标重排供应商和型号，不能沿用LLM对应关系。',
                '型号、参数、费用、延迟和输出格式可能变化，需重新验证。' if category=='chat_model' else '重排影响检索次序、延迟及额外模型费用；静态标识不证明可调用。')
        for node in nodes:
            if not isinstance(node,dict) or not identifier(node.get('id')) or node['id'] in seen:raise ValueError('来源节点ID重复或不明确，不能可靠定位资源。')
            seen.add(node['id']);data=node.get('data')
            if not isinstance(data,dict) or not identifier(data.get('type')):raise ValueError('来源节点类型不明确，不能跳过后报告完整。')
            kind=data['type'];location='节点 '+node['id']
            if node.get('parentId') is not None:
                if not identifier(node['parentId']):raise ValueError('节点容器标识不明确，不能猜测资源所属范围。')
                location+='（容器 '+node['parentId']+'）'
            if kind not in KNOWN:blockers.append(location+'：包含尚未适配的节点类型，不能据此清单执行迁移。')
            if kind in MODELS:model_use(data.get('model'),location)
            if kind=='knowledge-retrieval':
                ids=data.get('dataset_ids')
                if not isinstance(ids,list) or not ids or len(ids)>100 or len(set(i for i in ids if isinstance(i,str)))!=len(ids) or any(not identifier(i) for i in ids):
                    blockers.append(location+'：知识库ID缺失、重复或超限，不删除或猜测。')
                else:
                    add('datasets','知识库',location,list(ids),'逐个明确目标ID，保留每个节点的库组合、检索策略和无命中行为。','同名或ID相同不证明资料等价；需核对索引、Embedding、权限、覆盖、检索费用与代表性问题。')
                    if any(not valid_uuid(i) for i in ids):blockers.append(location+'：来源库ID不是明确的小写UUID，正式对应前须核对实际ID。')
                if data.get('retrieval_mode')!='multiple' or data.get('single_retrieval_config') is not None:
                    blockers.append(location+'：单库模型路由/备用配置未适配，不能省略其资源。')
                multi=data.get('multiple_retrieval_config')
                if not isinstance(multi,dict):blockers.append(location+'：缺少明确的多库检索配置。')
                else:
                    if multi.get('reranking_mode','reranking_model')!='reranking_model' or multi.get('weights') is not None:
                        blockers.append(location+'：含权重或未知重排配置，其额外Embedding等资源尚不能完整整理。')
                    if multi.get('reranking_enable',True) is True:model_use(multi.get('reranking_model'),location,'reranking_model')
                    elif multi.get('reranking_enable') is not False or multi.get('reranking_model') is not None:
                        blockers.append(location+'：重排开关与模型配置不一致，不能忽略备用资源。')
                if data.get('metadata_model_config') is not None or data.get('metadata_filtering_mode') not in (None,'disabled'):
                    blockers.append(location+'：元数据模型/过滤额外资源未适配，不能将其当作无依赖。')
            elif kind=='http-request':
                add('http','外部HTTP接口',location,[],'人工核对目标地址、可达性、认证变量、接口合同和副作用；清单不显示URL或请求内容。','可能访问原环境服务、产生写操作或费用；不调用接口，不推断只读，不自动替换地址。')
            elif kind=='code':
                add('code_runtime','代码执行环境',location,[],'核对目标沙箱、语言、依赖和代码中的外部访问；清单不执行或分析代码正文。','相同代码不保证目标环境可运行；网络、依赖、资源限制与外部副作用需人工复核。')
            elif kind in {'human-input','trigger-schedule'}:
                add('human_review' if kind=='human-input' else 'schedule','人工审核' if kind=='human-input' else '定时触发',location,[],
                    '目标环境须重新核对参与人、通知、发布与启停状态；原执行绑定不会迁移。','涉及人工投入、自动触发及重复副作用风险；准备草稿不批准发布或启用。')
        variables=workflow.get('environment_variables',[])
        if not isinstance(variables,list) or len(variables)>100:raise ValueError('环境变量结构或数量超限，不能忽略后继续整理。')
        names=set()
        for variable in variables:
            if not isinstance(variable,dict) or not identifier(variable.get('name')) or variable['name'] in names:raise ValueError('环境变量名称重复或不明确。')
            name=variable['name'];names.add(name)
            if variable.get('value_type') not in {'string','number','secret'}:blockers.append('环境变量 '+name+'：类型尚未适配，不猜测默认值。')
            if variable.get('value_type')=='secret' and variable.get('value')!='':raise ValueError('秘密变量非空，不能进入资源清单。')
            from .dsl import _contains_secret_key
            if variable.get('value_type')!='secret' and _contains_secret_key({name:variable.get('value')}):
                blockers.append('环境变量 '+name+'：疑似凭据名称却未声明为空秘密变量，不能复制其值到目标草稿。')
            add('environment_variable','秘密变量' if variable.get('value_type')=='secret' else '环境变量','应用环境',[name],
                '只列变量名，须在目标独立配置与核对用途；不读取或复制值。','错误沿用可能访问原系统；秘密值由用户在目标配置，不能放入DSL、日志或清单。')
        dependencies=root.get('dependencies',[])
        if not isinstance(dependencies,list) or len(dependencies)>100:raise ValueError('插件依赖结构或数量未适配，不能忽略。')
        for dependency in dependencies:
            value=dependency.get('value') if isinstance(dependency,dict) else None
            ident=value.get('marketplace_plugin_unique_identifier') if isinstance(value,dict) else None
            if dependency.get('type')!='marketplace' or not identifier(ident) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+:[^\s:]+',ident):
                blockers.append('应用包含未适配或不明确的插件依赖，不能猜测来源或安装版本。');continue
            add('plugin_dependency','固定市场插件依赖','应用插件',[ident],'核对目标安装的确切插件、版本和供应商配置；不能按模型名推测已安装。','安装与版本变化可能改变行为、兼容性和费用；本清单不安装或升级插件。')
        if len(entries)>3000:raise ValueError('资源项超出清单上限，不截断后当完整结果。')
        return {'available':True,'mode':mode,'document_token':document_token,'nodes_scanned':len(nodes),'entries':entries,'blockers':blockers,
                'warnings':['这是当前合并文件中已识别的结构化资源，不是对代码、提示词或外部副作用的语义审计。',
                            '未查询任何目标环境，未改写、导入或运行；没有资源项也不证明目标无需配置。',
                            '对话状态、文件入口、目标平台设置和业务覆盖仍须单独核对；原任务确认、凭据与运行绑定不会迁移。'],
                'note':'逐节点位置包含容器归属，同一模型或知识库的多处使用不会合并后漏掉；此清单不是目标映射成果或迁移批准。',
                'verification':'source_resource_inventory_only','target_resources_verified':False,'platform_verified':False,'business_verified':False,'task_modified':False}
    except (KeyError,TypeError,AttributeError,ValueError) as exc:
        return {'available':False,'reason':str(exc) if isinstance(exc,ValueError) else '来源资源结构无法完整整理，原文件保持；不返回部分清单冒充完整结果。'}


def valid_uuid(value):
    try:return str(uuid.UUID(value))==value
    except (ValueError,AttributeError,TypeError):return False
