"""Canonical success/failure summary for an explicitly adopted outcome graph.

Only prepare text. Never run customer code, save a task or contact Dify.
"""
import ast,copy,json,re,hashlib
from .iteration_outcomes import candidate as outcome_candidate,wrapped,MARKER,ERRORS,digest,NUMBER_GUARD
from .plan_text_codec import render
from .workflow_plan import validate_plan
from .iteration_object_contract import MARKER as OBJECT_MARKER, original_object, summary_object

SUMMARY_CODE='''# Sierra iteration result summary v1
def main(results: list, source_items: list) -> dict:
    if not isinstance(results, list) or not isinstance(source_items, list) or any(not isinstance(item, str) for item in source_items):
        raise TypeError('Iteration result and original input must be arrays of declared types')
    if len(results) != len(source_items):
        raise TypeError('Iteration result count differs from original input')
    successes = []
    failures = []
    for expected_index, row in enumerate(results):
        if not isinstance(row, dict) or set(row) != {'index', 'ok', 'value', 'error_category'}:
            raise TypeError('Iteration result fields mismatch')
        if type(row['index']) is not int or row['index'] != expected_index or type(row['ok']) is not bool:
            raise TypeError('Iteration result index or status mismatch')
        if row['ok']:
            if not isinstance(row['value'], str) or row['error_category'] is not None:
                raise TypeError('Successful result contract mismatch')
            successes.append(row)
        else:
            if row['value'] is not None or row['error_category'] not in ('ValueError', 'TypeError', 'ZeroDivisionError', 'KeyError', 'IndexError', 'OverflowError'):
                raise TypeError('Failed result contract mismatch')
            failures.append(row)
    return {'items': results, 'successes': successes, 'failures': failures,
            'total': len(results), 'succeeded': len(successes), 'failed': len(failures)}
'''
SUMMARY_OUTPUTS={k:{'type':t,'children':None} for k,t in (('items','array[object]'),('successes','array[object]'),('failures','array[object]'),('total','number'),('succeeded','number'),('failed','number'))}


def original_code(code,result_type='string'):
    probe='def main(item: str) -> dict:\n    return {"result": item}\n'
    renamed=probe.replace('def main(', 'def _sierra_calculate(',1)
    tail=wrapped(probe,result_type)[len(MARKER)+len(renamed):]
    if not isinstance(code,str) or len(code.encode('utf-8'))>16000 or not code.startswith(MARKER) or not code.endswith(tail):
        raise ValueError('只汇总完整原逐项结果封装，不忽略手改的错误或结果规则。')
    raw=code[len(MARKER):-len(tail)]
    try:
        tree=ast.parse(raw)
        fns=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        if len(fns)!=1 or fns[0].name!='_sierra_calculate':raise ValueError()
        lines=raw.splitlines(keepends=True);i=fns[0].lineno-1
        lines[i],count=re.subn(r'^def[ \t]+_sierra_calculate(?=[ \t]*\()', 'def main',lines[i],count=1)
        if count!=1:raise ValueError()
        original=''.join(lines)
        if wrapped(original,result_type)!=code:raise ValueError()
    except (SyntaxError,ValueError,IndexError):
        raise ValueError('原逐项结果封装不能完整核对，未覆盖手改或猜测数据结构。') from None
    return original


def original_contract_details(code):
    if isinstance(code,str) and code.startswith(OBJECT_MARKER):
        raw,schema=original_object(code)
        return raw,'object',schema
    raw,kind=original_contract(code)
    return raw,kind,None


def original_contract(code):
    if isinstance(code,str) and code.startswith(OBJECT_MARKER):return original_object(code)[0],'object'
    for kind in ('string','number'):
        try:return original_code(code,kind),kind
        except ValueError:pass
    raise ValueError('原逐项封装未匹配完整文字或数值合同，不猜类型或覆盖手改。')


def summary_code(result_type='string',result_schema=None):
    if result_type=='object':return summary_object(result_schema,SUMMARY_CODE)
    if result_schema is not None:raise ValueError('文字或数值汇总不接收对象Schema。')
    if result_type=='string':return SUMMARY_CODE
    if result_type!='number':raise ValueError('汇总结果须为已声明文字或数值。')
    guard=NUMBER_GUARD.replace("result['result']","row['value']")
    return SUMMARY_CODE.replace("not isinstance(row['value'], str)","not ("+guard+")")


