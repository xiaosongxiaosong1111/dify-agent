"""Prove an extraction success edge is necessary; no node execution or repair."""
import re

CONTROL_FIELDS={'__is_success','__reason','__usage'}
MACRO=re.compile(r'\{\{#([\w-]+)\.([\w]+)#\}\}')


def reachable(start, successors, excluded=None):
    seen=set();pending=[start] if isinstance(start,str) else []
    while pending:
        source=pending.pop()
        if source in seen:continue
        seen.add(source)
        for target,handle in successors.get(source,[]):
            if (source,target,handle)!=excluded:pending.append(target)
    return seen


def _refs(data):
    values=[]
    for row in data.get('variables',[]) if isinstance(data.get('variables'),list) else []:
        values.append(row.get('value_selector') if isinstance(row,dict) else row)
    for row in data.get('outputs',[]) if isinstance(data.get('outputs'),list) else []:
        if isinstance(row,dict):values.append(row.get('value_selector'))
    for key in ('query','query_variable_selector','variable_selector','variable','iterator_selector'):
        if key in data:values.append(data[key])
    for row in data.get('loop_variables',[]) if isinstance(data.get('loop_variables'),list) else []:
        if isinstance(row,dict) and row.get('value_type')=='variable':values.append(row.get('value'))
    for row in data.get('items',[]) if isinstance(data.get('items'),list) else []:
        if isinstance(row,dict) and row.get('input_type')=='variable':values.append(row.get('value'))
    for row in data.get('break_conditions',[]) if isinstance(data.get('break_conditions'),list) else []:
        if isinstance(row,dict):values.append(row.get('variable_selector'))
    context=data.get('context')
    if isinstance(context,dict) and context.get('enabled'):values.append(context.get('variable_selector'))
    for case in data.get('cases',[]) if isinstance(data.get('cases'),list) else []:
        for row in case.get('conditions',[]) if isinstance(case,dict) and isinstance(case.get('conditions'),list) else []:
            if isinstance(row,dict):values.append(row.get('variable_selector'))
    pending=[data[key] for key in ('prompt_template','template','answer','url','headers','params','body','cases') if key in data]
    count=0
    while pending:
        value=pending.pop();count+=1
        if count>40000:raise ValueError('成果引用过多，提取成功门无法完整核对，不派发。')
        if isinstance(value,str):values.extend([list(pair) for pair in MACRO.findall(value)])
        elif isinstance(value,list):pending.extend(value)
        elif isinstance(value,dict):pending.extend(value.values())
    return values


def require_native_success(root):
    raw=root['workflow']['graph']['nodes'];edges=root['workflow']['graph']['edges']
    if any(not isinstance(n,dict) or not isinstance(n.get('id'),str) or not isinstance(n.get('data'),dict) or n.get('parentId') is not None and not isinstance(n['parentId'],str) for n in raw):
        raise ValueError('成果节点／父作用域结构无法完整核对，不派发。')
    nodes={n['id']:n for n in raw};extractors={nid:n for nid,n in nodes.items() if n['data'].get('type')=='parameter-extractor'}
    if not extractors:return
    if len(nodes)!=len(raw):raise ValueError('成果节点ID重复，提取成功门无法核对，不派发。')
    successors={nid:[] for nid in nodes}
    for edge in edges:
        a,b=edge['source'],edge['target']
        if a not in nodes or b not in nodes:raise ValueError('成果连接引用未知节点，提取成功门无法核对。')
        successors[a].append((b,edge.get('sourceHandle','source')))
    owners={nid:n.get('parentId') for nid,n in nodes.items()};scopes={};proofs={}
    for nid,node in nodes.items():scopes.setdefault(owners[nid],[]).append(node)
    for consumer,node in nodes.items():
        for selector in _refs(node['data']):
            if not isinstance(selector,list) or not selector or not isinstance(selector[0],str) or selector[0] not in extractors:continue
            if len(selector)!=2 or not all(isinstance(v,str) for v in selector):raise ValueError('提取业务引用结构未适配，不能省略后派发。')
            source,field=selector
            if field in CONTROL_FIELDS:continue
            scope=owners[source];target=consumer;visited=set()
            # An outer extraction must protect the container entrance as well.
            while owners[target]!=scope:
                parent=owners[target]
                if parent not in nodes or parent in visited:raise ValueError('提取业务参数跨越不可证明的容器作用域，不派发。')
                visited.add(parent);target=parent
            if source not in proofs:
                outgoing=successors[source]
                if len(outgoing)!=1 or outgoing[0][1]!='source':raise ValueError('提取业务参数没有唯一直接成功检查，不派发。')
                guard=outgoing[0][0];data=nodes[guard]['data'];cases=data.get('cases')
                if data.get('type')!='if-else' or owners[guard]!=scope or not isinstance(cases,list) or len(cases)!=1 or not isinstance(cases[0],dict):raise ValueError('提取业务参数缺少明确同作用域成功IF，不派发。')
                case=cases[0];conditions=case.get('conditions');cid=case.get('case_id',case.get('id'))
                if not isinstance(cid,str) or not cid:raise ValueError('提取成功case缺少明确ID，不派发。')
                c=conditions[0] if isinstance(conditions,list) and len(conditions)==1 and isinstance(conditions[0],dict) else {}
                if case.get('logical_operator','and')!='and' or c.get('variable_selector')!=[source,'__is_success'] or c.get('varType')!='number' or c.get('comparison_operator')!='=' or c.get('value')!='1':raise ValueError('提取成功IF须明确检查数值__is_success等于文字1，不派发。')
                exits=[(b,h) for b,h in successors[guard] if h==cid]
                starts=[n['id'] for n in scopes[scope] if n['data'].get('type') in ({'start'} if scope is None else {'iteration-start','loop-start'})]
                if len(exits)!=1 or len(starts)!=1 or owners[exits[0][0]]!=scope:raise ValueError('无法完整核对提取成功出口和当前作用域入口，不派发。')
                local={a:[(b,h) for b,h in links if owners[b]==scope] for a,links in successors.items() if owners[a]==scope}
                proofs[source]=(reachable(starts[0],local),reachable(starts[0],local,(guard,exits[0][0],cid)))
            normal,bypass=proofs[source]
            if target not in normal or target in bypass:
                raise ValueError(f'节点 {consumer} 使用未经成功路径保护的提取业务参数，失败分支可能到达；请修改并重新确认成果，不派发。')
