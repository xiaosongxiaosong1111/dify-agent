"""Bounded scalar-state loops with explicit stop/no-progress contracts.

Generated guards are Dify code nodes: parse locally, never execute here.
"""
import ast
import copy
import math
import re
from .loop_body_graph import shape as body_shape,layout as body_layout

TYPES={'string','number','boolean'}
FIELDS={'loop_count','loop_variables','nodes','updates','break_conditions','logical_operator','failure_policy','limit_policy','no_progress_limit','progress_variables','progress_reason'}
SUFFIXES=('__loop_start','__loop_input','__loop_update','__loop_progress','__loop_limit','__scope_input','__scope_end')
PRIVATE_STAGNANT='__sierra_stagnant_rounds'
OPS={'number':{'=','≠','>','<','≥','≤'},'boolean':{'is','is not'},'string':{'is','is not','contains','not contains','start with','end with','empty','not empty'}}


def variable_types(cfg):
    rows=cfg.get('loop_variables')
    return {row['label']:row.get('var_type') for row in rows if isinstance(row,dict) and isinstance(row.get('label'),str)} if isinstance(rows,list) else {}


def output_type(cfg,name):
    return variable_types(cfg).get(name)


def valid_scalar(value,kind):
    if kind=='string':return isinstance(value,str) and len(value)<=64000 and not re.search(r'\bsk-[A-Za-z0-9_-]{16,}',value)
    if kind=='boolean':return type(value) is bool
    return type(value) in (int,float) and abs(value)<=10**12 and math.isfinite(value) if kind=='number' else False


def condition_expression(conditions,operator,aliases):
    """Emit only fixed operators and safely quoted literals, never user code."""
    parts=[]
    for row in conditions:
        left=aliases[row['variable_selector'][1]];op=row['comparison_operator'];kind=row['varType'];value=row['value']
        if kind=='number':parts.append(f'({left} '+{'=':'==','≠':'!=','>':'>','<':'<','≥':'>=','≤':'<='}[op]+f' {repr(float(value))})')
        elif kind=='boolean':parts.append(f'({left} {"is" if op=="is" else "is not"} {repr(value)})')
        elif op in {'empty','not empty'}:parts.append(f'({"not " if op=="empty" else ""}{left})')
        elif op in {'is','is not'}:parts.append(f'({left} {"==" if op=="is" else "!="} {repr(value)})')
        elif op in {'contains','not contains'}:parts.append(f'({repr(value)} {"in" if op=="contains" else "not in"} {left})')
        else:parts.append(f'({left}.{ "startswith" if op=="start with" else "endswith" }({repr(value)}))')
    return (' and ' if operator=='and' else ' or ').join(parts)


