"""Read native sequential-item containers without mutating their body graph."""
from .iteration import BODY_TYPES, BODY_GRAPH_TYPES, MAX_BODY_NODES


def scopes(graph,parallel_ids=()):
    raw_nodes, raw_edges = graph['nodes'], graph['edges']
    if len(raw_nodes) > 1500 or len(raw_edges) > 1500:
        raise ValueError('保留迭代图超过 1500 个节点／连接，请缩小调整范围。')
    nodes = {}
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get('id'), str) or not raw['id'] or raw['id'] in nodes or not isinstance(raw.get('data'), dict):
            raise ValueError('保留图节点 ID 须非空且唯一，data 须为对象。')
        nodes[raw['id']] = raw
    containers = {nid: raw for nid, raw in nodes.items() if raw['data'].get('type') == 'iteration'}
    members = {nid: {} for nid in containers}
    for nid, raw in nodes.items():
        parent, data = raw.get('parentId'), raw['data']
        if data.get('isInLoop') or data.get('loop_id'):
            raise ValueError('保留合并尚未适配一般循环，不会移除循环作用域后通过。')
        if parent:
            if parent not in containers or nid in containers:
                raise ValueError('保留迭代只支持单层容器；未知父节点和嵌套容器尚未适配。')
            if data.get('isInIteration') is not True or data.get('iteration_id', parent) != parent:
                raise ValueError('迭代子节点的父容器与作用域标识不一致。')
            members[parent][nid] = raw
        elif data.get('isInIteration') or data.get('iteration_id') or data.get('type') == 'iteration-start':
            raise ValueError('保留图包含无父容器的迭代内部节点。')
    internal = {nid: [] for nid in containers}
    for edge in raw_edges:
        if not isinstance(edge, dict) or edge.get('source') not in nodes or edge.get('target') not in nodes:
            raise ValueError('保留连接须引用实际存在的节点。')
        source, target = nodes[edge['source']], nodes[edge['target']]
        a, b = source.get('parentId'), target.get('parentId')
        if a != b and (a or b):
            raise ValueError('迭代内部连接不能穿越容器边界；外部连接须接迭代父节点。')
        metadata = edge.get('data') or {}
        if not isinstance(metadata, dict) or metadata.get('isInLoop') or metadata.get('loop_id'):
            raise ValueError('保留连接的循环标识或字段结构尚未适配。')
        if a:
            handle=edge.get('sourceHandle','source')
            if not isinstance(handle,str) or not handle or edge.get('targetHandle','target')!='target' or (source['data'].get('type') not in {'if-else','question-classifier'} and handle!='source'):
                raise ValueError('保留迭代内部连接须为实际条件出口或普通 source，目标为 target；未知句柄不能忽略。')
            if metadata.get('iteration_id', a) != a or metadata.get('isInIteration', True) is not True:
                raise ValueError('迭代内部连接的作用域标识不一致。')
            internal[a].append(edge)
        elif metadata.get('isInIteration') or metadata.get('iteration_id'):
            raise ValueError('外部连接不能标记为迭代内部连接。')
    ordered, starts, body_graphs = {}, set(), {}
    for nid, raw in containers.items():
        data, children = raw['data'], members[nid]
        if data.get('is_parallel') is True:
            if nid not in parallel_ids:raise ValueError('并行项保留需要当前最终文件的明确逐项独立性声明，不会猜测或改为顺序。')
            if type(data.get('parallel_nums')) is not int or not 2<=data['parallel_nums']<=10:raise ValueError('并行保留的实际并发数须为2—10的整数，不会修改后通过。')
        elif data.get('is_parallel') is not False:raise ValueError('迭代保留须明确顺序或并行执行，不能猜测。')
        elif type(data.get('parallel_nums', 1)) is not int or data.get('parallel_nums', 1) != 1:
            raise ValueError('顺序迭代保留要求 parallel_nums=1，不能静默忽略其他并发配置。')
        start = data.get('start_node_id')
        if not isinstance(start, str) or start not in children or children[start]['data'].get('type') != 'iteration-start':
            raise ValueError('迭代缺少属于本容器的实际内部开始节点。')
        if not 2 <= len(children) <= MAX_BODY_NODES + 1:
            raise ValueError(f'保留迭代须有一个内部开始和 1—{MAX_BODY_NODES} 个处理节点。')
        if any(raw['data'].get('type') not in BODY_GRAPH_TYPES for key, raw in children.items() if key != start):
            raise ValueError('保留迭代内部仅支持代码／模板／文字 LLM／标量数组处理／已声明HTTP读取／条件／文字分类／参数提取／无分组聚合；额外开始、嵌套或其他复杂节点未适配。')
        outgoing, incoming = {key: [] for key in children}, {key: 0 for key in children}
        for edge in internal[nid]:
            outgoing[edge['source']].append(edge['target'])
            incoming[edge['target']] += 1
        if incoming[start] or len(outgoing[start])!=1 or any(incoming[key]<1 for key in children if key!=start):
            raise ValueError('保留迭代须有唯一内部开始出口，其他处理节点必须有实际入边。')
        visited,pending={start},[start]
        while pending:
            current=pending.pop()
            for target in outgoing[current]:
                if target not in visited:visited.add(target);pending.append(target)
        if visited != set(children):
            raise ValueError('保留迭代包含未连通的内部节点，不会遗漏后通过。')
        sequential=all(raw['data'].get('type') in BODY_TYPES for key,raw in children.items() if key!=start) and all(incoming[key]==1 for key in children if key!=start) and all(len(values)<=1 for values in outgoing.values())
        if sequential:
            chain,current=[],start
            while outgoing[current]:current=outgoing[current][0];chain.append(current)
        else:
            # Keep original file order; validation follows the actual edges.
            chain=[key for key in children if key!=start]
            body_graphs[nid]={'entry_node_id':outgoing[start][0],
                              'edges':[{'source':edge['source'],'target':edge['target'],'source_handle':edge.get('sourceHandle','source')} for edge in internal[nid] if edge['source']!=start]}
        for key in chain:
            memory = children[key]['data'].get('memory')
            if memory is not None:
                raise ValueError('迭代内部 LLM 的会话记忆尚未适配，不能移除后通过。')
        ordered[nid] = chain
        starts.add(start)
    return ordered, starts, nodes, body_graphs
