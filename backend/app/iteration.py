"""Bounded sequential/parallel iteration with explicit independent-item declaration."""
from __future__ import annotations

import copy
import re
from .body_http import FIELDS as HTTP_BODY_FIELDS
from .retrieval_settings import FIELDS as RETRIEVAL_BODY_FIELDS

BODY_TYPES = {"code", "template-transform", "llm", "list-operator", "http-request", "knowledge-retrieval", "document-extractor"}
BODY_GRAPH_TYPES = BODY_TYPES | {'if-else','variable-aggregator','question-classifier','parameter-extractor'}
ARRAY_TYPES = {"array[string]", "array[number]", "array[object]", "array[file]"}
MAX_BODY_NODES = 12


def plan_nodes(plan: dict):
    """The supported IR has at most one container level; never recurse blindly."""
    for node in plan.get("nodes", []):
        if not isinstance(node, dict):
            continue
        yield node
        if node.get("type") in ("iteration","loop") and isinstance(node.get("config"), dict):
            children = node["config"].get("nodes", [])
            if isinstance(children, list):
                yield from (child for child in children if isinstance(child, dict))


def output_type(nodes: dict, selector) -> str | None:
    if not isinstance(selector, list) or len(selector) != 2 or not all(isinstance(x, str) for x in selector):
        return None
    node = nodes.get(selector[0], {})
    kind, cfg, name = node.get("type"), node.get("config", {}), selector[1]
    if not isinstance(cfg, dict):
        return None
    if kind == "code":
        schema = cfg.get("outputs", {})
        value = schema.get(name) if isinstance(schema, dict) else None
        return value.get("type") if isinstance(value, dict) else None
    if (kind == "llm" and name == "text") or (kind == "template-transform" and name == "output"):
        return "string"
    if kind == 'llm' and name == 'structured_output':
        from .structured_output import output_type as structured_type
        return structured_type(cfg)
    if kind == "iteration" and name == "output":
        return cfg.get("output_type")
    if kind=='loop':
        from .loop import output_type as loop_output_type
        return loop_output_type(cfg,name)
    if kind == 'variable-aggregator' and name == 'output':
        return cfg.get('output_type')
    if kind == 'list-operator' and name == 'result':
        return cfg.get('input_type')
    if kind == 'question-classifier':
        return {'class_id':'string','class_name':'string','class_label':'string','usage':'object'}.get(name)
    if kind == 'parameter-extractor':
        from .parameter_extractor import output_types
        return output_types(cfg).get(name)
    if kind == 'document-extractor' and name == 'text':return 'string' if cfg.get('input_type')=='file' else 'array[string]' if cfg.get('input_type')=='array[file]' else None
    if kind == 'http-request':return {'body':'string','status_code':'number','headers':'object','files':'array[file]'}.get(name)
    if kind == "start":
        from .start_inputs import declared_type
        return declared_type(cfg.get('variables'), name)
    return None


def validate_container_ids(plan: dict) -> list[str]:
    errors, seen = [], set()
    for node in plan_nodes(plan):
        nid = node.get("id")
        if not isinstance(nid, str) or not nid or not re.fullmatch(r"[\w-]+", nid):
            errors.append("含迭代的计划中，所有节点 ID 必须仅含字母、数字、下划线或连字符")
            continue
        if nid in seen:
            errors.append(f"迭代内外节点 ID 必须全局唯一：{nid}")
        seen.add(nid)
    for node in plan.get("nodes", []):
        if isinstance(node, dict) and node.get("type") in ("iteration","loop") and isinstance(node.get("id"), str):
            from .loop import SUFFIXES
            for suffix in (("__iteration_start", "__scope_input", "__scope_end") if node['type']=='iteration' else SUFFIXES):
                if node["id"] + suffix in seen:
                    errors.append(f"节点 ID 占用了迭代保留名称：{node['id'] + suffix}")
    return errors


