"""Explicit conditional loop body DAG. No back edge or implicit parallel fork."""
from .iteration import BODY_TYPES,BODY_GRAPH_TYPES
from .body_http import FIELDS as HTTP_BODY_FIELDS
from .retrieval_settings import FIELDS as RETRIEVAL_BODY_FIELDS

FIELDS={'code':{'code_language','code','variables','outputs'},'template-transform':{'template','variables'},
        'llm':{'system_prompt','user_prompt','context_variable_selector','model','structured_output_enabled','structured_output'},'if-else':{'cases'},
        'variable-aggregator':{'variables','output_type','selection_mode'},'question-classifier':{'classes','query_variable_selector','instruction','model','unmatched_policy'},'list-operator':{'variable','input_type','filter_by','order_by','extract_by','limit'},'parameter-extractor':{'query','parameters','instruction','reasoning_mode','model','failure_policy'},'http-request':HTTP_BODY_FIELDS,'knowledge-retrieval':RETRIEVAL_BODY_FIELDS,'document-extractor':{'variable_selector','input_type','empty_policy'}}


def shape(cfg):
    children=cfg.get('nodes');graph='edges' in cfg or 'entry_node_id' in cfg
    allowed=BODY_GRAPH_TYPES if graph else BODY_TYPES
    if not isinstance(children,list) or not 1<=len(children)<=12 or any(not isinstance(n,dict) or not isinstance(n.get('id'),str) or not n['id'] or not isinstance(n.get('type'),str) or n['type'] not in allowed or not isinstance(n.get('config'),dict) for n in children):
        raise ValueError('循环内部须有1—12个代码／模板／文字LLM／标量数组处理／知识检索／本容器HTTP文件文档提取／已声明HTTP读取；条件／分类／提取／聚合须完整内部DAG，嵌套／写入HTTP／人工未适配。')
    by_id={n['id']:n for n in children}
    if len(by_id)!=len(children):raise ValueError('循环内部节点ID必须唯一。')
    for n in children:
        if set(n['config'])-FIELDS[n['type']]:raise ValueError('循环内部节点包含未适配设置，不能忽略。')
    if not graph:
        return {'graph':False,'entry':children[0]['id'],'terminal':children[-1]['id'],
                'edges':[{'source':a['id'],'target':b['id']} for a,b in zip(children,children[1:])],
                'ranks':{n['id']:i for i,n in enumerate(children)}}
    entry,edges=cfg.get('entry_node_id'),cfg.get('edges')
    if not isinstance(entry,str) or entry not in by_id or not isinstance(edges,list) or not 1<=len(edges)<=48:
        raise ValueError('循环内部DAG须有实际entry_node_id及1—48条完整edges；不能只填写其中一个。')
    incoming={key:set() for key in by_id};outgoing={key:[] for key in by_id};seen=set();handles=set()
    for edge in edges:
        if not isinstance(edge,dict) or set(edge)-{'source','target','source_handle'} or not isinstance(edge.get('source'),str) or not isinstance(edge.get('target'),str) or edge['source'] not in by_id or edge['target'] not in by_id or not isinstance(edge.get('source_handle','source'),str):
            raise ValueError('循环内部连接只允许本正文source/target/source_handle，不能跨作用域或使用保护节点。')
        source,target,handle=edge['source'],edge['target'],edge.get('source_handle','source')
        key=(source,target,handle)
        if key in seen:raise ValueError('循环内部连接重复，不静默合并。')
        seen.add(key)
        if by_id[source]['type'] not in {'if-else','question-classifier'} and handle!='source':raise ValueError('循环普通内部节点只能使用source出口。')
        if (source,handle) in handles:raise ValueError('循环同一出口不能扇出多个目标，尚未适配内部隐式并行。')
        handles.add((source,handle));incoming[target].add(source);outgoing[source].append(target)
    if incoming[entry]:raise ValueError('循环正文入口不能有内部入边。')
    ends=[key for key in by_id if not outgoing[key]]
    if len(ends)!=1:raise ValueError('循环所有内部路径必须汇入一个共同正文终点，再经过进度与赋值保护。')
    terminal=ends[0];degree={key:len(value) for key,value in incoming.items()};queue=[entry];ranks={key:0 for key in by_id};visited=set()
    for source in queue:
        if source in visited:continue
        visited.add(source)
        for target in sorted(set(outgoing[source])):
            ranks[target]=max(ranks[target],ranks[source]+1);degree[target]-=1
            if degree[target]==0:queue.append(target)
    if visited!=set(by_id):raise ValueError('循环正文有回边、断开节点或未汇合路径；循环由父容器控制，不能在正文再创建图环。')
    return {'graph':True,'entry':entry,'terminal':terminal,'edges':edges,'ranks':ranks}


def layout(children,body):
    rows={};positions={}
    for child in children:
        rank=body['ranks'][child['id']];row=rows.get(rank,0);rows[rank]=row+1
        positions[child['id']]={'x':428+300*rank,'y':68+160*row}
    last=max(body['ranks'].values())
    return positions,150+300*(last+4),max(250,220+160*(max(rows.values())-1))