def validate_loop(task,node,outer,outputs,dominators,check_ref,conversation_types=None):
    from .workflow_plan import validate_plan,_placeholder_refs
    from .iteration import BODY_TYPES,output_type as declared_type
    conversation_types=conversation_types or {}
    cfg,nid=node['config'],node['id'];errors=[];warnings=[]
    if not FIELDS<=set(cfg) or set(cfg)-FIELDS-{'edges','entry_node_id'}:errors.append('循环须完整填写轮次、状态／更新、停止条件及失败／上限／无进展政策；未知或缺失字段不能默认。')
    if type(cfg.get('loop_count')) is not int or not 1<=cfg['loop_count']<=100:errors.append('循环 loop_count 必须明确为 1—100；此为 Sierra 首批支持范围，不会静默缩减。')
    if cfg.get('failure_policy')!='terminate' or cfg.get('limit_policy')!='fail_if_unmet':errors.append('循环须明确 failure_policy=terminate、limit_policy=fail_if_unmet；达到次数但目标未满足不能计成功，其他政策尚未适配。')
    if type(cfg.get('no_progress_limit')) is not int or not 2<=cfg['no_progress_limit']<=10:errors.append('连续无进展上限 no_progress_limit 须明确为 2—10。')
    reason=cfg.get('progress_reason')
    if not isinstance(reason,str) or not 0<len(reason.strip())<=2000:errors.append('请用 progress_reason 说明进度字段如何反映本次业务进展；这是声明，不是语义验证。')
    variables=cfg.get('loop_variables');types={}
    if not isinstance(variables,list) or not 1<=len(variables)<=12:return errors+['循环 loop_variables 须有 1—12 个明确状态变量。'],warnings
    for row in variables:
        if not isinstance(row,dict) or set(row)!={'label','var_type','value_type','value'}:errors.append('循环状态须明确 label、var_type、value_type、value。');continue
        label,kind=row['label'],row['var_type']
        if not isinstance(label,str) or not re.fullmatch(r'\w{1,64}',label) or label=='loop_round' or label.startswith('__sierra_') or label.lower() in {'api_key','apikey','token','password','secret','authorization','credential'}:errors.append('循环变量名须为 1—64 字母／数字／下划线，不占用保留名称或凭据字段。');continue
        if label in types:errors.append('循环状态变量名必须唯一。')
        if not isinstance(kind,str) or kind not in TYPES:errors.append('首批循环只支持 string／number／boolean 状态，不猜对象或数组更新类型。');continue
        types[label]=kind
        if row['value_type']=='constant':
            if not valid_scalar(row['value'],kind):errors.append('循环初始常量的类型／范围不符合声明，或疑似凭据；不能自动转换。')
        elif row['value_type']=='variable':
            check_ref(nid,row['value'],'loop_variable_initializer')
            selector=row['value'];actual=conversation_types.get(selector[1]) if isinstance(selector,list) and len(selector)==2 and selector[0]=='conversation' and isinstance(selector[1],str) else declared_type(outer,selector)
            if actual!=kind:errors.append('循环初始引用类型未知或与声明不一致，请先用代码明确输出。')
        else:errors.append('循环初始值 value_type 只能为 constant／variable。')
    progress=cfg.get('progress_variables')
    if not isinstance(progress,list) or not progress or any(not isinstance(name,str) or name not in types for name in progress) or len(progress)!=len(set(progress)):errors.append('progress_variables 须为非空且唯一的状态字段列表；不能把内部轮次计数当未声明的业务进度。')
    conditions=cfg.get('break_conditions');operator=cfg.get('logical_operator')
    if operator not in ('and','or') or not isinstance(conditions,list) or not 1<=len(conditions)<=12:errors.append('循环须明确 and／or 与 1—12 个停止条件。')
    else:
        for row in conditions:
            if not isinstance(row,dict) or set(row)!={'variable_selector','varType','comparison_operator','value'}:errors.append('停止条件须含 variable_selector、varType、comparison_operator、value；嵌套或变量右值尚未适配。');continue
            sel=row['variable_selector'];kind=row['varType'];op=row['comparison_operator'];value=row['value']
            if not isinstance(sel,list) or len(sel)!=2 or sel[0]!=nid or not isinstance(sel[1],str) or types.get(sel[1])!=kind or not isinstance(kind,str) or kind not in TYPES:errors.append('停止条件仅选择本循环已声明的状态，varType 必须一致。');continue
            if not isinstance(op,str) or op not in OPS[kind]:errors.append('停止操作符与变量类型不匹配或未适配。');continue
            if kind=='number':
                try:valid=type(value) is str and len(value)<=40 and math.isfinite(float(value)) and abs(float(value))<=10**12
                except ValueError:valid=False
                if not valid:errors.append('数值停止条件须有明确有限的数值文本，不接受表达式或变量右值。')
            elif kind=='boolean' and type(value) is not bool:errors.append('布尔停止条件须有明确 true／false。')
            elif kind=='string' and (not isinstance(value,str) or len(value)>4000 or re.search(r'\bsk-[A-Za-z0-9_-]{16,}',value)):errors.append('字符串停止条件须为最多 4000 字的文字，不接受凭据。')
    children=cfg.get('nodes')
    try:body=body_shape(cfg)
    except ValueError as exc:return errors+[str(exc)],warnings
    inner={child['id']:child for child in children}
    for child in children:
        if child['type']=='http-request':
            from .body_http import validate as validate_read,NOTE as READ_NOTE
            errors.extend('正文HTTP：'+message for message in validate_read(child['config']));warnings.append(READ_NOTE)
        if child['type']=='variable-aggregator':
            candidates=child['config'].get('variables')
            if isinstance(candidates,list) and any(not isinstance(sel,list) or len(sel)!=2 or not isinstance(sel[0],str) or sel[0] not in inner for sel in candidates):errors.append('循环内部聚合只选择正文声明输出，状态／外部值须先通过代码明确类型。')
    updates=cfg.get('updates');update_names=set()
    if not isinstance(updates,list) or len(updates)!=len(types):errors.append('循环 updates 须逐一完整更新所有声明状态，不能隐藏保留旧值。')
    else:
        for row in updates:
            if not isinstance(row,dict) or set(row)!={'variable','value_selector'} or not isinstance(row.get('variable'),str) or row['variable'] not in types or row['variable'] in update_names:errors.append('循环 updates 必须完整唯一对应状态变量。');continue
            update_names.add(row['variable']);sel=row['value_selector']
            if not isinstance(sel,list) or len(sel)!=2 or not isinstance(sel[0],str) or sel[0] not in inner or declared_type(inner,sel)!=types[row['variable']]:errors.append('状态更新只能取本轮内部已声明且匹配的处理输出，不读循环自身或未知类型。')
    # Available state is only current loop variables and external dominators.
    synthetic=nid+'__scope_input';bindings={(nid,name) for name in types}
    for source in dominators.get(nid,set())-{nid}:bindings.update((source,name) for name in outputs.get(source,set()))
    if task.get('app_type')=='advanced-chat':bindings.add(('sys','query'));bindings.update(('conversation',name) for name in conversation_types)
    mapped={pair:f'scope_{index}' for index,pair in enumerate(sorted(bindings))}
    from .declared_types import resolve as resolve_declaration
    scope_types={(synthetic,label):('string' if pair==('sys','query') else conversation_types.get(pair[1]) if pair[0]=='conversation' else types.get(pair[1]) if pair[0]==nid else resolve_declaration(outer,list(pair),mode=task.get('app_type'))) for pair,label in mapped.items()}
    def remap(sel):
        if isinstance(sel,list) and len(sel)==2 and all(isinstance(v,str) for v in sel) and tuple(sel) in mapped:
            if outer.get(sel[0],{}).get('type')=='parameter-extractor' and sel[1] not in {'__is_success','__reason','__usage'}:check_ref(nid,sel,'正文外部提取参数')
            return [synthetic,mapped[tuple(sel)]]
        return sel
    projected=copy.deepcopy(children)
    for child in projected:
        config=child['config']
        for row in config.get('variables',[]) if isinstance(config.get('variables'),list) else []:
            if isinstance(row,dict):
                original=row.get('value_selector');row['value_selector']=remap(original)
                if child['type']=='template-transform':
                    known=types.get(original[1]) if isinstance(original,list) and len(original)==2 and original[0]==nid and isinstance(original[1],str) else conversation_types.get(original[1]) if isinstance(original,list) and len(original)==2 and original[0]=='conversation' and isinstance(original[1],str) else declared_type({**outer,**inner},original)
                    if original==['sys','query'] and task.get('app_type')=='advanced-chat':known='string'
                    if known is not None and row.get('value_type','string')!=known:errors.append('循环模板 value_type 与实际状态／输出声明不一致。')
        if 'context_variable_selector' in config:config['context_variable_selector']=remap(config['context_variable_selector'])
        if child['type'] in {'question-classifier','knowledge-retrieval'}:
            if child['type']=='knowledge-retrieval' and not isinstance(config.get('query_variable_selector'),list):errors.append('循环内知识检索须明确本轮的文字 query_variable_selector，不继承应用默认问题。')
            config['query_variable_selector']=remap(config.get('query_variable_selector'))
        if child['type']=='document-extractor':config['variable_selector']=remap(config.get('variable_selector'))
        if child['type']=='list-operator':config['variable']=remap(config.get('variable'))
        if child['type']=='parameter-extractor':config['query']=remap(config.get('query'))
        if child['type']=='http-request':
            from .body_http import remap_templates,KEY
            remap_templates(config,remap)
            config.pop(KEY,None)
        if child['type']=='if-else':
            for case in config.get('cases',[]) if isinstance(config.get('cases'),list) else []:
                if not isinstance(case,dict):continue
                for condition in case.get('conditions',[]) if isinstance(case.get('conditions'),list) else []:
                    if not isinstance(condition,dict):continue
                    original=condition.get('variable_selector')
                    known=types.get(original[1]) if isinstance(original,list) and len(original)==2 and original[0]==nid and isinstance(original[1],str) else conversation_types.get(original[1]) if isinstance(original,list) and len(original)==2 and original[0]=='conversation' and isinstance(original[1],str) else declared_type({**outer,**inner},original)
                    if original==['sys','query'] and task.get('app_type')=='advanced-chat':known='string'
                    if known is None or condition.get('varType')!=known:errors.append('循环内部条件须引用明确且一致的实际变量类型，不猜测状态或分支输出。')
                    condition['variable_selector']=remap(original)
                    from .condition_settings import remap_value
                    if 'value' in condition:condition['value']=remap_value(condition['value'],remap)
        for field in ('system_prompt','user_prompt','template'):
            text=config.get(field)
            if isinstance(text,str):
                for src,var in _placeholder_refs(text):
                    if (src,var) in mapped:
                        remap([src,var])
                        text=text.replace('{{#'+src+'.'+var+'#}}','{{#'+synthetic+'.'+mapped[(src,var)]+'#}}')
                config[field]=text
    end_id=nid+'__scope_end';terminal_outputs=[{'variable':row['variable'],'value_selector':row['value_selector']} for row in updates if isinstance(row,dict) and set(row)=={'variable','value_selector'}] if isinstance(updates,list) else []
    nodes=[{'id':synthetic,'type':'start','config':{'variables':[{'variable':name,'type':'paragraph'} for name in mapped.values()]}}]+projected+[{'id':end_id,'type':'end','config':{'outputs':terminal_outputs}}]
    inner_edges=[{'source':synthetic,'target':body['entry']}]+copy.deepcopy(body['edges'])+[{'source':body['terminal'],'target':end_id}]
    checked=validate_plan({**task,'app_type':'workflow','configuration':{**task.get('configuration',{}),'conversation_memory':False}},{'schema_version':1,'nodes':nodes,'edges':inner_edges},_scope_types=scope_types)
    errors.extend('循环内部：'+message for message in checked['errors'])
    warnings.extend('循环内部：'+message for message in checked['warnings'] if '静态校验不等于' not in message)
    warnings+=['循环会生成内部无进展检查／变量赋值和外部停止复核节点；最多轮数未满足目标时按失败处理。进度字段是用户声明，不证明业务改善，目标达成优先于无进展判断。',
              '循环内部文字 LLM 逐轮调用独立或继承模型，不读取 Chatflow 历史；最大轮数不等于费用硬上限，实际模型／状态及初始即达目标场景须试跑。',
              '循环手改保留仅适配完整Sierra保护结构及当前文件规则声明；一般原生循环／嵌套尚未适配，不会删循环或保护后算完成。']
    if not errors:
        for guard in guard_specs(node):
            try:ast.parse(guard['config']['code'])
            except SyntaxError:errors.append('循环保护节点无法通过语法检查，未生成；请核对停止条件。')
    return errors,warnings


