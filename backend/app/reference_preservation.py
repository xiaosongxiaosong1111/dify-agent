"""Deterministic material-level reference preservation; local static checks only.

Preserve keeps the complete configuration of explicitly selected root
code／template-transform nodes without locking connections. Replicate compares
the whole compiler-expressible Workflow／Chatflow core. No execution, platform
call or semantic inference happens here.
"""
import json

from .dsl_roundtrip import digest, parse
from .material_sources import read_source

MAX_NODE_IDS = 250
CONTEXT_MAX_BYTES = 24000
PRESERVE_NODE_TYPES = {'code', 'template-transform'}
STRICT_NODE_TYPES = {'start', 'code', 'template-transform', 'llm', 'knowledge-retrieval', 'if-else',
                     'question-classifier', 'parameter-extractor', 'list-operator', 'variable-aggregator',
                     'document-extractor', 'end', 'answer'}
STRICT_APP_TYPES = {'workflow', 'advanced-chat'}
KNOWN_WORKFLOW_KEYS = {'graph', 'features', 'environment_variables', 'conversation_variables', 'rag_pipeline_variables'}


class PolicyError(ValueError):
    """The declared reference policy cannot be met without guessing."""


def node_selection(value):
    if not isinstance(value, list) or len(value) > MAX_NODE_IDS:
        raise PolicyError('保留节点选择须为最多250个节点的数组。')
    result = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise PolicyError('保留节点选择须为非空字符串ID，不接受其它类型或空值。')
        if item in result:
            raise PolicyError('保留节点选择不能重复；请逐项核对节点ID。')
        result.append(item)
    return result


def root_nodes(root):
    workflow = root.get('workflow')
    graph = workflow.get('graph') if isinstance(workflow, dict) else None
    nodes = graph.get('nodes') if isinstance(graph, dict) else None
    if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_NODE_IDS:
        raise PolicyError('参考流程须包含1—250个根节点；未读取到可核对的完整流程。')
    result = []
    seen = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('id'), str) or not node['id'] or node['id'] in seen:
            raise PolicyError('参考节点ID缺失或重复，不能核对保留。')
        seen.add(node['id'])
        result.append(node)
    return result


def selectable_ids(root):
    return [node['id'] for node in root_nodes(root)
            if node.get('parentId') is None
            and isinstance(node.get('data'), dict)
            and node['data'].get('type') in PRESERVE_NODE_TYPES]


def validate_selection(root, ids):
    ids = node_selection(ids)
    if not ids:
        return ids
    allowed = set(selectable_ids(root))
    if any(value not in allowed for value in ids):
        raise PolicyError('所选节点不存在或不是首批支持的根 code／模板转换节点，请在界面重新选择。')
    return ids


def node_snapshot(node):
    return {'id': node['id'], 'node_type': node.get('type'), 'config': node.get('data')}


def selected_snapshots(root, ids):
    by_id = {node['id']: node for node in root_nodes(root)}
    return [node_snapshot(by_id[value]) for value in ids]


def strict_source(root):
    nodes = root_nodes(root)
    workflow = root.get('workflow')
    graph = workflow.get('graph') if isinstance(workflow, dict) else None
    edges = graph.get('edges') if isinstance(graph, dict) else None
    if not isinstance(edges, list):
        raise PolicyError('参考流程连接结构不完整，不能严格复现。')
    ids = {node['id'] for node in nodes}
    if set(workflow) - KNOWN_WORKFLOW_KEYS:
        raise PolicyError('参考流程含尚未适配的关键字段，不能严格复现。')
    if any(node.get('parentId') is not None for node in nodes):
        raise PolicyError('参考图含容器子节点；首批严格复现仅支持无容器的根图。')
    for node in nodes:
        data = node.get('data')
        kind = data.get('type') if isinstance(data, dict) else None
        if not isinstance(kind, str) or kind not in STRICT_NODE_TYPES:
            raise PolicyError('参考节点类型尚未适配严格复现。')
    for edge in edges:
        if not isinstance(edge, dict) or edge.get('source') not in ids or edge.get('target') not in ids:
            raise PolicyError('参考连接引用缺失节点，不能严格复现。')
    try:
        from .workflow_publication import core as publication_core
        core_value = publication_core(workflow)
    except Exception:
        raise PolicyError('参考流程核心结构无法完整读取，不能严格复现。') from None
    dependencies = root.get('dependencies', [])
    if not isinstance(dependencies, list):
        raise PolicyError('参考依赖结构不完整，不能严格复现。')
    return {'core': core_value, 'dependencies': dependencies, 'digest': digest([core_value, dependencies])}


