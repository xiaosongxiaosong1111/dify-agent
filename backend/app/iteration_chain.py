"""Explicit failures-as-data for a bounded ordered pure calculation chain.

Only generates drafts. No customer code is executed by this module.
"""
import ast
import copy
import hashlib
import json
import re
from .iteration_outcomes import check, digest, ERRORS
from .iteration_summary import SUMMARY_OUTPUTS
from .plan_text_codec import render
from .workflow_plan import validate_plan

MARKER='# Sierra calculation chain outcomes v1\n'
SUMMARY_MARKER='# Sierra calculation chain summary v1\n'
PREFIX='_sierra_contract = '

DIAGNOSTIC_CODES=frozenset(('stage_configuration','calculation_scope','wrapper_contract','stage_order'))


class ChainStageError(ValueError):
    """A known preparation position, never an execution failure or raw code diagnostic."""
    def __init__(self, code, position, total):
        if code not in DIAGNOSTIC_CODES or type(position) is not int or type(total) is not int or not 2<=total<=8 or not 1<=position<=total:
            raise ValueError('计算链准备定位无效，原稿保持。')
        self.code=code;self.position=position;self.total=total
        super().__init__(f'第{position}步（共{total}步）的方案准备未通过，原稿保持，未执行代码。')

    def diagnostic(self):
        return {'code':self.code,'stage_position':self.position,'stage_count':self.total}

GUARD='''
def _sierra_match(value, kind):
    if kind == 'string': return type(value) is str
    return type(value) in (int, float) and -float('inf') < value < float('inf') and (type(value) is not int or -9007199254740991 <= value <= 9007199254740991)
'''


def tail(contract):
    position=contract['position']; total=contract['total']
    if position==1:
        head="def main(sierra_item: str, sierra_index: int) -> dict:\n"
        before="    if type(sierra_item) is not str:\n        raise TypeError('Declared chain input mismatch')\n    _sierra_input = sierra_item\n"
    else:
        head="def main(sierra_previous: dict, sierra_index: int) -> dict:\n"
        before=f'''    row = sierra_previous
    if type(row) is not dict or set(row) != {{'index', 'ok', 'value', 'error_category', 'failed_stage'}} or type(row['index']) is not int or row['index'] != sierra_index or type(row['ok']) is not bool:
        raise TypeError('Previous chain record mismatch')
    if not row['ok']:
        if row['value'] is not None or type(row['error_category']) is not str or row['error_category'] not in ('ValueError', 'TypeError', 'ZeroDivisionError', 'KeyError', 'IndexError', 'OverflowError') or type(row['failed_stage']) is not int or not 1 <= row['failed_stage'] < {position}:
            raise TypeError('Previous chain failure mismatch')
        return {{'outcome': row}}
    if row['error_category'] is not None or row['failed_stage'] is not None or not _sierra_match(row['value'], {contract['input_type']!r}):
        raise TypeError('Previous chain success mismatch')
    _sierra_input = row['value']
'''
    return '\n'+GUARD+'\n'+head+'''    if type(sierra_index) is not int or not 0 <= sierra_index <= 9007199254740991:
        raise TypeError('Declared chain index mismatch')
'''+before+f'''    try:
        result = _sierra_calculate(_sierra_input)
    except (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError, OverflowError) as _sierra_error:
        for _sierra_kind in (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError, OverflowError):
            if isinstance(_sierra_error, _sierra_kind):
                return {{'outcome': {{'index': sierra_index, 'ok': False, 'value': None, 'error_category': _sierra_kind.__name__, 'failed_stage': {position}}}}}
        raise
    if type(result) is not dict or set(result) != {{'result'}} or not _sierra_match(result['result'], {contract['value_type']!r}):
        raise TypeError('Declared chain output mismatch')
    return {{'outcome': {{'index': sierra_index, 'ok': True, 'value': result['result'], 'error_category': None, 'failed_stage': None}}}}
'''


