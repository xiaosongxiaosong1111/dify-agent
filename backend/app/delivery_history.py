"""Value-free index of this task's saved versions and confirmation metadata."""
from datetime import datetime
from uuid import UUID

VERSION_LIMIT = 100
CONFIRMATION_LIMIT = 500
FIELDS = {
    'requirements': '需求', 'configuration': '配置', 'environment_id': '目标环境',
    'materials': '材料登记', 'workflow_plan': '流程计划', 'agent_plan': 'Agent计划',
    'test_cases': '验收样例', 'dsl_reference': '参考DSL', 'dsl_overlay': 'DSL保留方案',
    'coverage_review': '覆盖复核', 'conflict_review': '冲突复核', 'intake_review': '需求准入复核',
}
KINDS = {'requirements': '需求', 'configuration': '配置'}
NOTE = ('仅导出本任务已保存的版本元数据、分区差异和确认日志，不导出历史正文、版本标签或凭据。'
        '快照在修改前保存，差异比较其后一个保存快照或当前记录；同修订可能有多次快照。'
        '未记录字段不回填为历史值，确认日志不证明操作者身份、外部资源许可或业务验收。')


def revision(value):
    return type(value) is int and value > 0


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64 or 'T' not in value:
        return None
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return value


def identifier(value):
    try:
        return str(UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def snapshot(task):
    current = task['revision']
    if not revision(current):
        raise ValueError('Invalid current revision')
    versions = task.get('versions', [])
    confirmations = task.get('confirmations', [])
    bad_versions = not isinstance(versions, list)
    bad_confirmations = not isinstance(confirmations, list)
    versions = versions if not bad_versions else []
    confirmations = confirmations if not bad_confirmations else []
    version_rows, confirmation_rows = [], []
    unreadable_versions = unreadable_confirmations = 0
    for index in range(max(0, len(versions) - VERSION_LIMIT), len(versions)):
        row = versions[index]
        target = versions[index + 1] if index + 1 < len(versions) else task
        if not isinstance(row, dict) or not revision(row.get('revision')) or row['revision'] > current:
            unreadable_versions += 1
            continue
        comparable = isinstance(target, dict) and revision(target.get('revision')) and row['revision'] <= target['revision'] <= current
        known = [key for key in FIELDS if key in row and comparable and key in target]
        version_rows.append({
            'sequence': index + 1, 'id': identifier(row.get('id')), 'revision': row['revision'],
            'created_at': timestamp(row.get('created_at')),
            'compared_to_revision': target['revision'] if comparable else None,
            'changed_sections': [FIELDS[key] for key in known if row[key] != target[key]],
            'unrecorded_sections': [FIELDS[key] for key in FIELDS if key not in known],
        })
    for index in range(max(0, len(confirmations) - CONFIRMATION_LIMIT), len(confirmations)):
        row = confirmations[index]
        if (not isinstance(row, dict) or not isinstance(row.get('kind'), str) or row['kind'] not in KINDS
                or not revision(row.get('revision')) or row['revision'] > current
                or ('carried_from_revision' in row and (not revision(row['carried_from_revision'])
                    or row['carried_from_revision'] >= row['revision']))):
            unreadable_confirmations += 1
            continue
        confirmation_rows.append({
            'sequence': index + 1, 'kind': row['kind'], 'revision': row['revision'],
            'created_at': timestamp(row.get('created_at')),
            'carried_from_revision': row.get('carried_from_revision'),
            'matches_current_revision': row['revision'] == current,
        })
    return {
        'revision': current,
        'current_flags': {kind: task.get(kind + '_confirmed') is True for kind in KINDS},
        'version_total': len(versions), 'confirmation_total': len(confirmations),
        'version_rows': version_rows, 'confirmation_rows': confirmation_rows,
        'version_omitted': max(0, len(versions) - VERSION_LIMIT),
        'confirmation_omitted': max(0, len(confirmations) - CONFIRMATION_LIMIT),
        'unreadable_versions': unreadable_versions, 'unreadable_confirmations': unreadable_confirmations,
        'invalid_version_container': bad_versions, 'invalid_confirmation_container': bad_confirmations,
    }


def render(task):
    data = snapshot(task)
    lines = ['## 版本、修改与确认记录', '', NOTE, '',
             f"当前修订：r{data['revision']}。当前保存标志：" + '；'.join(
                 KINDS[kind] + ('已确认' if data['current_flags'][kind] else '未确认') for kind in KINDS) + '。', '',
             '### 保存快照与后续变更', '',
             f"已保存快照总数：{data['version_total']}；仅列最后{VERSION_LIMIT}条，省略{data['version_omitted']}条，选中范围无法读取{data['unreadable_versions']}条。",
             '', '| 序号 | 快照修订 → 比较修订 | 保存时间 | 快照ID | 变化分区（仅已记录字段） | 未记录或无法比较分区 |',
             '|---|---|---|---|---|---|']
    for row in data['version_rows']:
        target = '未知' if row['compared_to_revision'] is None else 'r' + str(row['compared_to_revision'])
        changes = '、'.join(row['changed_sections']) or ('没有可比较字段' if len(row['unrecorded_sections']) == len(FIELDS) else '已记录字段未见差异')
        lines.append(f"| {row['sequence']} | r{row['revision']} → {target} | {row['created_at'] or '未记录或格式无效'} | {row['id'] or '未记录或格式无效'} | {changes} | {'、'.join(row['unrecorded_sections']) or '无'} |")
    if not data['version_rows']:
        lines += ['', '没有可展开的历史快照，不以当前内容补造旧版本。']
    lines += ['', '### 确认日志', '',
              f"已保存确认总数：{data['confirmation_total']}；仅列最后{CONFIRMATION_LIMIT}条，省略{data['confirmation_omitted']}条，选中范围无法读取{data['unreadable_confirmations']}条。", '',
              '| 序号 | 修订 | 类别 | 记录方式 | 记录时间 | 对应当前修订 |', '|---|---|---|---|---|---|']
    for row in data['confirmation_rows']:
        source = '显式确认日志' if row['carried_from_revision'] is None else '从r' + str(row['carried_from_revision']) + '沿用'
        lines.append(f"| {row['sequence']} | r{row['revision']} | {KINDS[row['kind']]} | {source} | {row['created_at'] or '未记录或格式无效'} | {'是' if row['matches_current_revision'] else '否，历史记录'} |")
    for kind, label in KINDS.items():
        if not any(row['kind'] == kind and row['matches_current_revision'] for row in data['confirmation_rows']):
            lines += ['', label + '：所列日志没有当前修订的确认记录；不根据当前标志反推确认人或确认时间。']
    if data['invalid_version_container'] or data['invalid_confirmation_container']:
        lines += ['', '历史集合格式无法识别，上述可展开总数不代表原记录为空；请在本机版本页核对，未补造或修改原数据。']
    return lines