def read_material_root(host, task, material):
    raw = read_source(host, task['id'], material)
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise PolicyError('参考原文件编码无法完整核对，未继续保留核对。') from None
    try:
        return parse(text, task['app_type'])
    except ValueError as exc:
        raise PolicyError(str(exc)) from None


def validate_ids_for_material(host, task, material, ids):
    ids = node_selection(ids)
    if not ids:
        return ids
    if task.get('app_type') not in STRICT_APP_TYPES:
        raise PolicyError('保留节点选择目前仅适配 Workflow／Chatflow；其它应用类型不能选择节点。')
    if material.get('source_kind') != 'reference_dsl':
        raise PolicyError('保留节点选择只适用于已识别的参考 DSL 材料；普通材料不能选择节点。')
    if material.get('status') != 'parsed':
        raise PolicyError('材料尚未成功解析，不能在此时保存节点选择。')
    root = read_material_root(host, task, material)
    return validate_selection(root, ids)


def _name(material):
    value = material.get('name')
    return value if isinstance(value, str) and value else material.get('id', '材料')


def prepare(host, task):
    """Validate all declared reference policies before any provider or budget read."""
    materials = task.get('materials')
    materials = materials if isinstance(materials, list) else []
    active = [m for m in materials if isinstance(m, dict) and m.get('reference_mode') in {'preserve', 'replicate'}]
    if not active:
        return None
    if task.get('dsl_reference'):
        raise PolicyError('已确认的实际 DSL 保留流程与材料级保留／复现暂不支持同时使用；请先明确放弃其中一种，不由程序猜测。')
    if task.get('app_type') not in STRICT_APP_TYPES:
        raise PolicyError('参考保留目前仅适配 Workflow／Chatflow；当前应用类型不能据此规划或构建。')
    policies = []
    for material in active:
        if material.get('status') != 'parsed':
            raise PolicyError(f'材料“{_name(material)}”尚未成功解析，不能按参考策略规划或构建。')
        mode = material.get('reference_mode')
        if mode == 'preserve':
            if material.get('source_kind') != 'reference_dsl':
                raise PolicyError(f'材料“{_name(material)}”是保留指定部分，但不是已识别的参考 DSL；普通文字材料不能据此规划或构建，也不会自动改为借鉴。')
            ids = node_selection(material.get('preserve_node_ids') or [])
            if not ids:
                raise PolicyError(f'材料“{_name(material)}”是保留指定部分，但尚未明确选择要保留的根节点；不会自动改为借鉴，只能保存讨论，不能规划或构建。')
            root = read_material_root(host, task, material)
            validate_selection(root, ids)
            policies.append({'mode': 'preserve', 'material_id': material['id'], 'name': _name(material),
                             'source_sha256': material.get('sha256'), 'node_ids': ids,
                             'nodes': selected_snapshots(root, ids)})
        else:
            if material.get('source_kind') != 'reference_dsl':
                raise PolicyError(f'材料“{_name(material)}”不是已识别的参考 DSL；严格复现不能把普通说明当作完整流程核心，也不会自动改为借鉴。')
            root = read_material_root(host, task, material)
            policies.append({'mode': 'replicate', 'material_id': material['id'], 'name': _name(material),
                             'source_sha256': material.get('sha256'), 'strict': strict_source(root)})
    return {'materials': policies}


def material_context(item):
    if item['mode'] == 'preserve':
        return {'material_id': item['material_id'], 'mode': 'preserve', 'source_sha256': item['source_sha256'],
                'node_ids': item['node_ids'], 'selected_nodes': item['nodes']}
    return {'material_id': item['material_id'], 'mode': 'replicate', 'source_sha256': item['source_sha256'],
            'core': item['strict']['core'], 'dependencies': item['strict']['dependencies'],
            'core_sha256': item['strict']['digest']}


