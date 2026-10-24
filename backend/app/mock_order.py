"""Explicit single-node simulated order lookup proposal; never run or save it."""
import copy
import hashlib
import json
import re

from .plan_drafts import inspect_text, DraftRoute
from .plan_text_codec import parse, render, unique
from .workflow_plan import validate_plan

PREFIX = '【模拟订单查询，非真实订单】'


def template(records):
    # repr keeps all supplied values as literals, including quotes and newlines.
    return (
        '# Sierra 模拟订单查询模板 v1；仅使用明确提供的合成样例，不访问外部服务。\n'
        'def main(order_id: str = "") -> dict:\n'
        '    if order_id is None:\n'
        '        order_id = ""\n'
        '    if not isinstance(order_id, str):\n'
        '        raise ValueError("订单号须为文字，不自动转换数字或其它类型。")\n'
        '    key = order_id.strip()\n'
        f'    orders = {records!r}\n'
        '    if not key:\n'
        f'        return {{"result": {PREFIX + "请提供订单号。"!r}, "status": "mock_missing_order_id"}}\n'
        '    if key not in orders:\n'
        f'        return {{"result": {PREFIX + "合成样例中没有该订单，请核对订单号或联系人工客服。"!r}, "status": "mock_not_found"}}\n'
        f'    return {{"result": {PREFIX!r} + orders[key], "status": "mock_found"}}\n'
    )


def prepare(task, text, node_id, selector, records_text, dependency):
    if task.get('app_type') not in {'workflow', 'advanced-chat'}:
        raise ValueError('订单模拟模板仅支持Workflow或Chatflow；不会更换应用类型或为Agent配置工具。')
    inspect_text(text); plan = parse(text)
    if not validate_plan(task, plan)['valid']:
        raise ValueError('原流程尚未通过完整结构检查；请先处理原稿，不用订单模板顺带修图。')
    if dependency not in (task.get('configuration') or {}).get('mock_dependencies', []):
        raise ValueError('请先在配置中明确声明这项模拟依赖并保存，再准备订单模板。')
    if any(item['dependency'] == dependency and item['node_id'] != node_id for item in
           (task.get('configuration') or {}).get('mock_dependency_bindings', [])):
        raise ValueError('该模拟依赖已声明在其它位置，请先明确核对配置；不会自动修改位置绑定。')
    target = next((node for node in plan['nodes'] if node['id'] == node_id), None)
    if not target or target['type'] != 'code':
        raise ValueError('须明确选择根流程中已有的代码节点；不新增节点、不替换其它节点或容器内业务。')
    start = next((node for node in plan['nodes'] if node['type'] == 'start'), None)
    valid_sources = [] if not start else [[start['id'], value['variable']] for value in start['config'].get('variables', [])
        if value.get('type') in {'text-input', 'paragraph'}]
    if task['app_type'] == 'advanced-chat':
        valid_sources.append(['sys', 'query'])
    if selector not in valid_sources:
        raise ValueError('订单号只接受开始节点的明确文字字段，或Chatflow的整条query；不隐式提取、拼接或转换类型。')
    if not isinstance(records_text, str) or len(records_text.encode('utf-8')) > 20000:
        raise ValueError('合成订单表须为20KB内的JSON对象。')
    inspect_text(records_text)
    try:
        records = json.loads(records_text, object_pairs_hook=unique)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('合成订单表须为无重复订单号的完整JSON对象；不选择重复值。') from None
    if not isinstance(records, dict) or not 1 <= len(records) <= 10 or any(
        not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', key) or
        not isinstance(value, str) or not value.strip() or len(value) > 500 for key, value in records.items()):
        raise ValueError('合成订单表须含1—10个不同订单号（1—64位字母/数字/下划线/横线），每个对应非空且最多500字的固定说明。')
    proposal = copy.deepcopy(plan)
    changed = next(node for node in proposal['nodes'] if node['id'] == node_id)
    changed['config'].update(code_language='python3', code=template(records),
        variables=[{'variable': 'order_id', 'value_selector': selector}],
        outputs={'result': {'type': 'string', 'children': None}, 'status': {'type': 'string', 'children': None}})
    if not validate_plan(task, proposal)['valid']:
        raise ValueError('替换后未通过完整流程校验，可能存在下游输出引用不兼容；不删除引用或其它业务后放行。')
    restored = copy.deepcopy(proposal)
    next(node for node in restored['nodes'] if node['id'] == node_id)['config'] = copy.deepcopy(target['config'])
    assert restored == plan
    output = render(proposal)
    return {'plan_text': output, 'node_id': node_id, 'dependency': dependency, 'input_selector': selector,
        'source_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'records_text_sha256': hashlib.sha256(records_text.encode()).hexdigest(),
        'proposal_sha256': hashlib.sha256(output.encode()).hexdigest(),
        'verification': 'local_mock_order_template', 'only_selected_code_config_changed': True,
        'task_changed': False, 'network_requested': False, 'code_executed': False, 'platform_checked': False, 'business_verified': False}


def register(h):
    import asyncio
    from uuid import UUID
    from fastapi import APIRouter, HTTPException, Request
    from pydantic import BaseModel, ConfigDict, StrictStr, StrictInt, StrictBool, Field
    class Payload(BaseModel):
        model_config = ConfigDict(extra='forbid')
        revision: StrictInt = Field(ge=1)
        plan_text: StrictStr = Field(max_length=2000000)
        node_id: StrictStr = Field(min_length=1, max_length=256)
        input_selector: list[StrictStr] = Field(min_length=2, max_length=2)
        records_text: StrictStr = Field(max_length=20000)
        dependency: StrictStr = Field(min_length=1, max_length=2000)
        acknowledge_mock: StrictBool
        request_nonce: UUID
    router = APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/mock-order-template')
    async def preview(item_id: str, payload: Payload, request: Request):
        if not payload.acknowledge_mock:
            raise HTTPException(422, '请明确接受仅使用合成样例、替换已选节点代码/绑定/输出的模拟范围；不是实际接口接入。')
        try:
            raw = await request.body()
            if len(raw) > 4100000: raise ValueError()
            json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise HTTPException(422, '请求须为有界且无重复键的完整JSON，不回显原文。') from None
        with h.store.lock:
            task = h.get_task(item_id); h.require_revision(task, payload.revision); h.require_idle(task)
            context = copy.deepcopy(task)
        try:
            value = await asyncio.to_thread(prepare, context, payload.plan_text, payload.node_id,
                payload.input_selector, payload.records_text, payload.dependency)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except (TypeError, KeyError, IndexError, RecursionError, OverflowError):
            raise HTTPException(422, '此草稿不符合本次单节点模板范围；原计划保持，不做部分替换。') from None
        with h.store.lock:
            task = h.get_task(item_id); h.require_revision(task, payload.revision); h.require_idle(task)
        return {**value, 'task_id': item_id, 'revision': payload.revision, 'request_nonce': str(payload.request_nonce)}
    h.app.include_router(router)
