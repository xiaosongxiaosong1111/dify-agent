"""Native Dify 1.17.1 Agent packages; no Workflow/Chatflow substitution."""
import re
import yaml
from .dsl import DSL_VERSION, REQUIREMENT_KEYS, MOCK_DEPENDENCY_WARNING, mock_dependency_notice
from .model_parameters import completion_parameters

AGENT_RUNTIME_NOTE = '原生 Agent 的内建配置 CLI／沙箱由 Dify 部署提供；空自定义工具列表不代表运行时没有内建工具。当前不配置自定义工具、文件、Skills 或人工介入；知识集检索由 Agent 按指令调用，不能保证每轮必检索。'


def validate_agent_plan(task, plan):
    errors = []
    if task.get('app_type') != 'agent':
        errors.append('Agent Plan 只能用于用户选择的原生 Agent 应用。')
    if not isinstance(plan, dict):
        return {'valid': False, 'errors': ['Agent Plan 必须为对象。'], 'warnings': [], 'nodes': 0}
    fields = {'schema_version', 'scope', 'system_prompt'}
    if plan.get('scope') == 'knowledge': fields.add('knowledge_sets')
    if set(plan) != fields:
        errors.append('Agent Plan 字段与所选范围不符；未支持的功能不能静默忽略。')
    if type(plan.get('schema_version')) is not int or plan.get('schema_version') != 1:
        errors.append('Agent Plan schema_version 必须为整数 1。')
    if plan.get('scope') not in {'text', 'knowledge'}:
        errors.append('当前原生 Agent 只支持 text 或 knowledge 范围；自定义工具、文件、Skills 与人工介入尚待适配。')
    prompt = plan.get('system_prompt')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        errors.append('Agent 系统指令须为非空且最多 20000 字的文本。')
    elif re.search(r'\[§|\{\{#', prompt):
        errors.append('当前 Agent Plan 不支持资源提及或 Workflow 变量引用，请明确纯文本指令。')
    cfg = task.get('configuration') or {}
    selected = cfg.get('dataset_ids', [])
    if plan.get('scope') == 'text' and selected:
        errors.append('文本范围不能丢弃已选择的知识库；请明确知识集方案，或先协商后调整资源范围。')
    if plan.get('scope') == 'knowledge':
        sets = plan.get('knowledge_sets')
        if not isinstance(sets, list) or not 1 <= len(sets) <= 5:
            errors.append('knowledge_sets 须为 1—5 个知识集。')
        else:
            ids, names = set(), set()
            for index, item in enumerate(sets, 1):
                label = f'知识集 {index}'
                if not isinstance(item, dict) or set(item) != {'name', 'description', 'dataset_ids', 'query_mode', 'top_k'}:
                    errors.append(label + ' 仅允许 name,description,dataset_ids,query_mode,top_k。'); continue
                name = item.get('name')
                if not isinstance(name, str) or not name.strip() or len(name) > 100 or name.strip().casefold() in names:
                    errors.append(label + ' 名称须非空、唯一且最多 100 字。')
                else: names.add(name.strip().casefold())
                if not isinstance(item.get('description'), str) or not item['description'].strip() or len(item['description']) > 2000:
                    errors.append(label + ' 用途说明须非空且最多 2000 字。')
                datasets = item.get('dataset_ids')
                if not isinstance(datasets, list) or not 1 <= len(datasets) <= 20 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', v) for v in datasets) or len(set(datasets)) != len(datasets):
                    errors.append(label + ' 知识库 ID 须明确、非空、唯一。')
                else: ids.update(datasets)
                if item.get('query_mode') != 'generated_query':
                    errors.append(label + ' 当前仅支持 generated_query；Agent 自主生成检索词，不能冒充固定查询或每轮强制检索。')
                if type(item.get('top_k')) is not int or not 1 <= item['top_k'] <= 20:
                    errors.append(label + ' top_k 须为 1—20 的整数。')
            if not isinstance(selected, list) or any(not isinstance(v, str) for v in selected) or set(selected) != ids or not ids:
                errors.append('知识集使用的 ID 必须与已选择知识库一致；不能漏用资源或加入未确认的库。')
    if cfg.get('conversation_memory'):
        errors.append('Chatflow 历史窗口不能套用到原生 Agent。原生会话记忆由 Dify Agent 管理，当前不支持配置该窗口。')
    return {'valid': not errors, 'errors': errors, 'warnings': [AGENT_RUNTIME_NOTE], 'nodes': 0, 'verification': 'static_only', 'plan_type': 'agent'}


