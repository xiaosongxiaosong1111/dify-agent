"""Guard one preserved Task/Budget and reject every other existing-object write."""
import copy
import json
from decimal import Decimal, InvalidOperation

from common import capture, digest, require, uuid
from reuse_policy import new_entries, preserve_budget, preserve_task

REQUIREMENTS = ('goal', 'audience', 'input', 'output', 'rules', 'knowledge', 'exceptions', 'tests')
BUDGET_LIMIT = Decimal('0.600')


def _money(value):
    require(isinstance(value, str) and value, 'Budget amount must be decimal text')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        require(False, 'Budget amount is not decimal')
    require(amount.is_finite(), 'Budget amount is not finite')
    return amount


def _approved_plans(contract):
    result = set()
    if not isinstance(contract, dict):
        return result
    if isinstance(contract.get('plan'), dict):
        result.add(digest(contract['plan']))
    for value in contract.values():
        if not isinstance(value, dict):
            continue
        if isinstance(value.get('plan'), dict):
            result.add(digest(value['plan']))
        if isinstance(value.get('plan_sha256'), str):
            result.add(value['plan_sha256'])
    return result


def guarded(base, env, provider, fixture, contract, boundary, old, reuse):
    """Return a Store subclass allowing exactly the preserved owner Task controls."""
    initial_task = reuse.get('task')
    initial_budget = reuse.get('budget')
    initial_limits = reuse.get('limits')
    provider_id = reuse.get('provider_id') or provider['id']
    require(isinstance(initial_task, dict) and isinstance(initial_budget, dict), 'Reuse binding missing')
    require(boundary.owner is not None and reuse.get('target', boundary.owner) == boundary.owner,
            'Guard owner not bound before Store construction')
    approved_plans = _approved_plans(contract)

    class Guarded(base):
        key_proposals = set()
        publications = set()
        service_writes = 0
        limits_written = 0

        def object_check(self, kind, item, value):
            require(isinstance(value, dict), 'Object must be a mapping')
            if kind == 'environment':
                require(item == env['id'], 'Other connection write')
                mutable = {'console_checked_at', 'console_auth_mode', 'console_login_blocked',
                           'console_failure_id', 'connection_revision', 'service_app_id', 'capabilities'}
                require({k: v for k, v in value.items() if k not in mutable}
                        == {k: v for k, v in env.items() if k not in mutable}, 'Connection source changed')
                require(value.get('service_app_id') in {env.get('service_app_id'), *boundary.apps},
                        'Wrong service App')
                require({k: v for k, v in value.get('capabilities', {}).items() if k not in {'console', 'runtime'}}
                        == {k: v for k, v in env.get('capabilities', {}).items() if k not in {'console', 'runtime'}},
                        'Other capability changed')
                return
            key = kind + ':' + item
            if key in old['objects']:
                require(item == boundary.owner and kind in {'task', 'task_budget', 'execution_limits'},
                        'Existing object write forbidden')
                if kind == 'task':
                    self._task(item, value)
                elif kind == 'task_budget':
                    self._budget(item, value)
                else:
                    self._limits(item, value)
                return
            if kind == 'task':
                require(False, 'New Task creation forbidden')
            if kind == 'task_budget':
                require(False, 'New Task budget forbidden')
            if kind == 'execution_limits':
                self._limits(item, value)
            elif kind in {'saved_console_reconnect', 'console_saved_reconnect', 'console_connection_failure'}:
                require(value.get('environment_id') == env['id'], 'Other authentication receipt')
            elif kind in {'workflow_publication', 'app_runtime_key_creation'}:
                require(value.get('task_id') == boundary.owner and value.get('environment_id') == env['id']
                        and value.get('app_id') in boundary.apps, 'Unbound resource receipt')
                records = self.publications if kind == 'workflow_publication' else self.key_proposals
                records.add(item)
                require(len(records) <= 2, 'Too many proposals')
            elif kind == 'app_runtime_credential':
                require(value.get('environment_id') == env['id'] and value.get('app_id') in boundary.apps
                        and item == env['id'] + ':app-runtime:' + str(value.get('app_id')), 'Wrong key archive')
            elif kind == 'runtime_key_previous_binding':
                require(value.get('environment_id') == env['id'] and value.get('source') in self.key_proposals
                        and item == str(value.get('source')) + ':previous-runtime-key'
                        and value.get('app_id') in {env.get('service_app_id'), *boundary.apps},
                        'Wrong previous key binding')
            elif kind in {'interview_operation', 'message_request'}:
                require(value.get('task_id') == boundary.owner, 'Other Task record')
                if kind == 'message_request':
                    require(item.startswith(boundary.owner + ':'), 'Wrong message receipt id')
            else:
                require(False, 'Unapproved object kind')

        def _task(self, item, value):
            require(item == boundary.owner and value.get('app_type') == 'advanced-chat'
                    and value.get('environment_id') == env['id'], 'Wrong existing Task/type/environment')
            req = value.get('requirements')
            require(isinstance(req, dict) and set(req) == set(REQUIREMENTS)
                    and all(isinstance(v, str) and len(v) <= 20000 for v in req.values())
                    and sum(len(v) for v in req.values()) <= 100000, 'Unapproved requirements structure')
            plan = value.get('workflow_plan')
            candidates = getattr(boundary, 'candidates', None) or ()
            approved = approved_plans | _approved_plans(getattr(boundary, 'contract', None)) \
                | {x for x in candidates if isinstance(x, str)}
            require(plan is None or isinstance(plan, dict) and digest(plan) in approved, 'Unexpected plan edit')
            require(all(isinstance(value.get(k, []), list)
                        for k in ('messages', 'planning_runs', 'interview_attempts', 'runs')),
                    'Malformed Task history')
            require(value.get('dify_app_id') in {None, *boundary.apps}, 'Wrong Task App')
            runs = value.get('runs', [])
            require(all(isinstance(r, dict) for r in runs), 'Malformed Task runs')
            require(all(sum(1 for r in runs if r.get('kind') == k) <= n
                        for k, n in [('import', 2), ('publish', 2), ('run', 12)]), 'Task record cap')
            if any(r.get('kind') == 'import' for r in runs):
                require(getattr(boundary, 'contract_reviewed', False), 'Import requires reviewed contract')
            preserve_task(initial_task, value, fixture)

        def _budget(self, item, value):
            require(item == boundary.owner and value.get('id') == item, 'Other Task budget')
            entries = value.get('entries', [])
            require(isinstance(entries, list) and len(entries) <= 6, 'Task budget entry cap')
            for entry in entries:
                require(isinstance(entry, dict) and entry.get('status') in {'reserved', 'settled', 'unknown'},
                        'Unexpected usage record')
                require(entry.get('provider_id') == provider['id'], 'Other model usage')
            if value.get('limit_usd') is None:
                require(not entries, 'Budget limit missing with usage')
            else:
                require(_money(value['limit_usd']) == BUDGET_LIMIT, 'Budget limit changed')
            history = value.get('policy_history', [])
            require(isinstance(history, list), 'Malformed budget history')
            for row in history:
                require(isinstance(row, dict) and (row.get('after') is None or _money(row['after']) <= BUDGET_LIMIT),
                        'Budget limit raised')
            preserve_budget(initial_budget, value, provider_id)

        def _limits(self, item, value):
            require(item == boundary.owner, 'Other execution policy')
            require(isinstance(value, dict) and value.get('id') == item, 'Wrong execution policy id')
            require(value.get('max_started_runs') == 12 and value.get('max_total_minutes') == 45
                    and value.get('max_reported_cost_usd') is None, 'Execution policy changed')
            require(isinstance(value.get('history'), list), 'Execution policy history missing')
            if initial_limits is None:
                require(self.limits_written == 0, 'Execution policy can only be set once')
                self.limits_written = 1
            else:
                require(digest(value) == digest(initial_limits), 'Existing execution policy changed')

        def _put_object(self, conn, states, kind, item, value):
            self.object_check(kind, item, value)
            return super()._put_object(conn, states, kind, item, value)

        def secret(self, item, key):
            allowed = item == provider['id'] and key == 'api_key'
            allowed = allowed or item == env['id'] and key in {
                'console_token', 'csrf_token', 'console_login_email', 'console_login_password',
                'service_api_key', 'dataset_api_key'}
            allowed = allowed or item in {env['id'] + ':app-runtime:' + a for a in boundary.apps} \
                and key == 'service_api_key'
            allowed = allowed or item.endswith(':previous-runtime-key') \
                and item.removesuffix(':previous-runtime-key') in self.key_proposals and key == 'service_api_key'
            require(allowed, 'Other credential read forbidden')
            return super().secret(item, key)

        def check_secrets(self, sets):
            for owner, values in sets.items():
                for key, value in values.items():
                    require(isinstance(value, str) and value, 'Empty secret write')
                    if owner == env['id']:
                        require(key in {'console_token', 'csrf_token', 'service_api_key'},
                                'Saved login/key mutation forbidden')
                        if key == 'service_api_key':
                            require(boundary.current in boundary.apps
                                    and value == boundary.apps[boundary.current]['key']
                                    and self.service_writes < 2, 'Wrong service Key')
                            self.service_writes += 1
                        else:
                            require(boundary.workspace_verified and boundary.login_tokens
                                    and value == boundary.login_tokens[key],
                                    'Workspace proof required before tokens saved')
                    elif owner in {env['id'] + ':app-runtime:' + a for a in boundary.apps}:
                        require(key == 'service_api_key'
                                and value == boundary.apps[owner.rsplit(':', 1)[1]]['key']
                                and owner + ':' + key not in old['secrets'], 'Wrong new App archive')
                    else:
                        require(owner.endswith(':previous-runtime-key')
                                and owner.removesuffix(':previous-runtime-key') in self.key_proposals
                                and key == 'service_api_key'
                                and value == self.secret(env['id'], 'service_api_key'),
                                'Wrong previous Key archive')

        def set_secret(self, item, key, value):
            self.check_secrets({item: {key: value}})
            return super().set_secret(item, key, value)

        def put_with_secrets(self, kind, item, value, secrets):
            self.check_secrets({item: secrets})
            return super().put_with_secrets(kind, item, value, secrets)

        def put_many_with_secrets(self, rows, item, secrets):
            self.check_secrets({item: secrets})
            return super().put_many_with_secrets(rows, item, secrets)

        def put_many_with_secret_sets(self, rows, sets):
            self.check_secrets(sets)
            return super().put_many_with_secret_sets(rows, sets)

        def delete(self, *args):
            raise RuntimeError('Delete forbidden')

    return Guarded


