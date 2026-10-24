"""Report instructions from saved current-App facts; never grant execution scope."""
from .workflow_publication import saved_publication


def describe(task, summary, *, runtime_key_paired=False):
    app = task.get('dify_app_id')
    rows = [r for r in task.get('runs', []) if r.get('revision') == task['revision']
            and r.get('environment_id') == task.get('environment_id')]
    def result(run):
        value = run.get('result')
        return value if isinstance(value, dict) else {}
    imported = bool(app) and any(r.get('kind') == 'import' and r.get('status') == 'success'
                                and result(r).get('app_id') == app for r in rows)
    mode = task.get('app_type')
    publication = saved_publication(task)
    todos = ['核对实际目标环境资源、插件和模型；本报告只读本机记录，没有访问Dify实时状态。']
    if not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or task.get('plan_stale'):
        todos.append('当前需求、配置或流程条件待复核；下面保存事实不能作为当前执行许可。')
    if imported:
        todos.append('已有与当前修订、环境及App匹配的成功导入记录，不要求重复导入。')
    else:
        todos.append('尚无与当前修订、环境及App匹配的成功导入记录；先核对成果、目标和具体资源方案，不能据静态检查推断已导入。')
    if mode not in {'workflow', 'advanced-chat'}:
        todos.append('原生Agent须按用户所选类型在Dify核对发布；不套用Workflow发布回执或改变应用类型。')
    elif publication['has_record'] and publication['status'] not in {'pending', 'unknown'} and not (publication['type_matches'] and publication['app_matches']):
        todos.append('当前发布记录缺少匹配应用类型依据，不套用Workflow发布回执；请核对原结果，禁止直接重发。')
    elif publication['uncertain']:
        todos.append('当前App发布结果未知或尚未返回，可能已经执行；核对原记录，禁止直接重发。')
    elif publication['published']:
        todos.append('已保存当前App发布成功回执，无需重复发布；外部编辑、删除或撤销仍须核对。')
    else:
        todos.append('尚无当前App的发布成功回执；先核对Dify实际状态，需要首次发布时另按明确方案确认，不能据试跑猜测。')
    if app and task.get('environment_id') and runtime_key_paired is True:
        todos.append('本机已有当前App配对的加密运行Key，无需再次创建或复制登记；外部撤销或改变后仍需重新核对。')
    else:
        todos.append('尚无当前App配对的本机运行Key；先核对App归属，再按已批准范围登记或准备创建，不沿用其他App的Key。')
    required = summary['required']
    if imported and required['total'] > 0 and summary.get('all_required_passed') is True:
        todos.append(f"已声明必选样例 {required['passed']} / {required['total']} 通过；核对保存输出及未覆盖场景，不要求为同一通过记录重复派发。")
    elif required.get('running') or required.get('unknown'):
        todos.append('样例仍有执行中或结果未知的记录；先核对原请求，不能直接当失败重新运行。')
    else:
        todos.append('已声明样例尚未全部通过或缺匹配导入依据；先核对未运行、失败或待人工复核项，新增运行仍须具体批准。')
    if task.get('configuration', {}).get('mock_dependencies'):
        todos.append('本任务声明模拟依赖；按原确认范围替换并重新验证，不能当真实依赖已经交付。')
    todos.append('规则通过不代表完整业务验收；继续核对未覆盖场景、真实依赖及供应商账单，任何新增模型、资源或运行仍须具体范围批准。')
    return todos