def wrapped(code, argument, input_type, value_type, position, total):
    if input_type not in ('string','number') or value_type not in ('string','number') or type(total) is not int or not 2<=total<=8 or type(position) is not int or not 1<=position<=total or position==1 and input_type!='string':
        raise ValueError('计算链须为2—8步明确文字／数值计算，首项输入文字。')
    fn=check(code,argument,'result',allow_json=True)
    lines=code.splitlines(keepends=True)
    lines[fn.lineno-1],count=re.subn(r'^def[ \t]+main(?=[ \t]*\()', 'def _sierra_calculate',lines[fn.lineno-1],count=1)
    if count!=1:raise ValueError('原计算函数头暂未适配，未改原文。')
    contract={'position':position,'total':total,'argument':argument,'input_type':input_type,'value_type':value_type}
    return MARKER+PREFIX+repr(contract)+'\n'+''.join(lines)+tail(contract)


def original(code):
    try:
        if not isinstance(code,str) or not code.startswith(MARKER) or len(code.encode('utf-8'))>24000:raise ValueError()
        header,body=code[len(MARKER):].split('\n',1)
        if not header.startswith(PREFIX):raise ValueError()
        contract=ast.literal_eval(header[len(PREFIX):])
        if not isinstance(contract,dict) or set(contract)!={'position','total','argument','input_type','value_type'} or not isinstance(contract['argument'],str):raise ValueError()
        suffix=tail(contract)
        if not body.endswith(suffix):raise ValueError()
        raw=body[:-len(suffix)];tree=ast.parse(raw)
        fns=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        if len(fns)!=1 or fns[0].name!='_sierra_calculate':raise ValueError()
        lines=raw.splitlines(keepends=True)
        lines[fns[0].lineno-1],count=re.subn(r'^def[ \t]+_sierra_calculate(?=[ \t]*\()', 'def main',lines[fns[0].lineno-1],count=1)
        raw=''.join(lines)
        if count!=1 or wrapped(raw,contract['argument'],contract['input_type'],contract['value_type'],contract['position'],contract['total'])!=code:raise ValueError()
        return raw,contract
    except (ValueError,TypeError,SyntaxError,KeyError,IndexError,RecursionError):
        raise ValueError('计算链封装或声明不能完整重建，未猜测步骤或覆盖手改。') from None


def summary_code(value_type, total):
    if value_type not in ('string','number') or type(total) is not int or not 2<=total<=8:raise ValueError('汇总须明确原计算类型和2—8步。')
    return SUMMARY_MARKER+GUARD+f'''
def main(results: list, source_items: list) -> dict:
    if type(results) is not list or type(source_items) is not list or any(type(item) is not str for item in source_items) or len(results) != len(source_items):
        raise TypeError('Chain result count or input mismatch')
    successes = []
    failures = []
    for expected_index, row in enumerate(results):
        if type(row) is not dict or set(row) != {{'index', 'ok', 'value', 'error_category', 'failed_stage'}} or type(row['index']) is not int or row['index'] != expected_index or type(row['ok']) is not bool:
            raise TypeError('Chain record fields or index mismatch')
        if row['ok']:
            if row['error_category'] is not None or row['failed_stage'] is not None or not _sierra_match(row['value'], {value_type!r}):
                raise TypeError('Chain successful result mismatch')
            successes.append(row)
        else:
            if row['value'] is not None or type(row['error_category']) is not str or row['error_category'] not in ('ValueError', 'TypeError', 'ZeroDivisionError', 'KeyError', 'IndexError', 'OverflowError') or type(row['failed_stage']) is not int or not 1 <= row['failed_stage'] <= {total}:
                raise TypeError('Chain failed result mismatch')
            failures.append(row)
    return {{'items': results, 'successes': successes, 'failures': failures, 'total': len(results), 'succeeded': len(successes), 'failed': len(failures)}}
'''


