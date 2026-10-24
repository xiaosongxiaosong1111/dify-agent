"""User-declared simulated dependency locations and real-service handoff todos."""


def validate_bindings(bindings):
    if not isinstance(bindings, list) or len(bindings) > 50:
        raise ValueError('模拟依赖接入待办须为最多50项的列表。')
    seen = set()
    for index, item in enumerate(bindings, 1):
        if not isinstance(item, dict) or set(item) != {'dependency', 'node_id', 'replacement_todo'}:
            raise ValueError(f'模拟依赖接入待办第{index}项须包含依赖、节点ID与接入待办。')
        for key, limit in [('dependency', 2000), ('node_id', 128), ('replacement_todo', 4000)]:
            if not isinstance(item[key], str) or not item[key].strip() or len(item[key]) > limit:
                raise ValueError(f'模拟依赖接入待办第{index}项的{key}须为非空且最多{limit}字的文本。')
        if item['dependency'] in seen:
            raise ValueError('每项模拟依赖只允许一个明确位置；多个位置须先拆分依赖声明。')
        seen.add(item['dependency'])


def handoff_note(bindings):
    return '\n模拟依赖接入待办（人工声明，仅核对节点存在；未验证模拟实现或真实接入）：\n' + '\n'.join(
        f"- {item['dependency']}；位置：{item['node_id']}；接入待办：{item['replacement_todo']}" for item in bindings)


def apply_to_export(task, dsl, validation):
    cfg = task.get('configuration') or {}
    bindings = cfg.get('mock_dependency_bindings', [])
    try:
        validate_bindings(bindings)
    except ValueError as exc:
        validation['errors'].append(str(exc)); validation['valid'] = False
        return
    declarations = cfg.get('mock_dependencies', [])
    if not isinstance(declarations, list):
        declarations = [str(declarations)]
    declarations = [str(value) for value in declarations if str(value).strip()]
    if task.get('app_type') == 'agent':
        nodes = {'agent.system_prompt'}
    else:
        nodes = {node['id'] for node in dsl['workflow']['graph']['nodes']}
    for index, item in enumerate(bindings, 1):
        if item['dependency'] not in declarations:
            validation['errors'].append(f'模拟依赖接入待办第{index}项不再对应当前声明；请明确移除旧待办或恢复原声明。')
        if item['node_id'] not in nodes:
            validation['errors'].append(f'模拟依赖接入待办第{index}项的节点在当前成果中不存在；请重新选择位置。')
    if validation['errors']:
        validation['valid'] = False
        return
    if any(value not in {item['dependency'] for item in bindings} for value in declarations):
        validation['warnings'].append('部分模拟依赖尚未填写节点位置和逐项接入待办；原声明保留，不能视为已交付真实服务。')
    if not bindings:
        return
    note = handoff_note(bindings)
    dsl['app']['description'] += note
    if task.get('app_type') == 'agent':
        dsl['agent_packages'][dsl['agent']['package_ref']]['metadata']['description'] += note
    validation['warnings'].append('模拟依赖位置仅通过节点存在检查；接入待办未验证完成，不证明模拟行为或真实接口可用。')


def verify_preserved(task, dsl, validation):
    """Check final hand-edited export without changing it or its stored approval."""
    bindings = (task.get('configuration') or {}).get('mock_dependency_bindings', [])
    if not bindings:
        return
    import copy
    apply_to_export(task, copy.deepcopy(dsl), validation)
    if not validation['valid']:
        raise ValueError('保留文件的模拟依赖检查失败：' + '; '.join(validation['errors']))
    descriptions = [dsl['app']['description']]
    if task.get('app_type') == 'agent':
        descriptions.append(dsl['agent_packages'][dsl['agent']['package_ref']]['metadata']['description'])
    if any(handoff_note(bindings) not in text for text in descriptions):
        raise ValueError('已确认保留文件缺少当前逐项接入待办说明；请明确补齐实际DSL的说明并重新分析确认，不会自动覆盖手改。')


def delivery_lines(task):
    cfg = task.get('configuration') or {}
    declarations = cfg.get('mock_dependencies') or []
    bindings = cfg.get('mock_dependency_bindings') or []
    if not declarations and not bindings:
        return []
    lines = ['人工填写的接入安排；节点存在性以当前构建的静态校验为准，不证明模拟实现或真实接入。']
    by_name = {item['dependency']: item for item in bindings}
    for declaration in declarations:
        item = by_name.get(declaration)
        lines.append(f"- {declaration}；位置：{item['node_id']}；接入待办（未验证完成）：{item['replacement_todo']}" if item else
                     f'- {declaration}；尚未填写节点位置与逐项接入待办。')
    if any(item['dependency'] not in declarations for item in bindings):
        lines.append('存在已不对应当前依赖声明的旧待办，须明确处理后重新构建。')
    return lines
