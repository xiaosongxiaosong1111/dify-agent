"""Explicit, one-field text transfer between reviewed candidate and saved plan."""
import copy
import hashlib
import json
import re
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from .dsl_roundtrip import digest
from .plan_text_codec import render
from .plan_drafts import inspect_text
from .retained_plan import candidate

TEXT_FIELDS = {'llm': ('system_prompt', 'user_prompt'), 'template-transform': ('template',)}
NOTE = '用户明确选择候选源字段和原方案同类型目标；只替换这一项文字，不猜节点对应关系，不修改其他字段或正式方案。引用占位符/模板语句须保持；仍需校验、保存及重新确认。'


def fields(plan, app_type):
    inspect_text(render(plan))
    result = []; seen = set()
    def add(path, node_id, node_type, field, value):
        if not isinstance(value, str): return
        if len(result) >= 400: raise HTTPException(422, '文字字段超过400项，不能返回局部映射范围。')
        result.append({'id': digest({'path': path, 'node_type': node_type, 'field': field, 'value': value}), 'path': path, 'node_id': node_id, 'node_type': node_type, 'field': field, 'value_text': value})
    if app_type == 'agent':
        add(['system_prompt'], 'Agent指令', 'agent', 'system_prompt', plan.get('system_prompt'))
        return result
    def visit(nodes, path):
        if not isinstance(nodes, list): return
        for index, node in enumerate(nodes):
            if not isinstance(node, dict) or not isinstance(node.get('id'), str):
                raise HTTPException(422, '节点缺少明确标识，不能映射文字字段。')
            if node['id'] in seen: raise HTTPException(422, '节点标识重复，不能猜测对应关系。')
            seen.add(node['id']); kind = node.get('type'); cfg = node.get('config')
            if not isinstance(kind, str): raise HTTPException(422, '节点类型不明确，不能映射文字字段。')
            if not isinstance(cfg, dict): continue
            for field in TEXT_FIELDS.get(kind, ()):
                add(path + [index, 'config', field], node['id'], kind, field, cfg.get(field))
            visit(cfg.get('nodes'), path + [index, 'config', 'nodes'])
    visit(plan.get('nodes'), ['nodes'])
    return result


def transfer(baseline, source_field, target_field):
    if source_field['node_type'] != target_field['node_type'] or source_field['field'] != target_field['field']:
        raise HTTPException(422, '源与目标必须是相同节点类型及同名文字字段，不转换或猜测用途。')
    value = source_field['value_text']; before = target_field['value_text']
    if value == before: raise HTTPException(409, '两项文字完全相同，无需合成变化。')
    def markup(text):
        pattern = r'{{.*?}}|{%.*?%}|{#.*?#}'
        rest = re.sub(pattern, '', text, flags=re.S)
        if any(marker in rest for marker in ('{{', '}}', '{%', '%}', '{#', '#}')):
            raise HTTPException(422, '文字含不完整占位符或模板语句，不能单字段映射。')
        return sorted(re.findall(pattern, text, flags=re.S))
    if markup(value) != markup(before):
        raise HTTPException(422, '源文字改变了引用占位符或模板语句，不能只替换文字；请核对完整方案。')
    result = copy.deepcopy(baseline); parent = result
    for part in target_field['path'][:-1]: parent = parent[part]
    # Internal paths only: never accept arbitrary user-provided JSON patches.
    parent[target_field['path'][-1]] = value
    inspect_text(render(result))
    return result


class Mapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    review_token: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    source_id: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    target_id: StrictStr = Field(pattern='^[a-f0-9]{64}$')
    confirm_transfer: StrictBool


def register(h, router, source, metadata):
    @router.get('/api/tasks/{item_id}/planning/{run_id}/candidate-text-mapping')
    def read(item_id: str, run_id: str, revision: int):
        with h.store.lock:
            task, baseline, _, token, sha = source(item_id, run_id, revision)
            complete = json.loads(candidate(task, run_id)['plan_text'])
            return metadata(task, run_id, token, sha) | {'verification': 'explicit_text_mapping_review', 'sources': fields(complete, task['app_type']), 'targets': fields(baseline, task['app_type']), 'note': NOTE}

    @router.post('/api/tasks/{item_id}/planning/{run_id}/candidate-text-mapping/compose')
    def compose(item_id: str, run_id: str, payload: Mapping):
        with h.store.lock:
            task, baseline, _, token, sha = source(item_id, run_id, payload.revision)
            if token != payload.review_token or payload.confirm_transfer is not True:
                raise HTTPException(409, '候选或原方案已变化，或未明确同意单字段替换；未合成草稿。')
            complete = json.loads(candidate(task, run_id)['plan_text'])
            src = next((v for v in fields(complete, task['app_type']) if v['id'] == payload.source_id), None)
            dst = next((v for v in fields(baseline, task['app_type']) if v['id'] == payload.target_id), None)
            if src is None or dst is None: raise HTTPException(409, '所选源或目标不属于当前完整方案，未合成。')
            result = transfer(baseline, src, dst); text = render(result); size, _ = inspect_text(text)
            return metadata(task, run_id, token, sha) | {'verification': 'mapped_text_unconfirmed_draft', 'plan_text': text, 'byte_count': size, 'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'source_id': src['id'], 'target_id': dst['id'], 'changed_fields': 1, 'static_validated': False, 'note': NOTE}
