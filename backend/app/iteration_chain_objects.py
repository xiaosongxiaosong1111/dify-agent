"""Explicit schemas for object intermediate values; generates drafts only."""
import ast,copy,hashlib,json,re
from . import iteration_chain as base
from .iteration_object_contract import schema_contract,schema_from_text,guard as object_guard
from .workflow_plan import validate_plan
from .plan_text_codec import render

MARKER='# Sierra typed calculation chain outcomes v1\n'
SUMMARY_MARKER='# Sierra typed calculation chain summary v1\n'
TYPES=('string','number','object')


def guard():
    value=object_guard()
    assert 'def _sierra_object_valid(value):' in value and '_sierra_check(value, _sierra_schema)' in value
    value=value.replace('def _sierra_object_valid(value):','def _sierra_object_valid(value, schema):').replace('_sierra_check(value, _sierra_schema)','_sierra_check(value, schema)')
    return value+"\ndef _sierra_match(value, kind, schema=None):\n    if kind == 'object': return _sierra_object_valid(value, schema)\n    if kind == 'string': return type(value) is str\n    return type(value) in (int, float) and -float('inf') < value < float('inf') and (type(value) is not int or -9007199254740991 <= value <= 9007199254740991)\n"


def tail(contract):
    value=base.tail(contract).replace(base.GUARD,guard())
    a=f"_sierra_match(row['value'], {contract['input_type']!r})";b=f"_sierra_match(result['result'], {contract['value_type']!r})"
    assert a in value or contract['position']==1
    assert b in value
    return value.replace(a,f"_sierra_match(row['value'], {contract['input_type']!r}, _sierra_contract['input_schema'])").replace(b,f"_sierra_match(result['result'], {contract['value_type']!r}, _sierra_contract['value_schema'])")


def wrapped(code,argument,input_type,value_type,position,total,input_schema=None,value_schema=None):
    if input_type not in TYPES or value_type not in TYPES or type(total) is not int or not 2<=total<=8 or type(position) is not int or not 1<=position<=total or position==1 and input_type!='string':raise ValueError('对象计算链步骤或类型声明不完整。')
    for kind,schema in ((input_type,input_schema),(value_type,value_schema)):
        if kind=='object':schema_contract(schema)
        elif schema is not None:raise ValueError('文字／数值步骤不接收额外对象Schema。')
    contract={'position':position,'total':total,'argument':argument,'input_type':input_type,'value_type':value_type,'input_schema':schema_contract(input_schema) if input_type=='object' else None,'value_schema':schema_contract(value_schema) if value_type=='object' else None}
    fn=base.check(code,argument,'result',allow_json=True);lines=code.splitlines(keepends=True)
    lines[fn.lineno-1],count=re.subn(r'^def[ \t]+main(?=[ \t]*\()', 'def _sierra_calculate',lines[fn.lineno-1],count=1)
    if count!=1:raise ValueError('原计算函数头暂未适配，未改原文。')
    return MARKER+base.PREFIX+repr(contract)+'\n'+''.join(lines)+tail(contract)


def original(code):
    try:
        if not isinstance(code,str) or not code.startswith(MARKER) or len(code.encode('utf-8'))>300000:raise ValueError()
        header,body=code[len(MARKER):].split('\n',1)
        if not header.startswith(base.PREFIX):raise ValueError()
        c=ast.literal_eval(header[len(base.PREFIX):])
        if type(c) is not dict or set(c)!={'position','total','argument','input_type','value_type','input_schema','value_schema'} or not isinstance(c['argument'],str):raise ValueError()
        suffix=tail(c)
        if not body.endswith(suffix):raise ValueError()
        raw=body[:-len(suffix)];tree=ast.parse(raw);fns=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        if len(fns)!=1 or fns[0].name!='_sierra_calculate':raise ValueError()
        lines=raw.splitlines(keepends=True);lines[fns[0].lineno-1],count=re.subn(r'^def[ \t]+_sierra_calculate(?=[ \t]*\()', 'def main',lines[fns[0].lineno-1],count=1);raw=''.join(lines)
        if count!=1 or wrapped(raw,c['argument'],c['input_type'],c['value_type'],c['position'],c['total'],c['input_schema'],c['value_schema'])!=code:raise ValueError()
        return raw,c
    except (ValueError,TypeError,SyntaxError,KeyError,IndexError,RecursionError,UnicodeError):raise ValueError('对象计算链原文或Schema封装不能完整重建，未覆盖手改。') from None


