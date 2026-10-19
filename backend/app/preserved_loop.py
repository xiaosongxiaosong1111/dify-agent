"""Recognize Sierra-protected scalar loops; never erase native guards to pass."""
import ast,copy
from .loop import PRIVATE_STAGNANT,guard_specs,input_guard_spec
from .iteration import BODY_TYPES,BODY_GRAPH_TYPES,MAX_BODY_NODES
from .loop_body_graph import shape as body_shape

REVIEW_FIELDS={'root_token','progress_variables','no_progress_limit','progress_reason','acknowledge_behavior'}
GUARD_DATA={'type','title','desc','selected','isInLoop','isInIteration','loop_id','code_language','code','variables','outputs'}
CONTROL_DATA={'type','title','desc','selected','isInLoop','isInIteration','loop_id','version','items'}
PARENT_DATA={'type','title','desc','selected','isInLoop','isInIteration','start_node_id','loop_count','loop_variables','logical_operator','break_conditions','width','height'}


def candidates(root):
    from .dsl_roundtrip import digest
    token=digest(root)
    return [{'id':n['id'],'title':n['data'].get('title') or n['id'],'loop_count':n['data'].get('loop_count'),'variables':[r.get('label') for r in (n['data'].get('loop_variables') if isinstance(n['data'].get('loop_variables'),list) else []) if isinstance(r,dict) and isinstance(r.get('label'),str) and r.get('label')!=PRIVATE_STAGNANT],'root_token':token} for n in root['workflow']['graph']['nodes'] if n['data'].get('type')=='loop']


def checked_reviews(root,reviews):
    found={r['id']:r for r in candidates(root)}
    if not isinstance(reviews,dict) or set(reviews)-set(found):raise ValueError('循环保留声明只能引用当前实际循环；未知或已移除循环的声明不能沿用。')
    if set(found)-set(reviews):raise ValueError('循环保留须核对当前最终文件的状态、更新、停止／失败、最大轮数及无进展保护；请明确进度字段与上限，不会删除循环或保护后通过。')
    for nid,review in reviews.items():
        if not isinstance(review,dict) or set(review)!=REVIEW_FIELDS or review['acknowledge_behavior'] is not True:raise ValueError('循环保留须精确填写当前文件摘要、进度字段、无进展轮数、业务进度理由并明确确认。')
        if review['root_token']!=found[nid]['root_token']:raise ValueError('循环保留的最终文件已变化，请重新核对；旧停止及进度声明不能复用。')
        reason,labels,limit=review['progress_reason'],review['progress_variables'],review['no_progress_limit']
        if not isinstance(reason,str) or not 0<len(reason.strip())<=2000 or type(limit) is not int or not 2<=limit<=10:raise ValueError('循环进度理由须为1—2000字，无进展轮数须为2—10的整数。')
        if not isinstance(labels,list) or not labels or len(labels)>12 or any(not isinstance(v,str) or v not in found[nid]['variables'] for v in labels) or len(set(labels))!=len(labels):raise ValueError('循环进度字段须非空、唯一并属于当前实际用户状态，不猜测业务进展。')
    return reviews


def same_guard(raw,spec):
    data=raw['data'];cfg=spec['config']
    if set(data)-GUARD_DATA or data.get('type')!='code':raise ValueError('循环保护节点带未适配行为字段或类型，不能忽略错误策略／重试后通过。')
    if any(data.get(k)!=cfg[k] for k in ('code_language','variables','outputs')):raise ValueError('循环保护节点的输入、输出或语言与实际状态／更新不一致。')
    try:same=ast.dump(ast.parse(data['code']),include_attributes=False)==ast.dump(ast.parse(cfg['code']),include_attributes=False)
    except (SyntaxError,TypeError,KeyError):same=False
    if not same:raise ValueError('循环入口／无进展／停止保护代码与已确认规则不一致，或不属于已适配Sierra结构；不会删除保护或猜测等价语义。')