def chain_context(plan,node_id):
    """Keep the complete valid upstream graph; change only a terminal chain."""
    nodes={n['id']:n for n in plan['nodes']}
    parent=nodes.get(node_id)
    if parent is None or parent['type']!='iteration':raise ValueError('须明确唯一根计算迭代。')
    ends=[n for n in plan['nodes'] if n['type']=='end']
    if len(ends)!=1:raise ValueError('本批须唯一结束；其它结束路径须另行确认，未省略。')
    end=ends[0];cfg=parent['config'];selector=cfg.get('iterator_selector')
    source=nodes.get(selector[0]) if isinstance(selector,list) and len(selector)==2 else None
    if source is None or source['type']!='code' or selector[1]!='items':raise ValueError('计算链输入仍须明确根Python解析节点的items文字数组，不猜其它来源。')
    incoming={nid:[] for nid in nodes}
    for edge in plan['edges']:incoming[edge['target']].append(edge['source'])
    ancestors=set();pending=[node_id]
    while pending:
        nid=pending.pop()
        if nid not in ancestors:ancestors.add(nid);pending.extend(incoming[nid])
    outgoing=[e for e in plan['edges'] if e['source']==node_id]
    if set(nodes)!=ancestors|{end['id']} or len(outgoing)!=1 or outgoing[0]['target']!=end['id']:
        raise ValueError('只扩展计算链之前的完整上游图；下游处理、旁路或其它消费者须另行确认，未删除或绕过。')
    outputs=end['config'].get('outputs',[])
    if len(outputs)!=1 or outputs[0].get('value_selector')!=[node_id,'output']:
        raise ValueError('计算链仍须直连唯一结束和唯一完整结果，不猜其它下游如何消费新合同。')
    return cfg,source,end


def wrap_plan(task,plan,node_id):
    render(plan)
    if task.get('app_type')!='workflow' or not validate_plan(task,plan)['valid']:raise ValueError('须为完整有效的Workflow，不更换应用类型或修复其它问题。')
    cfg,outer,end=chain_context(plan,node_id);children=cfg['nodes'];oc=outer['config']
    if not 2<=len(children)<=8 or any(n['type']!='code' for n in children) or 'edges' in cfg or 'entry_node_id' in cfg:raise ValueError('正文只支持2—8个顺序纯Python计算节点；DAG、分支、模型、HTTP或其它节点须另行讨论，未改成顺序或删减。')
    if cfg.get('iterator_input_type')!='array[string]' or cfg.get('iterator_selector')!=[outer['id'],'items'] or oc.get('code_language')!='python3' or oc.get('outputs')!={'items':{'type':'array[string]','children':None}} or len(oc.get('variables',[]))!=1:raise ValueError('输入须为明确的JSON文字数组解析items，不猜文件、对象或数值数组来源。')
    check(oc.get('code'),oc['variables'][0]['variable'],'items',True)
    result=copy.deepcopy(plan);target=next(n for n in result['nodes'] if n['id']==node_id)['config'];stages=[];previous_type='string'
    for index,child in enumerate(children):
        cc=child['config'];variables=cc.get('variables');outputs=cc.get('outputs');kind=(outputs or {}).get('result',{}).get('type')
        expected_source=[node_id,'item'] if index==0 else [children[index-1]['id'],'result']
        if set(cc)-{'code_language','code','variables','outputs'} or cc.get('code_language')!='python3' or kind not in ('string','number') or outputs!={'result':{'type':kind,'children':None}} or not isinstance(variables,list) or len(variables)!=1 or set(variables[0])!={'variable','value_selector'} or variables[0].get('value_selector')!=expected_source or not isinstance(variables[0].get('variable'),str):raise ChainStageError('stage_configuration',index+1,len(children))
        arg=variables[0]['variable']
        try:code=wrapped(cc['code'],arg,previous_type,kind,index+1,len(children))
        except ValueError:raise ChainStageError('calculation_scope',index+1,len(children)) from None
        new=target['nodes'][index]['config']
        new.update(code=code,variables=[{'variable':'sierra_item' if index==0 else 'sierra_previous','value_selector':[node_id,'item'] if index==0 else [children[index-1]['id'],'outcome']},{'variable':'sierra_index','value_selector':[node_id,'index']}],outputs={'outcome':{'type':'object','children':None}})
        stages.append({'position':index+1,'input_type':previous_type,'value_type':kind,'original_code_sha256':hashlib.sha256(cc['code'].encode()).hexdigest(),'code_sha256':hashlib.sha256(code.encode()).hexdigest()})
        previous_type=kind
    if cfg.get('output_selector')!=[children[-1]['id'],'result'] or cfg.get('output_type')!='array['+previous_type+']':raise ValueError('父输出须为最后一步完整result数组，不能猜测其它共同输出。')
    target.update(output_selector=[children[-1]['id'],'outcome'],output_type='array[object]')
    if not validate_plan(task,result)['valid']:raise ValueError('新的完整计算链不能通过计划检查，原稿保持。')
    return result,stages,previous_type