def summary_code(value_type,total,schema):
    if value_type not in TYPES:raise ValueError('须明确汇总成功类型。')
    if value_type=='object':schema=schema_contract(schema)
    elif schema is not None:raise ValueError('非对象汇总不接收Schema。')
    value=base.summary_code('number',total)
    value=value[len(base.SUMMARY_MARKER):].replace(base.GUARD,guard())
    value=value.replace("_sierra_match(row['value'], 'number')",f"_sierra_match(row['value'], {value_type!r}, _sierra_final_schema)")
    return SUMMARY_MARKER+'_sierra_final_schema = '+repr(schema)+'\n'+value


def wrap_plan(task,plan,node_id,texts):
    render(plan)
    if task.get('app_type')!='workflow' or not validate_plan(task,plan)['valid']:raise ValueError('须为完整有效Workflow，未修改其它问题。')
    cfg,source,end=base.chain_context(plan,node_id);children=cfg['nodes'];oc=source['config']
    if not 2<=len(children)<=8 or any(n['type']!='code' for n in children) or 'edges' in cfg or 'entry_node_id' in cfg:raise ValueError('对象中间结果只支持2—8步顺序纯Python计算，不删分支或其它节点。')
    if cfg.get('iterator_input_type')!='array[string]' or oc.get('code_language')!='python3' or oc.get('outputs')!={'items':{'type':'array[string]','children':None}} or len(oc.get('variables',[]))!=1:raise ValueError('须明确单输入Python解析items文字数组。')
    base.check(oc.get('code'),oc['variables'][0]['variable'],'items',True)
    wanted={n['id'] for n in children if n['config'].get('outputs',{}).get('result',{}).get('type')=='object'}
    if not wanted or type(texts) is not dict or set(texts)!=wanted:raise ValueError('每个对象结果步骤须分别明确完整Schema，不能缺少、多传或为非对象步骤附加规则。')
    schemas={}
    for index,child in enumerate(children):
        if child['id'] in wanted:
            try:schemas[child['id']]=schema_from_text(texts[child['id']])
            except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise base.ChainStageError('stage_configuration',index+1,len(children)) from None
    result=copy.deepcopy(plan);target=next(n for n in result['nodes'] if n['id']==node_id)['config'];stages=[];previous_type='string';previous_schema=None
    for index,child in enumerate(children):
        cc=child['config'];variables=cc.get('variables');outputs=cc.get('outputs');kind=(outputs or {}).get('result',{}).get('type');expected=[node_id,'item'] if index==0 else [children[index-1]['id'],'result']
        if set(cc)-{'code_language','code','variables','outputs'} or cc.get('code_language')!='python3' or kind not in TYPES or outputs!={'result':{'type':kind,'children':None}} or not isinstance(variables,list) or len(variables)!=1 or set(variables[0])!={'variable','value_selector'} or variables[0].get('value_selector')!=expected or not isinstance(variables[0].get('variable'),str):raise base.ChainStageError('stage_configuration',index+1,len(children))
        schema=schemas.get(child['id']);arg=variables[0]['variable']
        try:code=wrapped(cc['code'],arg,previous_type,kind,index+1,len(children),previous_schema,schema)
        except ValueError:raise base.ChainStageError('calculation_scope',index+1,len(children)) from None
        target['nodes'][index]['config'].update(code=code,variables=[{'variable':'sierra_item' if index==0 else 'sierra_previous','value_selector':[node_id,'item'] if index==0 else [children[index-1]['id'],'outcome']},{'variable':'sierra_index','value_selector':[node_id,'index']}],outputs={'outcome':{'type':'object','children':None}})
        stages.append({'position':index+1,'input_type':previous_type,'value_type':kind,'original_code_sha256':hashlib.sha256(cc['code'].encode()).hexdigest(),'code_sha256':hashlib.sha256(code.encode()).hexdigest()});previous_type=kind;previous_schema=schema
    if cfg.get('output_selector')!=[children[-1]['id'],'result'] or cfg.get('output_type')!='array['+previous_type+']':raise ValueError('父输出须为最后一步完整result数组。')
    target.update(output_selector=[children[-1]['id'],'outcome'],output_type='array[object]')
    if not validate_plan(task,result)['valid']:raise ValueError('完整对象计算链未通过计划检查，原稿保持。')
    return result,stages,previous_type,schemas