def _type_guard_lines(aliases,types):
    lines=['    import math']
    for label,name in aliases.items():
        kind=types[label]
        expr=f'type({name}) is str and len({name}) <= 64000' if kind=='string' else f'type({name}) is bool' if kind=='boolean' else f'type({name}) in (int, float) and abs({name}) <= 10**12 and math.isfinite({name})'
        lines.append(f'    if not ({expr}):\n        raise ValueError("Sierra 循环状态类型或范围不符合声明")')
    return lines


def guard_specs(node):
    cfg,nid=node['config'],node['id'];types=variable_types(cfg);labels=list(types);updates={row['variable']:row['value_selector'] for row in cfg['updates']}
    current={label:f'v{i}' for i,label in enumerate(labels)};candidate={label:f'n{i}' for i,label in enumerate(labels)}
    previous={label:f'p{i}' for i,label in enumerate(cfg['progress_variables'])}
    condition=condition_expression(cfg['break_conditions'],cfg['logical_operator'],candidate)
    args=[*previous.values(),*candidate.values(),'stagnant']
    lines=['def main('+', '.join(args)+') -> dict:']+_type_guard_lines(candidate,types)+_type_guard_lines(previous,types)
    same=' and '.join(f'({previous[label]} == {candidate[label]})' for label in previous)
    lines+=['    completed = '+condition,'    same = '+same,'    next_stagnant = 0 if completed or not same else stagnant + 1',f'    if next_stagnant >= {cfg["no_progress_limit"]}:\n        raise ValueError("Sierra 循环连续无进展达到已确认上限")','    return {"stagnant_rounds": next_stagnant}']
    progress={'id':nid+'__loop_progress','type':'code','title':'Sierra 循环无进展保护','config':{'code_language':'python3','code':'\n'.join(lines)+'\n',
              'variables':[{'variable':alias,'value_selector':[nid,label]} for label,alias in previous.items()]+[{'variable':alias,'value_selector':updates[label]} for label,alias in candidate.items()]+[{'variable':'stagnant','value_selector':[nid,PRIVATE_STAGNANT]}],
              'outputs':{'stagnant_rounds':{'type':'number','children':None}}}}
    lines=['def main('+', '.join(current.values())+') -> dict:']+_type_guard_lines(current,types)+['    if not ('+condition_expression(cfg['break_conditions'],cfg['logical_operator'],current)+'):\n        raise ValueError("Sierra 循环已达到最大轮数，但停止条件尚未满足")','    return {"checked": True}']
    limit={'id':nid+'__loop_limit','type':'code','title':'Sierra 循环停止条件复核','config':{'code_language':'python3','code':'\n'.join(lines)+'\n','variables':[{'variable':alias,'value_selector':[nid,label]} for label,alias in current.items()],'outputs':{'checked':{'type':'boolean','children':None}}}}
    return progress,limit


