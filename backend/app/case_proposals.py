"""Revision-bound evaluation suggestions. Adoption appends cases, never runs them."""
from __future__ import annotations
from .contract_loading import load_contract

import copy
import hashlib
import json
import re
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt

from .evaluation import validate_test_cases
from .intake import require_ready as require_intake


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt


class Adopt(Revision):
    proposal_id: str
    proposal_token: str
    item_ids: list[str]
    acknowledge_review: StrictBool


def case_key(case):
    return digest({key: case.get(key) for key in ('input', 'expectation', 'followups')})


class CaseProposalManager:
    def __init__(self, host):
        self.h = host

    def contract(self, task):
        """Use the current confirmed overlay when present, rather than a stale IR."""
        from .coverage import final_root
        if task.get('dsl_reference'):
            root, error = final_root(task)
            if error:
                raise HTTPException(422, error)
            nodes = root['workflow']['graph']['nodes']
            nodes = [{'id': n['id'], 'type': n['data']['type'], 'config': n['data']} for n in nodes]
            from .case_dsl_semantics import summary
            source = {'kind': 'preserved_dsl', 'digest': digest(root), 'semantics': summary(root)}
        elif task.get('workflow_plan'):
            from .iteration import plan_nodes
            nodes = list(plan_nodes(task['workflow_plan']))
            source = {'kind': 'workflow_plan', 'plan': task['workflow_plan']}
        elif task['app_type'] == 'agent':
            nodes = []
            source = {'kind': 'agent_plan', 'plan': task.get('agent_plan')}
        else:
            nodes = []
            source = {'kind': 'basic_template'}
        start = next((n for n in nodes if n['type'] == 'start'), None)
        variables = (start.get('config') or {}).get('variables', []) if start else []
        from .file_inputs import has_files,RUNTIME_LIMIT
        if has_files(variables):raise HTTPException(422,RUNTIME_LIMIT+' 自动样例生成已暂停，不会消耗模型费用制造假文件引用。')
        from .json_inputs import has_objects
        if task['app_type']!='workflow' and has_objects(variables):raise HTTPException(422,'JSON对象入口首批仅Workflow，Chatflow与Agent尚未适配，不改变应用类型或调用模型。')
        from .start_inputs import declared_type,validate_variable
        if not isinstance(variables,list) or any(not isinstance(v,dict) or not isinstance(v.get('variable'),str) or not v['variable'] for v in variables):
            raise HTTPException(422,'验收样例入口声明结构未适配，先核对开始变量，不能猜测或省略后调用模型。')
        if len({v['variable'] for v in variables})!=len(variables):raise HTTPException(422,'验收样例入口变量名重复，请先明确输入来源。')
        for variable in variables:
            errors=validate_variable(variable)
            if errors:raise HTTPException(422,'验收样例入口声明尚未适配：'+'；'.join(errors)+' 原值保持，未生成候选。')
        inputs = {v['variable']: {'required': bool(v.get('required', True)), 'type': declared_type(variables, v['variable']),
                  **({key:v[key] for key in ('options','default','max_length','json_schema') if key in v})} for v in variables}
        if task['app_type'] == 'workflow':
            if not nodes:
                inputs = {'query': {'required': True, 'type': 'string'}}
            outputs = sorted({o['variable'] for n in nodes if n['type'] == 'end' for o in n.get('config', {}).get('outputs', [])}) if nodes else ['result']
        else:
            inputs['query'] = {'required': True, 'type': 'string'}
            outputs = ['answer']
        return {'inputs': inputs, 'outputs': outputs, 'nodes': [{'id': n['id'], 'type': n['type']} for n in nodes], 'source': source}

    def stamp(self, task):
        env = self.h.store.get('environment', task.get('environment_id') or '')
        return digest({'revision': task['revision'], 'requirements_confirmed': task['requirements_confirmed'], 'requirements': task['requirements'], 'configuration': task['configuration'], 'environment': self.h.env_snapshot(env) if env else None, 'test_cases': task['test_cases'], 'plan_stale': task.get('plan_stale'), 'contract': self.contract(task), 'intake': task.get('intake_review'), 'coverage': task.get('coverage_review'), 'conflicts': task.get('conflict_review')})

    def validate(self, task, value):
        errors = []
        try:
            if not isinstance(value, dict) or set(value) != {'schema_version', 'items', 'open_issues', 'notes'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
                raise ValueError('样例建议须为 schema_version=1、items、open_issues 和 notes。')
            if not isinstance(value['notes'], str) or len(value['notes']) > 4000:
                raise ValueError('样例说明须为最多 4000 字的文本。')
            issues = value['open_issues']
            if not isinstance(issues, list) or len(issues) > 12 or any(not isinstance(i, dict) or set(i) != {'question', 'recommendation'} or any(not isinstance(v, str) or not 0 < len(v.strip()) <= 2000 for v in i.values()) for i in issues):
                raise ValueError('待决定事项最多 12 项，每项须有明确问题和建议。')
            items = value['items']
            if not isinstance(items, list) or not 1 <= len(items) <= 12:
                raise ValueError('每份建议须有 1—12 个样例。')
            if len(json.dumps(value, ensure_ascii=False)) > 80000:
                raise ValueError('样例建议超过大小限制。')
            contract = self.contract(task)
            nodes = {n['id']: n['type'] for n in contract['nodes']}
            seen, names, keys = set(), set(), {case_key(c) for c in task['test_cases']}
            for index, item in enumerate(items, 1):
                prefix = f'建议样例 {index}：'
                if not isinstance(item, dict) or set(item) != {'id', 'category', 'purpose', 'source', 'node_ids', 'case'}:
                    raise ValueError(prefix + '字段不完整或包含未知字段。')
                iid = item['id']
                if not isinstance(iid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', iid) or iid in seen:
                    raise ValueError(prefix + '建议 ID 须唯一且符合命名规则。')
                seen.add(iid)
                if item['category'] not in ('normal', 'branch', 'exception', 'conversation'):
                    raise ValueError(prefix + '类别须为 normal、branch、exception 或 conversation。')
                if not isinstance(item['purpose'], str) or not 0 < len(item['purpose'].strip()) <= 2000:
                    raise ValueError(prefix + '须说明检查目的。')
                source = item['source']
                if not isinstance(source, dict) or set(source) != {'field', 'quote'} or not isinstance(source['field'], str) or source['field'] not in self.h.REQ_KEYS or not isinstance(source['quote'], str) or not 0 < len(source['quote'].strip()) <= 2000 or source['quote'] not in task['requirements'][source['field']]:
                    raise ValueError(prefix + '来源须引用当前需求字段的原文，不能编造。')
                refs = item['node_ids']
                if not isinstance(refs, list) or len(refs) > 20 or any(not isinstance(r, str) or r not in nodes for r in refs) or len(set(refs)) != len(refs):
                    raise ValueError(prefix + '关联节点须存在且不能重复。')
                if item['category'] == 'branch' and not any(nodes[r] == 'if-else' for r in refs):
                    raise ValueError(prefix + '分支样例须关联实际条件节点；不能虚构分支。')
                case = item['case']
                if not isinstance(case, dict) or not {'name', 'input', 'required', 'expectation'} <= set(case) or set(case) - {'name', 'input', 'required', 'expectation', 'followups'} or case['required'] is not True:
                    raise ValueError(prefix + '须有名称、输入、必选标记及预期，不允许模型改变现有样例或预设可忽略。')
                checked = validate_test_cases([case], task['app_type'])
                if not checked['valid']:
                    raise ValueError(prefix + '；'.join(checked['errors']))
                if len(case['name']) > 200 or case['name'].strip() in names or case_key(case) in keys:
                    raise ValueError(prefix + '名称须唯一且最多 200 字；不能重复已有或本次输入与预期。')
                names.add(case['name'].strip()); keys.add(case_key(case))
                if (item['category'] == 'conversation') != bool(case.get('followups')):
                    raise ValueError(prefix + '多轮类别与后续轮次须一致。')
                for turn in [case, *case.get('followups', [])]:
                    inp = turn['input']
                    if set(inp) - set(contract['inputs']):
                        raise ValueError(prefix + '输入只能使用当前入口声明，不能添加会话 ID、文件或未知变量。')
                    from .start_inputs import finite_number
                    for name,value in inp.items():
                        rule=contract['inputs'][name]
                        if rule['type']=='number':
                            if not finite_number(value):raise ValueError(prefix+'数字输入须为有限 JSON 数字，不能是布尔值或数字文本。')
                        elif rule['type']=='object':
                            from .json_inputs import validate_value
                            validate_value(rule.get('json_schema'),value)
                        elif rule['type']=='boolean':
                            if type(value) is not bool:raise ValueError(prefix+'布尔输入须为JSON true／false，不转换数字、文本或null。')
                        elif rule['type']!='string' or not isinstance(value,str) or len(value)>8000:
                            raise ValueError(prefix+'文字／选项输入须为最多 8000 字的文本，未知入口类型尚未适配。')
                        limit=rule.get('max_length')
                        if rule['type']=='string' and not rule.get('options') and type(limit) is int and limit>0 and len(value)>limit:
                            raise ValueError(prefix+'文字输入超过已声明max_length；不截断或忽略边界。')
                        if 'options' in rule and rule['options'] and value not in rule['options']:
                            raise ValueError(prefix+'选项输入须属于已配置的 options。')
                    if any(rule['required'] and name not in inp for name, rule in contract['inputs'].items()):
                        raise ValueError(prefix + '缺少当前入口必填变量。')
                    if task['app_type'] != 'workflow' and not inp.get('query', '').strip():
                        raise ValueError(prefix + '对话入口需要非空 query；缺少业务信息应写成可发送的提问。')
                    exp = turn['expectation']
                    allowed = {'mode', 'description'} if exp['mode'] == 'manual' else {'mode', 'target', 'expected'}
                    if set(exp) != allowed:
                        raise ValueError(prefix + '预期仅包含对应检查模式的字段。')
                    if exp['mode'] != 'manual' and exp['target'].split('.')[0] not in contract['outputs']:
                        raise ValueError(prefix + '预期路径不属于当前应用输出，不能虚构结果字段。')
                if task['app_type']=='advanced-chat' and case.get('followups') and set(contract['inputs'])-{'query'}:
                    from .start_inputs import require_stable_chat_turns
                    require_stable_chat_turns(case)
        except (ValueError, HTTPException, TypeError, KeyError) as exc:
            errors.append(str(exc.detail) if isinstance(exc, HTTPException) else str(exc))
        return {'valid': not errors, 'errors': errors}

    def state(self, task):
        records = [r for r in self.h.store.list('case_proposal') if r['task_id'] == task['id']]
        record = records[0] if records else None
        error = None
        try:
            contract = self.contract(task)
            stale = bool(record and record['context_stamp'] != self.stamp(task))
        except HTTPException as exc:
            contract = None; stale = bool(record); error = str(exc.detail)
        return {'revision': task['revision'], 'generation_route': self.h.routing.preview(task), 'record': record, 'stale': stale, 'contract': contract, 'blocker': error, 'can_adopt': bool(record and record['status'] == 'proposed' and not stale and not record['candidate']['open_issues']), 'history': [{'id': r['id'], 'status': r['status'], 'origin_revision': r['origin_revision'], 'created_at': r['created_at'], 'applied_revision': r.get('applied_revision'), 'selected_item_ids': r.get('selected_item_ids', [])} for r in records], 'scope_note': '建议仅为待复核的输入和检查规则。采纳只追加本地样例，不修改已有样例、执行试跑或证明分支／业务已覆盖；语义质量仍需用户判断。'}

    def save(self, task, value):
        record = {'id': str(uuid.uuid4()), 'task_id': task['id'], 'origin_revision': task['revision'], 'created_at': self.h.now(), 'status': 'proposed', 'context_stamp': self.stamp(task), 'candidate': copy.deepcopy(value)}
        operation=next((op for op in reversed(task.get('planning_runs',[])) if op.get('kind')=='cases' and op.get('status')=='ready_to_confirm' and op.get('revision')==task['revision']),None)
        record['generation_origin']={key:copy.deepcopy(operation.get(key)) for key in ('id','provider_id','model','routing')} if operation else None
        record['proposal_token'] = digest(record)
        self.h.store.put('case_proposal', record['id'], record)
        return task

    def register(self):
        h = self.h

        @h.app.get('/api/tasks/{item_id}/case-proposal')
        def state(item_id: str):
            return self.state(h.get_task(item_id))

        @h.app.post('/api/tasks/{item_id}/case-proposal/generate')
        async def generate(item_id: str, payload: Revision):
            from .bounded_suggestions import suggest
            stamps = []

            def messages(task):
                require_intake(task); h.require_conflicts(task)
                if not task['requirements_confirmed']:
                    raise HTTPException(422, '请先确认当前需求，再建议验收样例。')
                if task.get('plan_stale'):
                    raise HTTPException(422, '流程计划已过期，请先复核并保存；不按旧流程生成样例。')
                if task['app_type'] == 'agent' and not task.get('agent_plan'):
                    raise HTTPException(422, '请先保存原生 Agent 方案，再建议样例。')
                stamps.append(self.stamp(task))
                prompt = load_contract(h.PROJECT_ROOT,'case-model-contract.md')
                return [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': json.dumps({'app_type': task['app_type'], 'requirements': task['requirements'], 'configuration': {k: v for k, v in task['configuration'].items() if k != 'assistant_provider_id'}, 'contract': self.contract(task), 'existing_cases': task['test_cases'], 'coverage_items': (task.get('coverage_review') or {}).get('items', [])}, ensure_ascii=False)}]

            def save(task, candidate):
                if self.stamp(task) != stamps[0]:
                    raise HTTPException(409, '样例依据已变化，候选未应用，请重新核对。')
                return self.save(task, candidate)

            return await suggest(h, item_id, payload.revision, 'cases', messages, self.validate, save)

        @h.app.post('/api/tasks/{item_id}/case-proposal/adopt')
        def adopt(item_id: str, payload: Adopt):
            with h.store.lock:
                task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload.revision)
                value = self.state(task); record = value['record']
                if not record or record['id'] != payload.proposal_id or record['proposal_token'] != payload.proposal_token or not value['can_adopt']:
                    raise HTTPException(409, '建议已过期、已采纳或有待决定事项，请重新核对，不能应用旧建议。')
                checked = self.validate(task, record['candidate'])
                if not checked['valid']:
                    raise HTTPException(422, '；'.join(checked['errors']))
                ids = payload.item_ids
                known = {i['id'] for i in record['candidate']['items']}
                if not ids or len(set(ids)) != len(ids) or set(ids) - known:
                    raise HTTPException(422, '请选择至少一个当前建议样例；选择不能重复或引用未知样例。')
                if not payload.acknowledge_review:
                    raise HTTPException(422, '请明确核对所选输入、检查规则及人工判断标准；建议不等于运行通过。')
                additions = [{**copy.deepcopy(i['case']), 'id': str(uuid.uuid4())} for i in record['candidate']['items'] if i['id'] in ids]
                h.invalidate(task, '验收建议采纳前保存')
                task['test_cases'].extend(additions); task['updated_at'] = h.now()
                record.update(status='adopted', applied_revision=task['revision'], adopted_at=h.now(), selected_item_ids=ids, added_case_ids=[c['id'] for c in additions], acknowledge_review=True)
                h.store.put_many([('task', item_id, task), ('case_proposal', record['id'], record)])
                return task
