"""Typed first-available variable aggregation with conservative path coverage."""
from .iteration import output_type

TYPES={'string','number','boolean','object','array[string]','array[number]','array[object]'}


def variable_type(nodes, selector, mode):
    if selector==['sys','query'] and mode=='advanced-chat':return 'string'
    result=output_type(nodes,selector)
    if result is not None:return result
    source,name=selector
    kind=nodes[source]['type']
    if kind=='knowledge-retrieval' and name=='result':return 'array[object]'
    if kind=='http-request':return {'status_code':'number','body':'string','headers':'object'}.get(name)
    return None


def validate_aggregation(node, nodes, outputs, predecessors, start_id, mode):
    cfg,nid=node['config'],node['id'];errors=[];prefix=f'变量聚合 {nid}：'
    if set(cfg)!={'variables','output_type','selection_mode'}:
        return [prefix+'须明确 variables、output_type、selection_mode 三个字段；分组与其他配置尚未适配。'],[]
    if cfg['selection_mode']!='first_available':errors.append(prefix+'仅支持明确 selection_mode=first_available，按列表优先级取第一个存在的变量。')
    if not isinstance(cfg['output_type'],str) or cfg['output_type'] not in TYPES:errors.append(prefix+'输出类型须为明确支持的字符串／数值／布尔／对象或数组类型。')
    selectors=cfg['variables']
    if not isinstance(selectors,list) or not 1<=len(selectors)<=12:
        return errors+[prefix+'候选变量须有 1—12 项。'],[]
    ancestors=set();pending=list(predecessors.get(nid,[]))
    while pending:
        current=pending.pop()
        if current in ancestors:continue
        ancestors.add(current);pending.extend(predecessors.get(current,[]))
    producers=set();seen=set()
    for index,selector in enumerate(selectors):
        label=prefix+f'第 {index+1} 个候选'
        if not isinstance(selector,list) or len(selector)!=2 or any(not isinstance(v,str) or not v for v in selector):
            errors.append(label+'须为 [节点 ID, 输出变量]。');continue
        key=tuple(selector)
        if key in seen:errors.append(label+'与前面重复，不能隐式改变优先级。')
        seen.add(key);source,name=selector
        if source=='sys':
            if mode!='advanced-chat' or name!='query':errors.append(label+'只允许 Chatflow 的 sys.query。');continue
            producer=start_id
        else:
            if source not in nodes or source not in ancestors or source==nid:
                errors.append(label+'必须来自实际上游节点，不能来自自身、后续或无关分支。');continue
            if name not in outputs.get(source,set()):errors.append(label+'引用了不存在的输出变量。');continue
            producer=source
        actual=variable_type(nodes,selector,mode)
        if actual is None:errors.append(label+'的类型未知，请先用代码声明明确输出类型。')
        elif actual!=cfg['output_type']:errors.append(label+f'类型为 {actual}，与聚合输出 {cfg["output_type"]} 不一致；不做隐式转换。')
        producers.add(producer)
    # A path avoiding all candidate producers proves there can be no value there.
    successors={key:set() for key in nodes}
    for target,preds in predecessors.items():
        for source in preds:successors.setdefault(source,set()).add(target)
    pending=[start_id] if start_id else [];visited=set()
    while pending:
        current=pending.pop()
        if current in visited or current in producers:continue
        visited.add(current)
        if current==nid:
            errors.append(prefix+'存在到达该节点但没有任何候选来源的路径，不能假装总有输出；补齐默认分支的真实候选。');break
        pending.extend(successors.get(current,[]))
    warning=prefix+'按配置列表选第一个存在的变量，不是拼接、投票或选第一个非空值；空字符串／0／false 仍可能被选中。图路径及声明类型检查不证明运行时一定有值，实际分支和资源须试跑。'
    return errors,[warning]