def candidate(task,plan,node_id,acknowledge=False):
    if type(acknowledge)is not bool or not acknowledge:
        raise ValueError('须明确接受增加成功／失败列表和计数的结束输出；只预览，不保存或运行。')
    render(plan)
    if task.get('app_type')!='workflow' or not validate_plan(task,plan)['valid']:
        raise ValueError('须为当前有效的Workflow逐项结果计划，不更换应用类型或修复其它问题。')
    if sorted(n['type'] for n in plan['nodes'])!=['code','end','iteration','start']:
        raise ValueError('本批只在四根节点的原逐项结果之后增加汇总，不改其它消费者或复杂图。')
    parents=[n for n in plan['nodes'] if n['id']==node_id and n['type']=='iteration']
    if len(parents)!=1:raise ValueError('请明确唯一目标迭代，不自动选择。')
    cfg=parents[0]['config'];children=cfg['nodes']
    if len(children)!=1 or children[0]['type']!='code':raise ValueError('正文不再是原单函数逐项结果，未生成汇总。')
    child=children[0];cc=child['config']
    if cc.get('variables')!=[{'variable':'item','value_selector':[node_id,'item']},{'variable':'sierra_index','value_selector':[node_id,'index']}] or cc.get('outputs')!={'outcome':{'type':'object','children':None}} or cfg.get('output_selector')!=[child['id'],'outcome'] or cfg.get('output_type')!='array[object]':
        raise ValueError('原逐项结果绑定、完整输出或数组类型已改变，不能猜测失败清单。')
    raw_code,result_type,result_schema=original_contract_details(cc.get('code'))
    reconstructed=copy.deepcopy(plan);pc=next(n for n in reconstructed['nodes'] if n['id']==node_id)['config'];body=pc['nodes'][0]['config']
    body.update(code=raw_code,variables=[{'variable':'item','value_selector':[node_id,'item']}],outputs={'result':{'type':result_type,'children':None}})
    pc.update(output_selector=[child['id'],'result'],output_type='array['+result_type+']')
    if json.loads(outcome_candidate(task,reconstructed,node_id,True,result_schema)['plan_text'])!=plan:
        raise ValueError('原逐项结果完整计划不一致，不覆盖手改或推测错误策略。')
    end=next(n for n in plan['nodes'] if n['type']=='end');original_output=end['config']['outputs'][0]
    extras=['successes','failures','total','succeeded','failed']
    if original_output['variable'] in extras:raise ValueError('原完整结果字段与新增汇总字段同名，请先明确结束字段名，未自动改名。')
    from .iteration import plan_nodes
    occupied={n['id'] for n in plan_nodes(plan)};summary_id=node_id+'_summary';index=2
    while summary_id in occupied:
        summary_id=node_id+'_summary_'+str(index);index+=1
    code=summary_code(result_type,result_schema)
    result=copy.deepcopy(plan);summary={'id':summary_id,'type':'code','title':'汇总逐项成功与失败','config':{'code_language':'python3','code':code,'variables':[{'variable':'results','value_selector':[node_id,'output']},{'variable':'source_items','value_selector':copy.deepcopy(cfg['iterator_selector'])}],'outputs':copy.deepcopy(SUMMARY_OUTPUTS)}}
    result['nodes'].insert(next(i for i,n in enumerate(result['nodes']) if n['id']==end['id']),summary)
    old_edge=next(e for e in result['edges'] if e['source']==node_id and e['target']==end['id'])
    old_edge['target']=summary_id
    result['edges'].append({'source':summary_id,'target':end['id']})
    final=next(n for n in result['nodes'] if n['id']==end['id'])
    final['config']['outputs'][0]['value_selector']=[summary_id,'items']
    final['config']['outputs'] += [{'variable':k,'value_selector':[summary_id,k]} for k in extras]
    if not validate_plan(task,result)['valid']:raise ValueError('新增汇总不能通过完整计划检查，原草稿保持。')
    return {'plan_text':render(result),'node_id':node_id,'summary_node_id':summary_id,'source_plan_sha256':digest(plan),'candidate_plan_sha256':digest(result),'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'value_type':result_type,'result_schema_sha256':digest(result_schema) if result_schema is not None else None,'added_nodes':1,'added_end_fields':extras,'original_result_field':original_output['variable'],'verification':'local_iteration_summary_draft_only','platform_checked':False,'business_verified':False,'task_changed':False,'network_requested':False}


def register(host):
    from fastapi import APIRouter,HTTPException
    from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
    from uuid import UUID
    from .plan_drafts import DraftRoute,inspect_text
    from .plan_text_codec import parse

    class Preview(BaseModel):
        model_config=ConfigDict(extra='forbid')
        revision:StrictInt=Field(ge=1)
        plan_text:StrictStr=Field(max_length=2_000_000)
        node_id:StrictStr=Field(min_length=1,max_length=256)
        acknowledge_summary_outputs:StrictBool
        request_nonce:UUID

    router=APIRouter(route_class=DraftRoute)
    @router.post('/api/tasks/{item_id}/iteration-summary')
    def prepare(item_id:str,payload:Preview):
        with host.store.lock:
            t=host.get_task(item_id);host.require_revision(t,payload.revision)
            try:
                inspect_text(payload.plan_text)
                result=candidate(t,parse(payload.plan_text),payload.node_id,payload.acknowledge_summary_outputs)
            except (TypeError,KeyError,RecursionError,UnicodeError,OverflowError):
                raise HTTPException(422,'汇总草稿结构或编码超出当前范围，未修改或执行原稿。') from None
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from None
            return {**result,'task_id':item_id,'revision':payload.revision,'request_nonce':str(payload.request_nonce)}
    host.app.include_router(router)