def validate_iteration(task, node, outer, outputs, dominators, check_ref,conversation_types=None):
    """Project the ordered body into a temporary DAG solely for validation.

    Native selectors/code remain unchanged. External bindings are made available
    only if their source dominates the container; item/index are body-local.
    """
    from .workflow_plan import validate_plan, _placeholder_refs
    conversation_types=conversation_types or {}
    cfg, nid = node["config"], node["id"]
    errors, warnings = [], []
    allowed = {"nodes", "edges", "entry_node_id", "iterator_selector", "iterator_input_type", "output_selector", "output_type", "is_parallel", "parallel_nums", "parallel_safe", "parallel_reason", "error_handle_mode", "flatten_output"}
    if set(cfg) - allowed:
        errors.append(f"迭代 {nid} 存在未适配配置：{', '.join(sorted(set(cfg) - allowed))}")
    parallel = cfg.get('is_parallel')
    if type(parallel) is not bool:
        errors.append(f'迭代 {nid} 须明确 is_parallel=true／false，不能猜测执行方式')
    if parallel is True:
        count = cfg.get('parallel_nums')
        if type(count) is not int or not 2 <= count <= 10:
            errors.append(f'迭代 {nid} 并发数 parallel_nums 须明确为 2—10 的整数')
        if cfg.get('parallel_safe') is not True or not isinstance(cfg.get('parallel_reason'), str) or not 0 < len(cfg['parallel_reason'].strip()) <= 2000:
            errors.append(f'迭代 {nid} 并行处理须声明 parallel_safe=true 并填写 parallel_reason，说明逐项独立、无顺序依赖及副作用条件；不是执行验证')
        warnings.append(f'迭代 {nid} 拟议并行处理，输出按输入索引汇总；逐项独立性只是已声明条件。失败后已派发项可能仍在执行，不保证即时取消；整批失败不计部分成功。并发增加速率限制与同时计费风险，Dify 执行费用未计入助手预算。')
    elif parallel is False:
        if 'parallel_nums' in cfg and (type(cfg['parallel_nums']) is not int or cfg['parallel_nums'] != 1):
            errors.append(f'迭代 {nid} 顺序处理只能指定 parallel_nums=1，不能静默忽略其他并发数')
        if 'parallel_safe' in cfg or 'parallel_reason' in cfg:
            errors.append(f'迭代 {nid} 顺序处理不能携带未生效的并行声明，请明确移除后复核')
    if cfg.get("error_handle_mode") != "terminated":
        errors.append(f"迭代 {nid} 须明确 error_handle_mode=terminated；任何一项失败即停止整批，继续或跳过失败尚未适配")
    if cfg.get("flatten_output") is not False:
        errors.append(f"迭代 {nid} 须明确 flatten_output=false，不自动展开或丢弃逐项结果")
    check_ref(nid, cfg.get("iterator_selector"), "iterator_selector")
    input_type = cfg.get("iterator_input_type")
    if not isinstance(input_type, str) or input_type not in ARRAY_TYPES:
        errors.append(f"迭代 {nid}.iterator_input_type 只支持 array[string]／array[number]／array[object]／根Workflow明确文件列表／原生HTTP.files的array[file]")
    elif output_type(outer, cfg.get("iterator_selector")) != input_type:
        errors.append(f"迭代 {nid} 输入数组类型与上游声明不一致或未知；请用代码节点明确输出类型")
    file_iterator=False
    if input_type=='array[file]':
        selector=cfg.get('iterator_selector');source=outer.get(selector[0],{}) if isinstance(selector,list) and len(selector)==2 and isinstance(selector[0],str) else {}
        from .file_inputs import root_source
        file_iterator=(source.get('type')=='http-request' and selector[1]=='files') or root_source(source,selector,'file-list')
        if not file_iterator:errors.append(f'文件迭代 {nid} 须明确全路径上游原生HTTP.files或已核对根Workflow文件列表，不接受代码伪造文件、未知或跨容器来源。')
    children = cfg.get("nodes")
    if not isinstance(children, list) or not 1 <= len(children) <= MAX_BODY_NODES:
        return errors + [f"迭代 {nid}.nodes 必须包含 1—{MAX_BODY_NODES} 个按执行顺序排列的节点"], warnings
    graph_body = 'edges' in cfg or 'entry_node_id' in cfg
    types = BODY_GRAPH_TYPES if graph_body else BODY_TYPES
    if any(not isinstance(child, dict) or not isinstance(child.get("id"), str) or not isinstance(child.get("type"), str) or child.get("type") not in types or not isinstance(child.get("config", {}), dict) for child in children):
        return errors + [f"迭代 {nid} 顺序体支持代码／模板／LLM／标量数组处理／知识检索／本容器HTTP文件文档提取／已声明GET或HEAD读取；内部DAG可增加条件／文字分类／文字参数提取／无分组聚合，须完整声明 edges 和 entry_node_id。不支持嵌套迭代、循环或其他节点"], warnings
    inner = {child["id"]: child for child in children}
    body_edges = cfg.get('edges')
    entry = cfg.get('entry_node_id')
    if graph_body:
        if not isinstance(entry,str) or entry not in inner or not isinstance(body_edges,list) or not 1<=len(body_edges)<=48:
            return errors+[f'迭代 {nid} 内部 DAG 须明确实际 entry_node_id 和 1—48 条 edges'],warnings
        if any(not isinstance(edge,dict) or set(edge)-{'source','target','source_handle'} or not isinstance(edge.get('source'),str) or not isinstance(edge.get('target'),str) or edge['source'] not in inner or edge['target'] not in inner or not isinstance(edge.get('source_handle','source'),str) for edge in body_edges):
            return errors+[f'迭代 {nid} 内部连接须仅引用本容器处理节点，使用 source／target／source_handle；不能跨越作用域或引用保留开始节点'],warnings
        seen=set()
        for edge in body_edges:
            key=(edge['source'],edge['target'],edge.get('source_handle','source'))
            if key in seen:errors.append(f'迭代 {nid} 内部连接重复，不能静默合并')
            seen.add(key)
            if inner[edge['source']]['type'] not in {'if-else','question-classifier'} and key[2]!='source':errors.append(f'迭代 {nid} 普通内部节点只允许 source 出口')
        if any(edge['target']==entry for edge in body_edges):errors.append(f'迭代 {nid} entry_node_id 必须是无内部入边的入口')
    else:
        entry=children[0]['id']
        body_edges=[{'source':a['id'],'target':b['id']} for a,b in zip(children,children[1:])]
    fields = {"code": {"code_language", "code", "variables", "outputs"}, "template-transform": {"template", "variables"}, "llm": {"system_prompt", "user_prompt", "context_variable_selector", "model", "structured_output_enabled", "structured_output"},'if-else':{'cases'},'variable-aggregator':{'variables','output_type','selection_mode'},'question-classifier':{'classes','query_variable_selector','instruction','model','unmatched_policy'},'list-operator':{'variable','input_type','filter_by','order_by','extract_by','limit'},'parameter-extractor':{'query','parameters','instruction','reasoning_mode','model','failure_policy'},'http-request':HTTP_BODY_FIELDS,'knowledge-retrieval':RETRIEVAL_BODY_FIELDS,'document-extractor':{'variable_selector','input_type','empty_policy'}}
    for child in children:
        if child['type']=='knowledge-retrieval' and not isinstance(child['config'].get('query_variable_selector'),list):
            errors.append(f"迭代 {nid} 内知识检索 {child['id']} 须明确本项的文字 query_variable_selector，不继承应用默认问题。")
        if child['type']=='http-request':
            from .body_http import validate as validate_read,NOTE as READ_NOTE
            errors.extend(f"迭代 {nid} 内HTTP {child['id']}：{message}" for message in validate_read(child['config']))
            warnings.append(READ_NOTE)
        extra = set(child.get("config", {})) - fields[child["type"]]
        if extra:
            errors.append(f"迭代 {nid} 内节点 {child['id']} 存在未适配配置：{', '.join(sorted(extra))}")
        if child['type']=='variable-aggregator':
            candidates=child['config'].get('variables')
            if isinstance(candidates,list) and any(not isinstance(selector,list) or len(selector)!=2 or not isinstance(selector[0],str) or selector[0] not in inner for selector in candidates):
                errors.append(f'迭代 {nid} 内聚合只允许内部处理节点的声明输出；item／index 或外部值请先用代码／模板显式转换，不把作用域占位值当作已验证类型')
    selected_type = output_type(inner, cfg.get("output_selector"))
    scalar_types = {"string", "number", "object"}
    selection = cfg.get("output_selector")
    selected_id = selection[0] if isinstance(selection,list) and len(selection)==2 and isinstance(selection[0],str) else None
    if selected_id not in inner or (not graph_body and selected_id!=children[-1]['id']) or any(edge['source']==selected_id for edge in body_edges) or not isinstance(selected_type, str) or selected_type not in scalar_types:
        errors.append(f"迭代 {nid}.output_selector 必须选择无内部出边的共同终点 string／number／object 输出；顺序体仍须为最后节点")
    elif cfg.get("output_type") != f"array[{selected_type}]":
        errors.append(f"迭代 {nid}.output_type 必须为 array[{selected_type}]，与逐项输出一致")

    synthetic = nid + "__scope_input"
    bindings = {(nid, "item"), (nid, "index")}
    for source in dominators.get(nid, set()) - {nid}:
        bindings.update((source, variable) for variable in outputs.get(source, set()))
    if task.get("app_type") == "advanced-chat":
        bindings.add(("sys", "query"))
        bindings.update(("conversation",name) for name in conversation_types)
    mapped = {binding: f"scope_{i}" for i, binding in enumerate(sorted(bindings))}
    from .declared_types import resolve as resolve_declaration
    scope_types={(synthetic,label):('string' if pair==('sys','query') else conversation_types.get(pair[1]) if pair[0]=='conversation' else input_type[6:-1] if pair==(nid,'item') and isinstance(input_type,str) else 'number' if pair==(nid,'index') else resolve_declaration(outer,list(pair),mode=task.get('app_type'))) for pair,label in mapped.items()}

    def remap(selector):
        if isinstance(selector, list) and len(selector) == 2 and all(isinstance(x, str) for x in selector):
            key = tuple(selector)
            if key in mapped:
                if outer.get(selector[0],{}).get('type')=='parameter-extractor' and selector[1] not in {'__is_success','__reason','__usage'}:
                    check_ref(nid,selector,'正文外部提取参数')
                return [synthetic, mapped[key]]
        return selector

    projected = copy.deepcopy(children)
    for child in projected:
        config = child.setdefault("config", {})
        for variable in config.get("variables", []) if isinstance(config.get("variables", []), list) else []:
            if isinstance(variable, dict):
                variable["value_selector"] = remap(variable.get("value_selector"))
                # Dify requires the real type on template variable bindings.
                if child["type"] == "template-transform":
                    original = next((v.get("value_selector") for v in inner[child["id"]].get("config", {}).get("variables", []) if isinstance(v, dict) and v.get("variable") == variable.get("variable")), None)
                    actual = "number" if original == [nid, "index"] else input_type[6:-1] if original == [nid, "item"] and isinstance(input_type, str) else conversation_types.get(original[1]) if isinstance(original,list) and len(original)==2 and original[0]=='conversation' and isinstance(original[1],str) else output_type({**outer, **inner}, original)
                    if actual is not None and variable.get("value_type", "string") != actual:
                        errors.append(f"迭代 {nid} 内模板 {child['id']} 的 value_type 与引用类型不一致，应为 {actual}")
        if config.get("context_variable_selector") is not None:
            config["context_variable_selector"] = remap(config["context_variable_selector"])
        if child['type'] in {'question-classifier','knowledge-retrieval'}:config['query_variable_selector']=remap(config.get('query_variable_selector'))
        if child['type']=='document-extractor':config['variable_selector']=remap(config.get('variable_selector'))
        if child['type']=='list-operator':config['variable']=remap(config.get('variable'))
        if child['type']=='parameter-extractor':config['query']=remap(config.get('query'))
        if child['type']=='http-request':
            from .body_http import remap_templates,KEY
            remap_templates(config,remap)
            config.pop(KEY,None)
        if child['type']=='if-else':
            for case in config.get('cases',[]) if isinstance(config.get('cases'),list) else []:
                if isinstance(case,dict):
                    for condition in case.get('conditions',[]) if isinstance(case.get('conditions'),list) else []:
                        if isinstance(condition,dict):
                            condition['variable_selector']=remap(condition.get('variable_selector'))
                            from .condition_settings import remap_value
                            if 'value' in condition:condition['value']=remap_value(condition['value'],remap)
        for field in ("system_prompt", "user_prompt", "template"):
            text = config.get(field)
            if isinstance(text, str):
                for src, var in _placeholder_refs(text):
                    if (src, var) in mapped:
                        remap([src,var])
                        text = text.replace("{{#" + src + "." + var + "#}}", "{{#" + synthetic + "." + mapped[(src, var)] + "#}}")
                config[field] = text
    temporary_nodes = [{"id": synthetic, "type": "start", "config": {"variables": [{"variable": name, "type": "paragraph"} for name in mapped.values()]}}] + projected
    end_id = nid + "__scope_end"
    temporary_nodes.append({"id": end_id, "type": "end", "config": {"outputs": [{"variable": "result", "value_selector": selection}]}})
    temporary_edges=[{'source':synthetic,'target':entry}]+copy.deepcopy(body_edges)+[{'source':selected_id,'target':end_id}]
    result = validate_plan({**task, "app_type": "workflow", "configuration": {**task.get("configuration", {}), "conversation_memory": False}}, {"schema_version": 1, "nodes": temporary_nodes, "edges": temporary_edges},_scope_types=scope_types,_scope_file_items={(synthetic,mapped[(nid,'item')])} if file_iterator else None)
    errors.extend(f"迭代 {nid} 内：{error}" for error in result["errors"])
    warnings.extend(f"迭代 {nid} 内：{warning}" for warning in result["warnings"] if "静态校验不等于" not in warning)
    warnings.append(f"迭代 {nid} 每项按{'内部 DAG 条件与连接' if graph_body else '顺序体'}处理，按输入索引保留顺序与重复项；任一项异常则整批失败，不承诺恢复到中间项。含模型的批量费用尚无全任务硬上限。")
    if graph_body:warnings.append(f'迭代 {nid} 内部分支必须汇入一个共同输出终点；各分支无命中／默认行为仍须确认并分别试跑。模型按实际被执行的内部节点调用，不应按每项一次估算。已适配单层正文可保留手改，并行须明确当前文件独立性；嵌套保留未适配。')
    if any(child["type"] == "llm" for child in children):
        warnings.append(f"迭代 {nid} 内部 LLM 逐项调用节点独立模型或继承任务模型，不读取 Chatflow 历史；所需上下文须在提示词中明确引用。")
    return errors, warnings


