"""Generate a pure Python guard for the supported schema subset; never execute it."""
import copy
import hashlib
import json
from .structured_output import native, output_type, NOTE


MARKER = '# Sierra strict schema guard v1\n'


CHECKER = '''
def _check(value, rule):
    kind = rule["type"]
    if kind == "object":
        if type(value) is not dict or any(type(k) is not str for k in value): return False
        properties = rule["properties"]
        if any(k not in properties for k in value): return False
        if any(k not in value for k in rule.get("required", [])): return False
        return all(_check(v, properties[k]) for k, v in value.items())
    if kind == "array":
        if type(value) is not list: return False
        if "minItems" in rule and len(value) < rule["minItems"]: return False
        if "maxItems" in rule and len(value) > rule["maxItems"]: return False
        return all(_check(v, rule["items"]) for v in value)
    if kind == "string":
        if type(value) is not str: return False
        if "minLength" in rule and len(value) < rule["minLength"]: return False
        if "maxLength" in rule and len(value) > rule["maxLength"]: return False
    elif kind == "boolean":
        if type(value) is not bool: return False
    elif kind in ("number", "integer"):
        if type(value) not in (int, float): return False
        if type(value) is float and not math.isfinite(value): return False
        if kind == "integer" and type(value) is float and not value.is_integer(): return False
        if "minimum" in rule and value < rule["minimum"]: return False
        if "maximum" in rule and value > rule["maximum"]: return False
    else:
        return False
    return "enum" not in rule or any(value == option for option in rule["enum"])


def main(data: dict) -> dict:
    if not _check(data, _SCHEMA):
        raise ValueError("结构化对象未通过当前Schema校验，本次运行失败；未补默认或重试。")
    return {"result": data}
'''


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def guard_code(schema):
    normalized = json.loads(json.dumps(schema, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return MARKER + 'import math\n\n_SCHEMA = ' + repr(normalized) + '\n' + CHECKER


def validate_generated(node, nodes, edges, *, mode, nested=False):
    cfg = node.get('config', {})
    code = cfg.get('code')
    if not isinstance(code, str) or not code.startswith(MARKER): return []
    if set(cfg) - {'code_language','code','variables','outputs'}:
        return ['生成校验含未适配执行配置，不忽略后声称失败终止／不重试保护。']
    if mode != 'workflow' or nested:
        return ['Sierra严格Schema校验首批仅支持Workflow根节点，不能复制到Chatflow或容器后仍声称原保护有效。']
    variables = cfg.get('variables')
    if not isinstance(variables, list) or len(variables) != 1 or not isinstance(variables[0], dict):
        return ['生成校验的对象输入绑定改变，请核对原步骤，不自动修正。']
    selector = variables[0].get('value_selector')
    source = nodes.get(selector[0]) if isinstance(selector, list) and len(selector) == 2 and isinstance(selector[0], str) else None
    if not source or source.get('type') != 'llm' or output_type(source.get('config', {})) != 'object':
        return ['生成校验须绑定当前明确启用的LLM结构化对象，原配置已失效。']
    expected_variables = [{'variable':'data','value_selector':[source['id'],'structured_output']}]
    expected_outputs = {'result':{'type':'object','children':None}}
    if variables != expected_variables or cfg.get('outputs') != expected_outputs or cfg.get('code_language') != 'python3':
        return ['生成校验的语言／输入／输出改变，未将其当作原Schema保护；请明确核对自定义代码。']
    if code != guard_code(source['config']['structured_output']['schema']):
        return ['原LLM Schema或生成校验代码已改变，不能沿用旧保护；请先预览更新原模板；手改代码须明确核对保留，或明确改为自定义代码（删除生成标记）。']
    outgoing = [e for e in edges if isinstance(e, dict) and e.get('source') == source['id']]
    incoming = [e for e in edges if isinstance(e, dict) and e.get('target') == node['id']]
    if len(outgoing) != 1 or outgoing[0].get('target') != node['id'] or len(incoming) != 1 or incoming[0].get('source') != source['id']:
        return ['生成校验的唯一前置连接改变或存在绕过路径，不能当作原Schema保护；未自动删除或改写连接。']
    return []


def validate_native(data):
    code = data.get('code')
    if not isinstance(code, str) or not code.startswith(MARKER): return []
    allowed = {'type','title','desc','selected','code_language','code','variables','outputs',
               'isInIteration','isInLoop','iteration_id','loop_id','version','retry_config','error_strategy','default_value'}
    if set(data) - allowed or data.get('version', '1') != '1':
        return ['实际生成校验含未适配字段或版本，不能沿用原保护。']
    if data.get('error_strategy') is not None or data.get('default_value') not in (None, []):
        return ['实际生成校验配置了错误分支／默认值，不能当作非法对象终止整次运行。']
    retry = data.get('retry_config')
    if retry is not None:
        if not isinstance(retry, dict) or retry.get('retry_enabled') is not False or set(retry)-{'retry_enabled','max_retries','retry_interval'}:
            return ['实际生成校验启用或不明确的重试／未知设置，未将其当作不重试保护。']
        if any(type(retry[k]) is not int or retry[k] < 0 for k in ('max_retries','retry_interval') if k in retry):
            return ['实际生成校验的禁用重试参数结构无效，未忽略。']
    return []


def candidate(task, plan, node_id):
    if task['app_type'] != 'workflow':
        raise ValueError('严格Schema校验插入首批只适配Workflow。Chatflow实时回答可能先于后续代码发出，不能将此步骤当作流式内容保护；不更换应用类型。')
    from .workflow_plan import validate_plan
    checked = validate_plan(task, plan)
    if not checked['valid']: raise ValueError('先修正当前流程草稿：'+'；'.join(checked['errors']))
    selected = [n for n in plan['nodes'] if n['id'] == node_id]
    if len(selected) != 1 or selected[0]['type'] != 'llm':
        raise ValueError('请选择当前Workflow根大模型节点；容器内校验插入尚未适配，不猜跨容器连接。')
    node = selected[0]
    if output_type(node['config']) != 'object':
        raise ValueError('该节点须明确开启且通过结构化对象Schema检查，不能校验text或未开启的对象。')
    # A second explicit insertion is rejected rather than silently multiplying work.
    if any(n.get('type') == 'code' and isinstance(n.get('config'), dict) and n['config'].get('variables') == [{'variable':'data','value_selector':[node_id,'structured_output']}] and n['config'].get('code','').startswith(MARKER) for n in plan['nodes']):
        raise ValueError('当前草稿已有此节点的Sierra严格校验步骤；可选择更新现有校验方案；不重复插入或覆盖手工代码。')
    result = copy.deepcopy(plan)
    from .iteration import plan_nodes
    identities = {n['id'] for n in plan_nodes(plan)}
    for index in range(1, 101):
        guard_id = node_id + '__schema_check' + ('' if index == 1 else str(index))
        if guard_id not in identities: break
    else: raise ValueError('无法分配独立校验节点ID，未覆盖现有节点。')
    outgoing = [e for e in result['edges'] if e['source'] == node_id]
    if not outgoing: raise ValueError('选中节点没有后继连接，未插入无效校验。')
    schema = native(node['config'])['structured_output']['schema']
    code = guard_code(schema)
    guard = {'id':guard_id,'type':'code','title':'严格校验结构化对象','config':{
        'code_language':'python3','code':code,
        'variables':[{'variable':'data','value_selector':[node_id,'structured_output']}],
        'outputs':{'result':{'type':'object','children':None}},
    }}
    position = next(i for i, n in enumerate(result['nodes']) if n['id'] == node_id)
    result['nodes'].insert(position+1, guard)
    for edge in outgoing: edge['source'] = guard_id
    result['edges'].append({'source':node_id,'target':guard_id})
    checked = validate_plan(task, result)
    if not checked['valid']: raise ValueError('插入后的草稿未通过静态检查，未采用：'+'；'.join(checked['errors']))
    return {'plan':result,'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),
            'node_id':node_id,'guard_node_id':guard_id,'schema_sha256':digest(schema),
            'changed_edges':len(outgoing),'added_nodes':1,'verification':'draft_code_static_only',
            'platform_checked':False,'business_verified':False,
            'failure_behavior':'fail_workflow_no_defaults_no_retry',
            'note':'仅生成本机草稿方案：在此根LLM所有后继前插入纯代码Schema检查；不转换值，不补默认，不重试。非法对象抛出错误，使整次Workflow失败；原有下游引用和其它节点保持，不替换手工代码。'+NOTE+' 生成后更改原LLM Schema会使此生成校验步骤失效，须核对并显式重新生成，不自动覆盖。尚未执行代码、模型、Dify或沙箱；用户采纳到草稿后仍须保存、重新确认和试跑。'}


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, Field
from uuid import UUID
from typing import Literal
from .plan_drafts import DraftRoute


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    plan: dict
    node_id: str = Field(min_length=1, max_length=256)
    acknowledge_fail_workflow: StrictBool
    request_nonce: UUID
    operation: Literal['insert','refresh'] = 'insert'


class StructuredGuard:
    def __init__(self, host): self.h = host
    def register(self):
        h = self.h
        router = APIRouter(route_class=DraftRoute)

        @router.post('/api/tasks/{item_id}/structured-output-guard')
        def prepare(item_id: str, payload: Preview):
            if not payload.acknowledge_fail_workflow:
                raise HTTPException(422, '须明确选择非法对象使整次Workflow失败、不补默认且不自动重试，再生成校验方案。')
            with h.store.lock:
                task = h.get_task(item_id)
                h.require_revision(task, payload.revision)
                try:
                    content = json.dumps(payload.plan, ensure_ascii=False, allow_nan=False).encode('utf-8')
                    if len(content) > 2000000: raise ValueError('流程草稿超过2MB，不截断后插入。')
                    result = (candidate if payload.operation == 'insert' else refresh_candidate)(task, payload.plan, payload.node_id)
                except (TypeError, RecursionError, UnicodeError):
                    raise HTTPException(422, '流程草稿结构或编码不受支持，原稿保持。') from None
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from None
                return {**result, 'operation':payload.operation, 'updated_nodes':result.get('updated_nodes',0), 'task_id':item_id, 'revision':payload.revision, 'request_nonce':str(payload.request_nonce)}

        h.app.include_router(router)


def refresh_candidate(task, plan, node_id):
    """Replace only an untouched v1 recipe, preserving guard ID and connections."""
    import ast
    from .workflow_plan import validate_plan
    if task['app_type'] != 'workflow':
        raise ValueError('更新生成校验首批只适配Workflow根LLM，不改变应用类型。')
    if not isinstance(plan, dict) or not isinstance(plan.get('nodes'), list) or not isinstance(plan.get('edges'), list):
        raise ValueError('当前草稿节点与连接须为数组，未修改原稿。')
    if any(not isinstance(n, dict) or not isinstance(n.get('config', {}), dict) for n in plan['nodes']) or any(not isinstance(e, dict) for e in plan['edges']):
        raise ValueError('当前草稿节点／连接结构无效，不猜更新位置。')
    identities = [n.get('id') for n in plan['nodes']]
    if any(not isinstance(i, str) for i in identities) or len(set(identities)) != len(identities):
        raise ValueError('当前草稿根节点ID须完整唯一，不猜更新目标。')
    selected = [n for n in plan['nodes'] if n['id'] == node_id and n.get('type') == 'llm']
    if len(selected) != 1 or output_type(selected[0].get('config', {})) != 'object':
        raise ValueError('请选择当前明确启用合法Schema的根LLM，未修改其它节点。')
    source = selected[0]
    expected_variables = [{'variable':'data','value_selector':[node_id,'structured_output']}]
    candidates = [n for n in plan['nodes'] if n.get('type') == 'code' and n.get('config', {}).get('variables') == expected_variables and isinstance(n.get('config', {}).get('code'), str) and n['config']['code'].startswith(MARKER)]
    if len(candidates) != 1:
        raise ValueError('须有且只有一个绑定此LLM的v1生成校验，未选择其它代码或多个目标。')
    guard = candidates[0]
    try:
        tree = ast.parse(guard['config']['code'])
        assignments = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == '_SCHEMA']
        if len(assignments) != 1: raise ValueError()
        old_schema = ast.literal_eval(assignments[0].value)
        if guard['config']['code'] != guard_code(old_schema): raise ValueError()
    except (SyntaxError, ValueError, TypeError, RecursionError):
        raise ValueError('旧校验代码已手工修改或不再是原v1模板，未覆盖；请保留并明确审查自定义代码。') from None
    # Validate the original recipe against its original schema, never execute it.
    historical = copy.deepcopy(source)
    historical['config']['structured_output'] = {'schema':old_schema}
    nodes = {n['id']:n for n in plan['nodes']}
    nodes[node_id] = historical
    errors = validate_generated(guard, nodes, plan['edges'], mode='workflow')
    if errors: raise ValueError('旧生成校验的绑定或代码已改变，未覆盖：'+'；'.join(errors))
    current_schema = source['config']['structured_output']['schema']
    if digest(current_schema) == digest(old_schema):
        raise ValueError('当前Schema未改变，无需更新生成校验，未产生重复修改。')
    result = copy.deepcopy(plan)
    target = next(n for n in result['nodes'] if n['id'] == guard['id'])
    target['config']['code'] = guard_code(current_schema)
    checked = validate_plan(task, result)
    if not checked['valid']:
        raise ValueError('更新后的草稿仍有其它静态问题，未采用：'+'；'.join(checked['errors']))
    return {'plan':result,'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),
            'node_id':node_id,'guard_node_id':guard['id'],'schema_sha256':digest(current_schema),
            'previous_schema_sha256':digest(old_schema),'changed_edges':0,'added_nodes':0,'updated_nodes':1,
            'verification':'draft_code_static_only','platform_checked':False,'business_verified':False,
            'failure_behavior':'fail_workflow_no_defaults_no_retry',
            'note':'仅更新当前Schema对应的原v1生成检查代码；旧模板及原绑定已静态核对，保留校验节点ID、标题、所有连接、提示词及其它节点。没有覆盖手工改过的代码，不转换值、不补默认、不重试。非法对象仍使整次Workflow失败。尚未执行代码、模型、Dify或沙箱；采纳草稿后仍须保存、重新确认和试跑。'+NOTE}