def candidate(task,plan,node_id,acknowledge,include_summary,ack_summary,operation,texts):
    if type(acknowledge) is not bool or acknowledge is not True or type(include_summary) is not bool or type(ack_summary) is not bool or include_summary!=ack_summary:raise ValueError('须明确确认逐项五字段合同，增加汇总另行确认。')
    if operation=='wrap':result,stages,kind,schemas=wrap_plan(task,plan,node_id,texts)
    elif operation=='append_summary':
        if not include_summary or texts:raise ValueError('追加汇总仅使用原封装Schema，须确认汇总且不传替换规则。')
        render(plan)
        if task.get('app_type')!='workflow' or not validate_plan(task,plan)['valid']:raise ValueError('须完整有效的原对象计算链。')
        reconstructed=copy.deepcopy(plan);cfg,_,_=base.chain_context(reconstructed,node_id);children=cfg['nodes'];texts={}
        if not 2<=len(children)<=8:raise ValueError('原链须2—8步。')
        for index,child in enumerate(children):
            try:raw,c=original(child.get('config',{}).get('code'))
            except ValueError:raise base.ChainStageError('wrapper_contract',index+1,len(children)) from None
            if c['position']!=index+1 or c['total']!=len(children):raise base.ChainStageError('stage_order',index+1,len(children))
            child['config'].update(code=raw,variables=[{'variable':c['argument'],'value_selector':[node_id,'item'] if index==0 else [children[index-1]['id'],'result']}],outputs={'result':{'type':c['value_type'],'children':None}})
            if c['value_type']=='object':texts[child['id']]=json.dumps(c['value_schema'],ensure_ascii=False,separators=(',',':'))
        cfg.update(output_selector=[children[-1]['id'],'result'],output_type='array['+c['value_type']+']')
        rebuilt,stages,kind,schemas=wrap_plan(task,reconstructed,node_id,texts)
        if rebuilt!=plan:raise ValueError('完整原对象计算链或绑定已变化，未覆盖手改。')
        result=copy.deepcopy(plan)
    else:raise ValueError('未知计算链操作。')
    final_id=next(n for n in result['nodes'] if n['id']==node_id)['config']['nodes'][-1]['id'];final_schema=schemas.get(final_id);sid=None;extras=[]
    if include_summary:result,sid,extras=base.add_summary(task,result,node_id,kind,len(stages),code=summary_code(kind,len(stages),final_schema))
    source_schema_hashes={nid:hashlib.sha256(text.encode('utf-8')).hexdigest() for nid,text in texts.items()} if operation=='wrap' else {}
    return {'plan_text':render(result),'node_id':node_id,'source_plan_sha256':base.digest(plan),'candidate_plan_sha256':base.digest(result),'stages':stages,'value_type':kind,'operation':operation,'include_summary':include_summary,'summary_node_id':sid,'added_nodes':int(include_summary),'added_end_fields':extras,'caught_error_classes':list(base.ERRORS),'native_error_handle_mode':'terminated','output_type':'array[object]','record_fields':['index','ok','value','error_category','failed_stage'],'verification':'local_calculation_chain_draft_only','task_changed':False,'network_requested':False,'platform_checked':False,'business_verified':False,'stage_schema_text_sha256':source_schema_hashes,'stage_schema_sha256':{nid:base.digest(s) for nid,s in schemas.items()},'result_schema_sha256':base.digest(final_schema) if kind=='object' else None}