def compile_agent_plan(task):
    plan = task.get('agent_plan')
    result = validate_agent_plan(task, plan)
    if not result['valid']:
        raise ValueError('Agent 配置检查失败：' + '; '.join(result['errors']))
    cfg = task['configuration']
    provider, model = cfg.get('dify_model_provider'), cfg.get('dify_model')
    if not isinstance(provider, str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', provider):
        raise ValueError('原生 Agent 需要实际插件模型标识 author/plugin/provider，不能猜测插件 ID。')
    if not isinstance(model, str) or not model.strip():
        raise ValueError('请明确原生 Agent 使用的实际模型。')
    params = completion_parameters(cfg)
    fmt = params.get('response_format')
    if fmt is not None:
        if fmt not in {'text', 'json_object'}:
            raise ValueError('当前 Agent 只支持明确的 text 或 json_object 输出格式；不能删除不支持的格式。')
        params['response_format'] = {'type': fmt}
    req = task.get('requirements') or {}
    if any(not isinstance(req.get(k), str) or not req[k].strip() for k in REQUIREMENT_KEYS):
        raise ValueError('原生 Agent 构建前须明确八项需求。')
    name = task.get('name', '')
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        raise ValueError('原生 Agent 名称须为非空且最多 255 字。')
    package = {'schema_version': 1, 'metadata': {'name': name, 'description': req['goal'], 'role': ''},
               'soul': {'schema_version': 1, 'prompt': {'system_prompt': plan['system_prompt']},
                        'tools': {'dify_tools': [], 'cli_tools': []}, 'knowledge': {'sets': []},
                        'model': {'plugin_id': '/'.join(provider.split('/')[:2]), 'model_provider': provider,
                                  'model': model, 'credential_ref': None, 'model_settings': params},
                        'app_features': {'opening_statement': cfg.get('opening_statement', ''),
                                         'suggested_questions': cfg.get('suggested_questions', []),
                                         'file_upload': {'enabled': False}}},
               'omitted_assets': [], 'workspace_skills': []}
    if plan['scope'] == 'knowledge':
        package['soul']['knowledge']['sets'] = [
            {'id': f'knowledge_{i}', 'name': item['name'].strip(), 'description': item['description'],
             'datasets': [{'id': value} for value in item['dataset_ids']],
             'query': {'mode': 'generated_query', 'value': None},
             'retrieval': {'mode': 'multiple', 'top_k': item['top_k'], 'score_threshold': None,
                           'reranking_enable': False, 'reranking_mode': 'reranking_model'},
             'metadata_filtering': {'mode': 'disabled'}} for i, item in enumerate(plan['knowledge_sets'], 1)]
    root = {'app': {'name': name, 'description': req['goal'], 'mode': 'agent', 'icon': '🤖',
                    'icon_background': '#EFF6FF', 'icon_type': 'emoji', 'use_icon_as_answer_icon': False},
            'dependencies': [], 'kind': 'app', 'version': DSL_VERSION,
            'agent': {'package_ref': 'agent_1'}, 'agent_packages': {'agent_1': package}}
    mock_note = mock_dependency_notice(cfg)
    if mock_note:
        root['app']['description'] += '\n' + mock_note
        package['metadata']['description'] += '\n' + mock_note
        result['warnings'].append(MOCK_DEPENDENCY_WARNING)
    return yaml.safe_dump(root, allow_unicode=True, sort_keys=False), result