def add_summary(task,plan,node_id,value_type,total,code=None):
    result=copy.deepcopy(plan);parent=next(n for n in result['nodes'] if n['id']==node_id);end=next(n for n in result['nodes'] if n['type']=='end');field=end['config']['outputs'][0]['variable'];extras=['successes','failures','total','succeeded','failed']
    if field in extras:raise ValueError('原结束字段与汇总字段冲突，未自动改名；可明确不加汇总或先处理字段名。')
    from .iteration import plan_nodes
    occupied={n['id'] for n in plan_nodes(result)};sid=node_id+'_chain_summary';i=2
    while sid in occupied:sid=node_id+'_chain_summary_'+str(i);i+=1
    code=summary_code(value_type,total) if code is None else code
    result['nodes'].insert(result['nodes'].index(end),{'id':sid,'type':'code','title':'汇总计算链成功与失败','config':{'code_language':'python3','code':code,'variables':[{'variable':'results','value_selector':[node_id,'output']},{'variable':'source_items','value_selector':copy.deepcopy(parent['config']['iterator_selector'])}],'outputs':copy.deepcopy(SUMMARY_OUTPUTS)}})
    next(e for e in result['edges'] if e['source']==node_id and e['target']==end['id'])['target']=sid
    result['edges'].append({'source':sid,'target':end['id']})
    end['config']['outputs'][0]['value_selector']=[sid,'items']
    end['config']['outputs'] += [{'variable':name,'value_selector':[sid,name]} for name in extras]
    if not validate_plan(task,result)['valid']:raise ValueError('汇总后的完整计算链无效，原稿保持。')
    return result,sid,extras


def typed_child(node):
    if not isinstance(node,dict) or not isinstance(node.get('config'),dict):return False
    cfg=node['config'];outputs=cfg.get('outputs');result=outputs.get('result') if isinstance(outputs,dict) else None
    return isinstance(result,dict) and result.get('type')=='object' or isinstance(cfg.get('code'),str) and cfg['code'].startswith('# Sierra typed calculation chain outcomes v1\n')


