"""Current saved plan and matching prior inputs for bounded regeneration context."""
import copy
from .acceptance import same_json


def replanning_context(task):
    key = 'agent_plan' if task.get('app_type') == 'agent' else 'workflow_plan'
    plan = task.get(key)
    if not isinstance(plan, dict):
        return None
    matches = [v for v in reversed(task.get('versions', []))
               if isinstance(v, dict) and same_json(v.get(key),plan)]
    # Recent snapshots often only differ in name/cases. Find the latest actual
    # requirements/configuration transition against this exact saved plan.
    baseline = next((v for v in matches if any(
        v.get(k) != task.get(k) for k in ('requirements', 'configuration'))),
        matches[0] if matches else None)
    result = {
        'revision': task['revision'],
        'plan': copy.deepcopy(plan),
        'stale': bool(task.get('plan_stale')),
        'baseline_available': baseline is not None,
        'verification': 'saved_task_context_not_platform_evidence',
        'note': '以现有完整计划为修改基线，逐项对应当前明确需求；非目标字段保持，不把旧确认或运行证据沿用为本版批准。',
    }
    if baseline is not None:
        for key in ('requirements', 'configuration'):
            before, after = baseline.get(key), task.get(key)
            result['previous_' + key] = copy.deepcopy(before)
            result['changed_' + key + '_fields'] = sorted(
                k for k in set(before or {}) | set(after or {})
                if (before or {}).get(k) != (after or {}).get(k))
        result['baseline_revision'] = baseline['revision']
    return result