def model_context(policy):
    if policy is None:
        return None
    value = {'verification': 'local_static_policy_only', 'source_files_rechecked': True,
             'business_verified': False, 'platform_verified': False,
             'note': '仅本机静态读取与比对；不能凭摘要猜测缺失字段，资源可用性、真实导入与运行均未验证。',
             'materials': [material_context(item) for item in policy['materials']]}
    try:
        size = len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise PolicyError('参考保留上下文编码无法核对，未自动规划。') from None
    if size > CONTEXT_MAX_BYTES:
        raise PolicyError('参考保留上下文超过24000字节，拒绝自动规划；可手工保存完整流程计划后由本机静态核对，不截断冒充完整。')
    return value


def _compare(item, root):
    if item['mode'] == 'preserve':
        by_id = {node['id']: node for node in root_nodes(root)}
        mismatched = []
        for snapshot in item['nodes']:
            node = by_id.get(snapshot['id'])
            if node is None or node.get('parentId') is not None or digest(node_snapshot(node)) != digest(snapshot):
                mismatched.append(snapshot['id'])
        if mismatched:
            raise PolicyError('选中节点未按原始完整配置保留为根节点：' + '、'.join(mismatched) + '。')
        return {'mode': 'preserve', 'material_id': item['material_id'], 'source_sha256': item['source_sha256'],
                'node_ids': item['node_ids'],
                'nodes': [{'id': snapshot['id'], 'sha256': digest(snapshot)} for snapshot in item['nodes']],
                'verification': 'local_static_node_config_only', 'complete_node_config': True,
                'connections_locked': False, 'business_verified': False, 'platform_verified': False}
    strict = strict_source(root)
    if strict['digest'] != item['strict']['digest']:
        raise PolicyError('当前流程核心与参考材料不一致（节点、连接、features、变量或依赖不同）。')
    return {'mode': 'replicate', 'material_id': item['material_id'], 'source_sha256': item['source_sha256'],
            'source_core_sha256': item['strict']['digest'], 'candidate_core_sha256': strict['digest'],
            'verification': 'local_static_core_equal', 'business_verified': False, 'platform_verified': False}


def _confirmation_eligible(task):
    active = [m for m in (task.get('materials') or []) if isinstance(m, dict) and m.get('reference_mode') in {'preserve', 'replicate'}]
    return task.get('app_type') in STRICT_APP_TYPES and all(
        material.get('status') == 'parsed' and material.get('source_kind') == 'reference_dsl' for material in active)


def configuration_check(host, task):
    """Confirmation refuses incomplete eligible policies; legacy ineligible
    materials keep their explicit planning/build rejection instead."""
    active = [m for m in (task.get('materials') or []) if isinstance(m, dict) and m.get('reference_mode') in {'preserve', 'replicate'}]
    if not active:
        return None
    if task.get('dsl_reference'):
        raise PolicyError('已确认的实际 DSL 保留流程与材料级保留／复现暂不支持同时使用；请先明确放弃其中一种，不由程序猜测。')
    if not _confirmation_eligible(task):
        return None
    policy = prepare(host, task)
    return check_plan(task, policy, task.get('workflow_plan'))


def check_plan(task, policy, plan, content=None):
    """Compile (when needed) and compare the final native content; never writes."""
    if policy is None:
        return None
    if task.get('app_type') not in STRICT_APP_TYPES:
        raise PolicyError('参考保留目前仅适配 Workflow／Chatflow。')
    if not isinstance(plan, dict) or not plan:
        raise PolicyError('参考保留策略要求先保存完整显式流程计划；不能用基础线性模板顶替。')
    if content is None:
        from .workflow_plan import compile_workflow_plan
        try:
            content, validation = compile_workflow_plan({**task, 'workflow_plan': plan})
        except ValueError as exc:
            raise PolicyError(str(exc)) from None
        if not validation.get('valid'):
            raise PolicyError('候选流程计划未通过静态编译，不能核对保留。')
    try:
        root = parse(content, task['app_type'])
    except ValueError as exc:
        raise PolicyError(str(exc)) from None
    return {'verification': 'local_static_only', 'business_verified': False, 'platform_verified': False,
            'materials': [_compare(item, root) for item in policy['materials']]}