def input_guard_spec(internal):
    nid,cfg=internal['id'],internal['config'];_,limit=guard_specs(internal)
    input_guard=copy.deepcopy(limit);input_guard['id']=nid+'__loop_input';input_guard['title']='Sierra 循环状态入口检查'
    types=variable_types(cfg);aliases={label:row['variable'] for label,row in zip(types,limit['config']['variables'])}
    input_guard['config']['code']='\n'.join(['def main('+', '.join(aliases.values())+') -> dict:']+_type_guard_lines(aliases,types)+['    return {"checked": True}'])+'\n'
    return input_guard


def native_loop(internal,x,native_node):
    nid,cfg=internal['id'],internal['config'];start_id=nid+'__loop_start';update_id=nid+'__loop_update';progress,limit=guard_specs(internal)
    input_guard=input_guard_spec(internal)
    children=cfg['nodes'];body=body_shape(cfg);positions,width,height=body_layout(children,body);parent=native_node(internal,x)
    parent.update(width=width,height=height,zIndex=1)
    variables=[{'id':nid+'__var_'+str(i),**copy.deepcopy(row)} for i,row in enumerate(cfg['loop_variables'])]+[{'id':nid+'__private_progress','label':PRIVATE_STAGNANT,'var_type':'number','value_type':'constant','value':0}]
    parent['data'].update(start_node_id=start_id,loop_count=cfg['loop_count'],loop_variables=variables,logical_operator=cfg['logical_operator'],break_conditions=copy.deepcopy(cfg['break_conditions']),width=width,height=height)
    start={'id':start_id,'type':'custom-loop-start','parentId':nid,'position':{'x':24,'y':68},'positionAbsolute':{'x':x+24,'y':350},'width':44,'height':48,'zIndex':1002,'draggable':False,'selectable':False,'sourcePosition':'right','targetPosition':'left','data':{'type':'loop-start','title':'','desc':'','selected':False,'isInLoop':True,'isInIteration':False,'loop_id':nid}}
    nodes=[parent,start];edges=[];by_id={child['id']:child for child in children}
    progress_position={'x':428+300*(max(body['ranks'].values())+1),'y':68}
    for child in [input_guard]+children+[progress]:
        emitted=native_node({**internal,**child},x);position={'x':128,'y':68} if child['id']==input_guard['id'] else progress_position if child['id']==progress['id'] else positions[child['id']]
        emitted.update(parentId=nid,zIndex=1002,position=position,positionAbsolute={'x':x+position['x'],'y':350})
        emitted['data'].update(isInLoop=True,isInIteration=False,loop_id=nid);emitted['data'].pop('memory',None)
        nodes.append(emitted)
    edges.extend([_edge(nid,start_id,input_guard['id'],'loop-start','code'),_edge(nid,input_guard['id'],body['entry'],'code',by_id[body['entry']]['type'])])
    for row in body['edges']:
        a,b,handle=row['source'],row['target'],row.get('source_handle','source')
        edge=_edge(nid,a,b,by_id[a]['type'],by_id[b]['type']);edge['sourceHandle']=handle;edge['id']=a+'-'+handle+'-'+b;edges.append(edge)
    edges.append(_edge(nid,body['terminal'],progress['id'],by_id[body['terminal']]['type'],'code'))
    items=[{'variable_selector':[nid,row['variable']],'input_type':'variable','operation':'over-write','value':copy.deepcopy(row['value_selector'])} for row in cfg['updates']]
    items.append({'variable_selector':[nid,PRIVATE_STAGNANT],'input_type':'variable','operation':'over-write','value':[progress['id'],'stagnant_rounds']})
    update=native_node({'id':update_id,'type':'assigner','title':'Sierra 更新本轮循环状态','config':{},'_task_config':internal['_task_config'],'_mode':internal['_mode'],'_start_id':internal['_start_id']},x)
    position={'x':progress_position['x']+300,'y':68};update.update(parentId=nid,zIndex=1002,position=position,positionAbsolute={'x':x+position['x'],'y':350})
    update['data'].update(version='2',items=items,isInLoop=True,isInIteration=False,loop_id=nid)
    nodes.append(update);edges.append(_edge(nid,progress['id'],update_id,'code','assigner'))
    outer_guard=native_node({**internal,**limit},x+width+80);nodes.append(outer_guard)
    return nodes,edges,width,limit['id']


def _edge(nid,source,target,source_type,target_type):
    return {'id':source+'-source-'+target,'source':source,'sourceHandle':'source','target':target,'targetHandle':'target','type':'custom','zIndex':1002,
            'data':{'isInLoop':True,'isInIteration':False,'loop_id':nid,'sourceType':source_type,'targetType':target_type}}
