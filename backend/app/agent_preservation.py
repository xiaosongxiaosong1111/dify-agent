"""Bounded native text/knowledge Agent preservation, pinned to Dify 1.17.1 DTOs.

No projection to Workflow, no deletion of unsupported capabilities. Returned
validation is local only; model identity/settings must match the proposal.
"""
import copy
import re
from .agent_plan import AGENT_RUNTIME_NOTE, validate_agent_plan
from .dsl import DSL_VERSION
from .dsl_roundtrip import digest

FILE_DEFAULTS = {'enabled': True, 'allowed_file_extensions': ['JPG','JPEG','PNG','GIF','WEBP','SVG'],
    'allowed_file_types': ['document','image','audio','video'],
    'allowed_file_upload_methods': ['local_file','remote_url'], 'image': {'enabled': True}, 'number_limits': 3}
FEATURE_DEFAULTS = {'opening_statement': None, 'suggested_questions': None,
    'suggested_questions_after_answer': None, 'speech_to_text': None,
    'text_to_speech': None, 'retriever_resource': None,
    'sensitive_word_avoidance': None, 'file_upload': FILE_DEFAULTS}
SOUL_DEFAULTS = {'human': {'contacts': [], 'tools': []}, 'env': {'variables': [], 'secret_refs': []},
    'config_skills': [], 'config_files': [], 'config_note': '',
    'sandbox': {'provider': None, 'config': {'image': None, 'working_dir': None, 'env': [], 'cpu': None}},
    'memory': {'scope': None, 'budget': None, 'artifacts': []}, 'app_variables': [],
    'misc_legacy': FEATURE_DEFAULTS}
MODEL_DEFAULTS = {'temperature','top_p','presence_penalty','frequency_penalty','max_tokens','stop','response_format'}


def subset_defaults(value, defaults):
    # Exact typed values: False/0, []/{}, and missing/None are not interchangeable.
    if isinstance(defaults, dict):
        return isinstance(value, dict) and not set(value)-set(defaults) and all(subset_defaults(v, defaults[k]) for k,v in value.items())
    return digest(value) == digest(defaults)


def fields(value, allowed, label, required=()):
    if not isinstance(value, dict) or set(value)-set(allowed) or not set(required)<=set(value):
        raise ValueError(label + '含未知字段或缺少必需字段，不能删除后声称保留。')
    return value


def text(value, label, limit, nonempty=False):
    if not isinstance(value,str) or len(value)>limit or nonempty and not value.strip():
        raise ValueError(label + '须为长度范围内的明确文本。')