def native_iteration(internal: dict, x: int, native_node):
    nid, cfg = internal["id"], internal["config"]
    start_id = nid + "__iteration_start"
    children=cfg['nodes'];by_id={n['id']:n for n in children}
    body_edges=cfg.get('edges') if 'edges' in cfg else [{'source':a['id'],'target':b['id']} for a,b in zip(children,children[1:])]
    entry=cfg.get('entry_node_id',children[0]['id'])
    predecessors={key:set() for key in by_id};successors={key:set() for key in by_id}
    for edge in body_edges:predecessors[edge['target']].add(edge['source']);successors[edge['source']].add(edge['target'])
    ranks={key:0 for key in by_id};degree={key:len(preds) for key,preds in predecessors.items()};queue=[entry]
    for current in queue:
        for target in sorted(successors[current]):
            ranks[target]=max(ranks[target],ranks[current]+1);degree[target]-=1
            if degree[target]==0:queue.append(target)
    rows={};positions={}
    for child in children:
        rank=ranks[child['id']];row=rows.get(rank,0);rows[rank]=row+1;positions[child['id']]={'x':128+300*rank,'y':68+160*row}
    width=150+300*(max(ranks.values())+1)
    height=max(220+160*(max(rows.values())-1),300 if any(n['type']=='if-else' for n in children) else 220)
    parent = native_node(internal, x)
    parent.update(width=width, height=height, zIndex=1)
    parent["data"].update(start_node_id=start_id, iterator_selector=cfg["iterator_selector"], iterator_input_type=cfg["iterator_input_type"], output_selector=cfg["output_selector"], output_type=cfg["output_type"], is_parallel=cfg['is_parallel'], parallel_nums=cfg['parallel_nums'] if cfg['is_parallel'] else 1, error_handle_mode="terminated", flatten_output=False, width=width, height=height)
    start = {"id": start_id, "data": {"type": "iteration-start", "title": "", "desc": "", "selected": False, "isInIteration": True}, "parentId": nid, "type": "custom-iteration-start", "position": {"x": 24, "y": 68}, "positionAbsolute": {"x": x + 24, "y": 350}, "width": 44, "height": 48, "zIndex": 1002, "draggable": False, "selectable": False, "sourcePosition": "right", "targetPosition": "left"}
    nodes, edges = [parent, start], []
    for child in children:
        emitted = native_node({**internal, **child, "config": child.get("config", {})}, x)
        position=positions[child['id']]
        emitted.update(parentId=nid, zIndex=1002, position=position, positionAbsolute={"x":x+position['x'],"y":282+position['y']})
        emitted["data"].update(isInIteration=True, isInLoop=False, iteration_id=nid)
        # Chatflow history is deliberately not read once per item.
        emitted["data"].pop("memory", None)
        nodes.append(emitted)
    for edge in [{'source':start_id,'target':entry}]+body_edges:
        source,target,handle=edge['source'],edge['target'],edge.get('source_handle','source')
        edges.append({'id':f'{source}-{handle}-{target}','source':source,'sourceHandle':handle,'target':target,'targetHandle':'target','type':'custom','zIndex':1002,
                      'data':{'isInIteration':True,'isInLoop':False,'iteration_id':nid,'sourceType':'iteration-start' if source==start_id else by_id[source]['type'],'targetType':by_id[target]['type']}})
    return nodes, edges, width