def project(root,reviews=None):
    reviews=checked_reviews(root,{} if reviews is None else reviews)
    graph=root['workflow']['graph'];nodes={};removed=set();configs={};bodies={};guard_owner={}
    if len(graph['nodes'])>1500 or len(graph['edges'])>1500:raise ValueError('循环保留图超过1500个节点／连接，请缩小范围。')
    for raw in graph['nodes']:
        if not isinstance(raw,dict) or not isinstance(raw.get('id'),str) or not raw['id'] or raw['id'] in nodes or not isinstance(raw.get('data'),dict):raise ValueError('保留图节点须有非空唯一ID和data对象。')
        nodes[raw['id']]=raw
    edges=graph['edges'];internal={nid:[] for nid in reviews}
    for edge in edges:
        if not isinstance(edge,dict) or edge.get('source') not in nodes or edge.get('target') not in nodes:raise ValueError('循环保留连接须引用实际存在节点。')
    for nid,review in reviews.items():
        parent=nodes[nid];data=parent['data'];children={key:raw for key,raw in nodes.items() if raw.get('parentId')==nid}
        if parent.get('parentId') or data.get('loop_id') or data.get('isInLoop'):raise ValueError('循环保留仅支持顶层单层循环，嵌套不移除后通过。')
        if set(data)-PARENT_DATA:raise ValueError('循环父节点含未适配控制字段，不能忽略并行、错误继续或其他策略后通过。')
        if not 5<=len(children)<=MAX_BODY_NODES+4:raise ValueError('循环保留须有开始／入口／进度／赋值保护和1—12个顺序处理节点。')
        fixed={key:nid+suffix for key,suffix in [('start','__loop_start'),('input','__loop_input'),('progress','__loop_progress'),('update','__loop_update'),('limit','__loop_limit')]}
        if any(value not in nodes for value in fixed.values()) or any(fixed[k] not in children for k in ('start','input','progress','update')) or nodes[fixed['limit']].get('parentId'):raise ValueError('循环保留缺少完整Sierra保护结构；原生一般循环及变更保护节点ID尚未适配。')
        if data.get('start_node_id')!=fixed['start'] or children[fixed['start']]['data'].get('type')!='loop-start':raise ValueError('实际循环开始节点与保护结构不一致。')
        if set(children[fixed['start']]['data'])-{'type','title','desc','selected','isInLoop','isInIteration','loop_id'}:raise ValueError('循环开始节点含未知控制字段，不能忽略后宣称保护完整。')
        for key,raw in children.items():
            d=raw['data']
            if d.get('isInLoop') is not True or d.get('isInIteration') is not False or d.get('loop_id')!=nid:raise ValueError('循环内部父节点、loop_id与作用域标识不一致。')
            if d.get('memory') is not None or d.get('error_strategy') is not None or (d.get('retry_config') or {}).get('retry_enabled'):raise ValueError('循环内部记忆、错误继续／默认结果或启用重试尚未适配，不删除后通过。')
        outside=nodes[fixed['limit']]['data']
        if outside.get('isInLoop') or outside.get('loop_id') or outside.get('isInIteration') or outside.get('iteration_id'):raise ValueError('循环停止复核必须在容器外，不能错放作用域。')
        local=[];outgoing={key:[] for key in children};incoming={key:0 for key in children};parent_to_guard=0;guard_out=0
        for edge in edges:
            a,b=edge['source'],edge['target'];meta=edge.get('data') or {}
            if a in children or b in children:
                if a not in children or b not in children:raise ValueError('循环内部连接不能穿越容器；状态须通过循环父节点输出。')
                if (children[a]['data'].get('type') not in {'if-else','question-classifier'} and edge.get('sourceHandle','source')!='source') or edge.get('targetHandle','target')!='target' or not isinstance(meta,dict) or meta.get('isInLoop') is not True or meta.get('loop_id')!=nid or meta.get('isInIteration'):raise ValueError('循环内部须有明确出口与当前作用域，不忽略未知出口。')
                outgoing[a].append(b);incoming[b]+=1;local.append(edge)
            elif a==nid:
                if b!=fixed['limit'] or edge.get('sourceHandle','source')!='source' or edge.get('targetHandle','target')!='target':raise ValueError('循环所有外部出口必须先经过停止复核，不能旁路保护。')
                parent_to_guard+=1
            elif b==fixed['limit']:raise ValueError('停止复核不能混入其他入口或兄弟分支来源。')
            elif a==fixed['limit']:
                if edge.get('sourceHandle','source')!='source' or edge.get('targetHandle','target')!='target':raise ValueError('停止复核只支持普通输出连接。')
                guard_out+=1
        body=[key for key in children if key not in {fixed[k] for k in ('start','input','progress','update')}]
        if not body or any(children[k]['data'].get('type') not in BODY_GRAPH_TYPES for k in body):raise ValueError('循环保留正文仅支持代码／模板／文字LLM／标量数组处理／已声明HTTP读取及条件／文字分类／参数提取／无分组聚合，嵌套和其他节点未适配。')
        if parent_to_guard!=1 or guard_out<1 or incoming[fixed['start']] or outgoing[fixed['start']]!=[fixed['input']] or incoming[fixed['input']]!=1 or len(outgoing[fixed['input']])!=1 or outgoing[fixed['input']][0] not in body or incoming[fixed['progress']]!=1 or outgoing[fixed['progress']]!=[fixed['update']] or incoming[fixed['update']]!=1 or outgoing[fixed['update']]:raise ValueError('循环开始／入口／进度／赋值与外部停止保护必须完整连接，不能旁路或遗漏。')
        entry=outgoing[fixed['input']][0]
        body_edges=[{'source':edge['source'],'target':edge['target'],'source_handle':edge.get('sourceHandle','source')} for edge in local if edge['source'] in body and edge['target'] in body]
        candidate={'nodes':[{'id':key,'type':children[key]['data']['type'],'config':{}} for key in body], 'entry_node_id':entry,'edges':body_edges}
        if len(body)==1:
            if body_edges:raise ValueError('循环单正文不能有额外回边。')
            topology=body_shape({'nodes':candidate['nodes']})
        else:topology=body_shape(candidate)
        connectors={(fixed['start'],fixed['input']),(fixed['input'],entry),(topology['terminal'],fixed['progress']),(fixed['progress'],fixed['update'])}
        outside_body=[edge for edge in local if edge['source'] not in body or edge['target'] not in body]
        if len(outside_body)!=4 or {(edge['source'],edge['target']) for edge in outside_body}!=connectors or any(edge.get('sourceHandle','source')!='source' for edge in outside_body):raise ValueError('循环所有正文路径须经同一终点再到进度／赋值保护，不能有旁路连接。')
        sequential=all(children[key]['data']['type'] in BODY_TYPES for key in body) and all(len(outgoing[key])==1 and incoming[key]==1 for key in body)
        if sequential:
            ordered=[];current=entry
            while current in body:
                if current in ordered:raise ValueError('循环正文含额外回边。')
                ordered.append(current);current=outgoing[current][0]
            if set(ordered)!=set(body):raise ValueError('循环正文未完整连接。')
            body=ordered
        variables=data.get('loop_variables')
        if not isinstance(variables,list) or not 2<=len(variables)<=13:raise ValueError('循环保留实际变量须为1—12用户标量及私有无进展状态。')
        private=[r for r in variables if isinstance(r,dict) and r.get('label')==PRIVATE_STAGNANT]
        if len(private)!=1 or private[0]!={'id':nid+'__private_progress','label':PRIVATE_STAGNANT,'var_type':'number','value_type':'constant','value':0}:raise ValueError('循环私有无进展状态与初始值不完整或被修改，不猜测计数起点。')
        user=[]
        for r in variables:
            if not isinstance(r,dict) or set(r)-{'id','label','var_type','value_type','value'}:raise ValueError('循环变量含未适配字段，不忽略后通过。')
            if r.get('label')!=PRIVATE_STAGNANT:user.append({k:r.get(k) for k in ('label','var_type','value_type','value')})
        assign=children[fixed['update']]['data'];items=assign.get('items');updates=[]
        if assign.get('type')!='assigner' or assign.get('version')!='2' or set(assign)-CONTROL_DATA or not isinstance(items,list) or len(items)!=len(user)+1:raise ValueError('循环必须保留v2完整赋值列表，不适配未知错误策略或部分更新。')
        for item in items[:-1]:
            if not isinstance(item,dict) or set(item)!={'variable_selector','input_type','operation','value'} or item['input_type']!='variable' or item['operation']!='over-write' or not isinstance(item['variable_selector'],list) or len(item['variable_selector'])!=2 or item['variable_selector'][0]!=nid:raise ValueError('循环赋值必须明确覆盖本容器用户状态，并取实际正文输出。')
            updates.append({'variable':item['variable_selector'][1],'value_selector':copy.deepcopy(item['value'])})
        if items[-1]!={'variable_selector':[nid,PRIVATE_STAGNANT],'input_type':'variable','operation':'over-write','value':[fixed['progress'],'stagnant_rounds']}:raise ValueError('循环私有无进展状态必须取实际保护节点输出，不能手改为固定值或别处变量。')
        cfg={'loop_count':data.get('loop_count'),'loop_variables':user,'nodes':[],'updates':updates,'break_conditions':copy.deepcopy(data.get('break_conditions')),'logical_operator':data.get('logical_operator'),'failure_policy':'terminate','limit_policy':'fail_if_unmet','no_progress_limit':review['no_progress_limit'],'progress_variables':copy.deepcopy(review['progress_variables']),'progress_reason':review['progress_reason']}
        if not sequential:cfg.update(entry_node_id=entry,edges=body_edges)
        node={'id':nid,'config':cfg};progress,limit=guard_specs(node)
        for spec in (input_guard_spec(node),progress,limit):same_guard(nodes[spec['id']],spec)
        configs[nid]=cfg;bodies[nid]=body;removed.update(children);removed.add(fixed['limit']);guard_owner[fixed['limit']]=nid
    scope_graph={'nodes':[copy.deepcopy(raw) for raw in graph['nodes'] if raw['id'] not in removed], 'edges':[]}
    for edge in edges:
        a,b=edge['source'],edge['target']
        if a in removed and a not in guard_owner or b in removed:continue
        copied=copy.deepcopy(edge)
        if a in guard_owner:copied['source']=guard_owner[a]
        scope_graph['edges'].append(copied)
    body_nodes=[nodes[key] for ids in bodies.values() for key in ids]
    return scope_graph,configs,bodies,body_nodes