def verify(store, env, boundary, old, reuse):
    now = capture(store)
    owner = boundary.owner
    provider_id = reuse.get('provider_id')
    initial_task = reuse['task']
    initial_budget = reuse['budget']
    initial_limits = reuse.get('limits')
    task = store.get('task', owner)
    budget = store.get('task_budget', owner)
    limits = store.get('execution_limits', owner)
    require(isinstance(task, dict) and isinstance(budget, dict), 'Target Task/Budget missing')
    preserve_task(initial_task, task, reuse.get('fixture') or {})
    preserve_budget(initial_budget, budget, provider_id)
    new_model = len(new_entries(initial_budget, budget)) > 0
    new_planning = len(task.get('planning_runs', [])) > len(initial_task.get('planning_runs', []))
    new_runs = len(task.get('runs', [])) > len(initial_task.get('runs', []))
    new_resources = (task.get('artifact') is not None or task.get('dify_app_id') is not None
                     or task.get('workflow_plan') is not None)
    if initial_limits is None:
        if limits is None:
            require(not (new_model or new_planning or new_runs or new_resources),
                    'Execution policy required once planning/resource/run starts')
        else:
            require(isinstance(limits, dict) and limits.get('max_started_runs') == 12
                    and limits.get('max_total_minutes') == 45
                    and limits.get('max_reported_cost_usd') is None,
                    'Execution policy must be 12/45/None')
    else:
        require(digest(limits) == digest(initial_limits), 'Existing execution policy changed')
    allowed = {'environment:' + env['id'], 'task:' + owner, 'task_budget:' + owner,
               'execution_limits:' + owner}
    require(all(now['objects'].get(k) == v for k, v in old['objects'].items() if k not in allowed),
            'Original object changed')
    require(len(store.list('task')) == sum(k.startswith('task:') for k in old['objects']),
            'Task count changed')
    require(all(now['secrets'].get(k) == v for k, v in old['secrets'].items()
                if k not in {env['id'] + ':console_token', env['id'] + ':csrf_token',
                             env['id'] + ':service_api_key'}), 'Original credentials changed')
    require(all(now['files'].get(k) == v for k, v in old['files'].items()), 'Original files/assets changed')
    require(all(k in old['files'] or k.startswith(str(owner) + '\\') or k.startswith(str(owner) + '/')
                for k in now['files']), 'Unrelated new file')
    with store.connect() as db:
        for kind, item, raw in db.execute('SELECT kind,id,value FROM objects'):
            if kind + ':' + item not in old['objects']:
                if kind == 'execution_limits' and item == owner:
                    continue
                store.object_check(kind, item, json.loads(raw))
    policy_12_45 = isinstance(limits, dict) and limits.get('max_started_runs') == 12 \
        and limits.get('max_total_minutes') == 45 and limits.get('max_reported_cost_usd') is None
    original_none_kept = (limits is None) if initial_limits is None \
        else digest(limits) == digest(initial_limits)
    return {'original_objects_kept': True, 'original_task_and_ledger_prefix_kept': True,
            'old_credentials_and_assets_kept': True, 'new_tasks': 0,
            'execution_policy_12_45': bool(policy_12_45),
            'original_execution_policy_none_kept': bool(original_none_kept)}
