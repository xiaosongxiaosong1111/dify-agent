"""Compile the existing opt-in template; no model or platform operations."""
import copy
import json
import yaml
from common import require


def build(h,fixture):
    from app.after_sales_starter import prepare,ORDER_VALUE_CODE,FOLLOWUP_CODE
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(copy.deepcopy(fixture['configuration']))
    task={'id':'public-contract','name':fixture['task_name'],'app_type':'advanced-chat','revision':1,'requirements':fixture['requirements'],'configuration':config}
    text,validation=prepare(task,fixture['inputs']);require(validation['valid'],'Public template invalid')
    original=json.loads(text);modified=copy.deepcopy(original);changes=0
    answer=next(n for n in original['nodes'] if n['id']=='grounded_answer')['config']
    require(answer.get('context_variable_selector')==['retrieve','result'] and '{{#context#}}' in answer.get('user_prompt',''),'Corrected retrieval context must enter answer prompt')
    require(all(word in answer.get('system_prompt','') for word in ('适用条件','政策编号','结论')),'Policy completeness instruction must remain explicit')
    nodes={n['id']:n for n in original['nodes']};edges={(e['source'],e.get('source_handle','source'),e['target']) for e in original['edges']}
    intent=nodes['intent']['config'];order=next(c for c in intent['classes'] if c['id']=='order')
    require('本会话历史' in intent['instruction'] and '不把孤立编号自动当订单' in intent['instruction'] and '被追问订单号后补充订单号' in order['name'],'Bounded continuation classification must remain explicit')
    required={('check_order','extracted','validate_order'),('validate_order','source','check_order_value'),('check_order_value','has_order','order_lookup'),('check_order_value','false','request_order_wait')}
    guard=nodes.get('validate_order',{}).get('config',{})
    require(len(nodes)==23 and len(edges)==24 and required<=edges and ('check_order','extracted','order_lookup') not in edges and guard.get('code')==ORDER_VALUE_CODE,'Business value guard missing or bypassed')
    required_state={('start','source','order_followup'),('order_followup','source','consume_order_wait'),('consume_order_wait','source','route_order_followup'),('route_order_followup','continue_order','extract_order'),('route_order_followup','false','intent'),('check_order','false','request_order_wait'),('request_order_wait','source','missing_order')}
    states=original.get('conversation_variables',[])
    require(len(states)==2 and {r['name'] for r in states}=={'order_wait_requested','order_wait_consumed'} and all(r['var_type']=='boolean' and r['initial_value'] is False and r['persistence_policy']=='per_conversation' and r['unwritten_policy']=='retain_current' for r in states),'Exact initial isolated boolean states required')
    require(required_state<=edges and nodes['order_followup']['config']['code']==FOLLOWUP_CODE,'Deterministic followup route required')
    writers={n['id']:n['config']['items'] for n in nodes.values() if n['type']=='assigner'}
    require(writers=={'consume_order_wait':[{'variable_selector':['conversation','order_wait_consumed'],'input_type':'variable','operation':'over-write','value':['order_followup','consume_value']}],'request_order_wait':[{'variable_selector':['conversation','order_wait_requested'],'input_type':'variable','operation':'over-write','value':['order_followup','next_request']}]},'Only two reviewed state writers allowed')
    for node in modified['nodes']:
        key='template' if node['id']=='no_hit' else 'system_prompt' if node['id']=='grounded_answer' else None
        if key:
            before=node['config'][key];require(before.count(fixture['inputs']['no_hit_reply'])==1,'Fixed wording not unique')
            node['config'][key]=before.replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply']);changes+=1
    require(changes==2,'Expected two literal changes')
    value={'configuration':config}
    for name,plan in [('original',original),('modified',modified)]:
        content,checked=compile_workflow_plan({**task,'workflow_plan':plan});require(checked['valid'],'Changed template invalid')
        native=yaml.safe_load(content);value[name]={'plan':plan,'native':native,'core':core(native['workflow'])}
    return value


def bind_owner(h,fixture,contract,owner):
    """Materialize only deterministic declaration IDs, without editing frozen files."""
    from common import digest,uuid
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    from uuid import uuid5,NAMESPACE_URL
    require(uuid(owner) and 'owner_task_id' not in contract,'Unique new Task owner required')
    require(digest(contract)==digest(build(h,fixture)),'Frozen prototype contract changed')
    updated={}
    for version in ('original','modified'):
        task={'id':owner,'name':fixture['task_name'],'app_type':'advanced-chat','revision':1,'requirements':fixture['requirements'],'configuration':contract['configuration'],'workflow_plan':contract[version]['plan']}
        content,checked=compile_workflow_plan(task);require(checked['valid'],'Owner native graph invalid')
        native=yaml.safe_load(content);expected=copy.deepcopy(contract[version]['native'])
        for row in expected['workflow']['conversation_variables']:
            row['id']=str(uuid5(NAMESPACE_URL,'sierra:conversation:'+owner+':'+row['name']))
        require(native==expected,'Only two deterministic state IDs may change')
        updated[version]={'plan':contract[version]['plan'],'native':native,'core':core(native['workflow'])}
    contract.update(updated);contract['owner_task_id']=owner