def candidate(task,plan,node_id,acknowledge=False,include_summary=False,ack_summary=False,operation='wrap',stage_schema_texts=None):
    if type(acknowledge) is not bool or acknowledge is not True:raise ValueError('须明确接受五字段逐项合同、失败步骤及后续计算跳过；其它错误仍终止。')
    if type(include_summary) is not bool or type(ack_summary) is not bool or include_summary!=ack_summary:raise ValueError('增加汇总须单独明确确认，不能忽略多余或缺少的确认。')
    if operation not in ('wrap','append_summary'):raise ValueError('未知计算链操作。')
    selected=next((n.get('config',{}) for n in plan.get('nodes',[]) if isinstance(n,dict) and n.get('id')==node_id and n.get('type')=='iteration'),{}) if isinstance(plan,dict) else {}
    children=selected.get('nodes',[]) if isinstance(selected,dict) else []
    typed=any(typed_child(n) for n in children) if isinstance(children,list) else False
    if typed:
        from .iteration_chain_objects import candidate as typed_candidate
        return typed_candidate(task,plan,node_id,acknowledge,include_summary,ack_summary,operation,{} if stage_schema_texts is None else stage_schema_texts)
    if stage_schema_texts:raise ValueError('原文字／数值计算链不接收额外对象步骤Schema。')
    if operation=='wrap':result,stages,kind=wrap_plan(task,plan,node_id)
    else:
        if not include_summary:raise ValueError('追加汇总须明确选择并确认汇总输出。')
        render(plan)
        if task.get('app_type')!='workflow' or not validate_plan(task,plan)['valid']:raise ValueError('仅为完整有效Workflow计算链追加汇总，不覆盖已有汇总或其它图。')
        reconstructed=copy.deepcopy(plan);cfg,_,_=chain_context(reconstructed,node_id)
        if not cfg or not 2<=len(cfg.get('nodes',[]))<=8:raise ValueError('未找到完整原计算链。')
        for index,child in enumerate(cfg['nodes']):
            try:raw,contract=original(child.get('config',{}).get('code'))
            except ValueError:raise ChainStageError('wrapper_contract',index+1,len(cfg['nodes'])) from None
            if contract['position']!=index+1 or contract['total']!=len(cfg['nodes']):raise ChainStageError('stage_order',index+1,len(cfg['nodes']))
            child['config'].update(code=raw,variables=[{'variable':contract['argument'],'value_selector':[node_id,'item'] if index==0 else [cfg['nodes'][index-1]['id'],'result']}],outputs={'result':{'type':contract['value_type'],'children':None}})
        cfg.update(output_selector=[cfg['nodes'][-1]['id'],'result'],output_type='array['+contract['value_type']+']')
        rebuilt,stages,kind=wrap_plan(task,reconstructed,node_id)
        if rebuilt!=plan:raise ValueError('原完整封装或绑定已改变，未覆盖手改或猜测结果。')
        result=copy.deepcopy(plan)
    sid=None;extras=[]
    if include_summary:result,sid,extras=add_summary(task,result,node_id,kind,len(stages))
    return {'plan_text':render(result),'node_id':node_id,'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),'stages':stages,'value_type':kind,'operation':operation,'include_summary':include_summary,'summary_node_id':sid,'added_nodes':int(include_summary),'added_end_fields':extras,'caught_error_classes':list(ERRORS),'native_error_handle_mode':'terminated','output_type':'array[object]','record_fields':['index','ok','value','error_category','failed_stage'],'verification':'local_calculation_chain_draft_only','task_changed':False,'network_requested':False,'platform_checked':False,'business_verified':False}


def register(host):
    from fastapi import APIRouter,HTTPException
    from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
    from uuid import UUID
    from typing import Literal,Annotated
    from .plan_drafts import DraftRoute,inspect_text
    from .plan_text_codec import parse
    class Request(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        plan_text:StrictStr=Field(max_length=2_000_000)
        node_id:StrictStr=Field(min_length=1,max_length=256)
        acknowledge_chain_contract:StrictBool
        include_summary:StrictBool=False
        acknowledge_summary_outputs:StrictBool=False
        operation:Literal['wrap','append_summary']='wrap'
        request_nonce:UUID
        stage_schema_texts:dict[Annotated[StrictStr,Field(min_length=1,max_length=256)],Annotated[StrictStr,Field(max_length=64000)]]=Field(default_factory=dict,max_length=8)
    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/iteration-chain-outcomes')
    def prepare(item_id:str,payload:Request):
        with host.store.lock:
            task=host.get_task(item_id);host.require_revision(task,payload.revision)
            try:
                inspect_text(payload.plan_text)
                for text in payload.stage_schema_texts.values():inspect_text(text)
                value=candidate(task,parse(payload.plan_text),payload.node_id,payload.acknowledge_chain_contract,payload.include_summary,payload.acknowledge_summary_outputs,payload.operation,payload.stage_schema_texts)
            except ChainStageError as exc:
                detail={**exc.diagnostic(),'kind':'chain_stage_preparation','task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce),'node_id':payload.node_id,'operation':payload.operation,'include_summary':payload.include_summary,'source_text_sha256':hashlib.sha256(payload.plan_text.encode('utf-8')).hexdigest(),'verification':'local_chain_preparation_only','task_changed':False,'network_requested':False,'platform_checked':False,'business_verified':False}
                raise HTTPException(422,detail) from None
            except (TypeError,KeyError,UnicodeError,RecursionError,OverflowError):raise HTTPException(422,'计算链结构或编码超出此批范围，原稿保持，未执行代码。') from None
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
            return {**value,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
    host.app.include_router(router)