def model_identity(model):
    fields(model, {'plugin_id','model_provider','model','credential_ref','model_settings'}, 'Agent 模型', ('plugin_id','model_provider','model','model_settings'))
    if model.get('credential_ref') is not None:raise ValueError('Agent 保留不接受模型凭据引用，请重新无密钥导出并确认模型配置。')
    provider=model['model_provider']
    if not isinstance(provider,str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+',provider) or model['plugin_id']!='/'.join(provider.split('/')[:2]):
        raise ValueError('Agent 模型插件与供应商标识不一致。')
    text(model['model'],'Agent 模型名称',255,True)
    params=model['model_settings']
    if not isinstance(params,dict):raise ValueError('Agent 模型参数须为对象。')
    normalized=copy.deepcopy(model)
    normalized['model_settings']={k:v for k,v in params.items() if v is not None or k not in MODEL_DEFAULTS}
    normalized['credential_ref']=None
    return normalized


def validate(root, proposal, parallel_reviews=None, loop_reviews=None):
    try:
        if parallel_reviews or loop_reviews:raise ValueError('原生 Agent 不接受 Workflow 并行或循环声明。')
        fields(root, {'app','kind','version','dependencies','agent','agent_packages'}, '原生 Agent 文件', ('app','kind','version','agent','agent_packages'))
        if root['kind']!='app' or root['version']!=DSL_VERSION:raise ValueError('原生 Agent 文件类型或版本不匹配。')
        app=fields(root['app'], {'name','description','mode','icon','icon_type','icon_background','use_icon_as_answer_icon'}, 'Agent 应用', ('mode','name'))
        if app['mode']!='agent':raise ValueError('原生 Agent 不转换为其他应用类型。')
        text(app['name'],'Agent 应用名称',255,True)
        for key in ('description','icon','icon_type','icon_background'):
            if key in app and app[key] is not None:text(app[key],'Agent 应用显示信息',10000)
        if 'use_icon_as_answer_icon' in app and type(app['use_icon_as_answer_icon']) is not bool:raise ValueError('Agent 图标开关须为布尔值。')
        binding=fields(root['agent'], {'package_ref'}, 'Agent 包引用', ('package_ref',))
        ref=binding['package_ref'];packages=root['agent_packages']
        if not isinstance(ref,str) or not isinstance(packages,dict) or len(packages)!=1 or ref not in packages:
            raise ValueError('首批 Agent 保留只支持一个完整且明确引用的文本包；不删除其他包后通过。')
        pkg=fields(packages[ref], {'schema_version','metadata','soul','omitted_assets','workspace_skills'}, 'Agent 配置包', ('schema_version','metadata','soul'))
        if type(pkg['schema_version']) is not int or pkg['schema_version']!=1:raise ValueError('Agent 包 schema_version 须为整数 1。')
        for key in ('omitted_assets','workspace_skills'):
            if key in pkg and digest(pkg[key])!=digest([]):raise ValueError('Agent 含文件或 Skills 绑定／缺失资产，暂不合并且不会删除资产提示。')
        meta=fields(pkg['metadata'], {'name','description','role','icon_type','icon','icon_background'}, 'Agent 包显示信息', ('name',))
        text(meta['name'],'Agent 包名称',255,True)
        for key in set(meta)-{'name'}:
            if meta[key] is not None:text(meta[key],'Agent 包显示信息',10000)
        soul=fields(pkg['soul'], {'schema_version','prompt','tools','knowledge','model','app_features',*SOUL_DEFAULTS}, 'Agent soul', ('schema_version','prompt','tools','knowledge','model','app_features'))
        if type(soul['schema_version']) is not int or soul['schema_version']!=1:raise ValueError('Agent soul schema_version 须为整数 1。')
        for key,defaults in SOUL_DEFAULTS.items():
            if key in soul and not subset_defaults(soul[key],defaults):raise ValueError('Agent 的 '+key+' 含未适配行为；本次只保留默认空配置，不省略后通过。')
        if not subset_defaults(soul['tools'], {'dify_tools':[],'cli_tools':[]}):raise ValueError('Agent 自定义工具暂不保留合并，不会删除工具后通过。')
        prompt=fields(soul['prompt'], {'system_prompt'}, 'Agent 系统指令', ('system_prompt',))
        checked=validate_agent_plan({'app_type':'agent','configuration':{}}, {'schema_version':1,'scope':'text','system_prompt':prompt['system_prompt']})
        if not checked['valid']:raise ValueError('；'.join(checked['errors']))
        selected=proposal['agent_packages'][proposal['agent']['package_ref']]['soul']
        from .agent_knowledge_preservation import project as project_knowledge
        knowledge_rows=project_knowledge(soul['knowledge'],selected.get('knowledge',{}),prompt['system_prompt'])
        if digest(model_identity(soul['model']))!=digest(model_identity(selected['model'])):
            raise ValueError('Agent 保留文件的模型或参数与本次已选配置不同；请先明确调整模型配置再重新分析，不能用旧配置确认其他模型。')
        features=fields(soul['app_features'], FEATURE_DEFAULTS, 'Agent 应用功能', ('file_upload',))
        for key,value in features.items():
            if key=='opening_statement' and value is not None:text(value,'Agent 开场白',20000)
            elif key=='suggested_questions' and value is not None:
                if not isinstance(value,list) or len(value)>10:raise ValueError('Agent 建议问题须为最多 10 项的文本列表。')
                for question in value:text(question,'Agent 建议问题',1000,True)
            elif key=='file_upload':
                defaults={**FILE_DEFAULTS,'enabled':False}
                if not isinstance(value,dict) or value.get('enabled') is not False or not subset_defaults(value,defaults):raise ValueError('Agent 文件功能或文件配置暂不保留合并，请保留完整文件。')
            elif value is not None:raise ValueError('Agent 额外应用功能暂不保留合并，不会移除后通过。')
        deps=root.get('dependencies',[])
        if not isinstance(deps,list) or len(deps)>1:raise ValueError('文本 Agent 只保留一个所选模型的市场依赖声明。')
        for dep in deps:
            fields(dep, {'type','value','current_identifier'}, 'Agent 插件依赖', ('type','value'))
            value=fields(dep['value'], {'marketplace_plugin_unique_identifier','version'}, 'Agent 市场依赖', ('marketplace_plugin_unique_identifier',))
            ident=value['marketplace_plugin_unique_identifier']
            plugin=soul['model']['plugin_id']
            if dep['type']!='marketplace' or not isinstance(ident,str) or not ident.startswith(plugin+':') or len(ident)>1024 or any(c.isspace() or ord(c)<32 for c in ident):raise ValueError('Agent 插件依赖须明确属于当前模型；GitHub／包安装及其他插件尚未适配。')
            for val in (dep.get('current_identifier'),value.get('version')):
                if val is not None:text(val,'Agent 依赖版本',1024)
        return {'valid':True,'errors':[],'warnings':[AGENT_RUNTIME_NOTE,
            '仅静态保留单个文本或已选知识集 Agent 包的指令、显示信息、开场白和建议问题；知识集名称／说明／top_k与明确分组按最终文件保留，库ID并集须与本次选择一致。模型与本次生成配置一致，依赖可用性、部署内建工具和实际业务未验证。'],
            'nodes':0,'verification':'static_only','plan_type':'agent'}
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        return {'valid':False,'errors':[str(exc) if isinstance(exc,ValueError) else 'Agent 包结构不完整，不能按 Workflow 或缺省空包处理。'], 'warnings':[], 'nodes':0,'verification':'static_only','plan_type':'agent'}
