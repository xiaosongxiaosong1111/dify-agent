"""Controlled models, real repository code/state routing; never physical HTTP."""
import copy,json,re
import pytest,yaml
from test_after_sales_starter import context,inputs
from app.after_sales_starter import prepare
from app.workflow_plan import compile_workflow_plan
from app.dsl_roundtrip import validate_preserved

def graph():return json.loads(prepare(context(),inputs())[0])
def state(plan):return {r['name']:r['initial_value'] for r in plan.get('conversation_variables',[])}
def pending(s):return s.get('order_wait_requested')!=s.get('order_wait_consumed')

def turn(plan,query,s,category='order',order_no='',success=1,forbid_classifier=False):
    nodes={n['id']:n for n in plan['nodes']};values={'sys':{'query':query},'conversation':s};seen=[];current='start'
    def nxt(source,handle='source'):
        edges=[e for e in plan['edges'] if e['source']==source and e.get('source_handle','source')==handle]
        assert len(edges)==1
        return edges[0]['target']
    for _ in range(len(nodes)+1):
        node=nodes[current];cfg=node['config'];seen.append(current);kind=node['type']
        if kind=='start':current=nxt(current)
        elif kind=='question-classifier':
            if forbid_classifier:pytest.fail('Bare ID was sent back to classifier despite a pending question')
            current=nxt(current,category)
        elif kind=='parameter-extractor':values[current]={'__is_success':success,'order_no':order_no};current=nxt(current)
        elif kind=='code':
            scope={};exec(cfg['code'],scope)
            args={v['variable']:values[v['value_selector'][0]][v['value_selector'][1]] for v in cfg['variables']}
            values[current]=scope['main'](**args);current=nxt(current)
        elif kind=='assigner':
            for item in cfg['items']:
                assert item['operation']=='over-write'
                value=item['value'] if item['input_type']=='constant' else values[item['value'][0]][item['value'][1]]
                s[item['variable_selector'][1]]=value
            current=nxt(current)
        elif kind=='if-else':
            case=cfg['cases'][0];assert case['logical_operator']=='and';matches=[]
            for c in case['conditions']:
                actual=values[c['variable_selector'][0]][c['variable_selector'][1]]
                matches.append(float(actual)==float(c['value']) if c['comparison_operator']=='=' else actual is c['value'])
            current=nxt(current,case['case_id'] if all(matches) else 'false')
        elif kind=='knowledge-retrieval':values[current]={'result':[]};current=nxt(current)
        elif kind=='template-transform':values[current]={'output':cfg['template']};current=nxt(current)
        elif kind=='answer':
            answer=re.sub(r'\{\{#([\w-]+)\.([\w-]+)#\}\}',lambda m:values[m[1]][m[2]],cfg['answer'])
            return answer,seen
        else:pytest.fail('Unexpected node in controlled public path')
    pytest.fail('Route did not terminate')

def ask(plan,s):
    answer,seen=turn(plan,'我想查询订单但没有提供订单号',s)
    assert answer==inputs()['missing_order_reply'] and 'order_lookup' not in seen

def test_waiting_id_deterministically_bypasses_classifier_that_would_clarify():
    p=graph();s=state(p);ask(p,s)
    answer,seen=turn(p,'DEMO-001',s,order_no='DEMO-001',forbid_classifier=True)
    assert answer=='【模拟订单查询，非真实订单】合成样例：已发货。' and 'order_lookup' in seen
    assert not pending(s)

def test_isolated_id_in_new_conversation_is_not_forced_into_order_branch():
    p=graph();s=state(p);answer,seen=turn(p,'DEMO-001',s,category='clarify')
    assert answer==inputs()['clarify_reply'] and 'intent' in seen and 'order_lookup' not in seen

def test_waiting_is_per_conversation_not_shared():
    p=graph();a=state(p);b=state(p);ask(p,a);assert pending(a) and not pending(b)
    assert turn(p,'DEMO-001',b,category='clarify')[0]==inputs()['clarify_reply']
    assert pending(a) and not pending(b)
    assert 'order_lookup' in turn(p,'DEMO-001',a,order_no='DEMO-001',forbid_classifier=True)[1]

@pytest.mark.parametrize('query,category',[('查看售后政策','faq'),('预订机票','clarify')])
def test_explicit_new_topic_consumes_waiting_and_still_uses_classifier(query,category):
    p=graph();s=state(p);ask(p,s);answer,seen=turn(p,query,s,category=category)
    assert 'intent' in seen and 'order_lookup' not in seen and not pending(s)
    assert answer==inputs()['no_hit_reply' if category=='faq' else 'clarify_reply']

@pytest.mark.parametrize('query',['DEMO-001','UNLISTED-DEMO',' A2_3-4 ','9'])
def test_only_explicit_waiting_identifier_path_skips_classifier(query):
    p=graph();s=state(p);ask(p,s)
    answer,seen=turn(p,query,s,order_no=query.strip(),forbid_classifier=True)
    assert 'order_lookup' in seen and answer.startswith('【模拟订单查询，非真实订单】') and not pending(s)

@pytest.mark.parametrize('query',['','A B','-BAD','１２３','A'*65,'查看政策'])
def test_non_identifier_turn_is_delegated_to_classifier(query):
    p=graph();s=state(p);ask(p,s);answer,seen=turn(p,query,s,category='clarify')
    assert 'intent' in seen and 'order_lookup' not in seen and not pending(s)

def test_still_missing_reopens_exactly_one_waiting_question():
    p=graph();s=state(p);ask(p,s);assert pending(s)
    assert turn(p,'DEMO-001',s,order_no='',forbid_classifier=True)[0]==inputs()['missing_order_reply']
    assert pending(s)
    assert 'order_lookup' in turn(p,'DEMO-001',s,order_no='DEMO-001',forbid_classifier=True)[1]
    assert not pending(s)

def test_native_boolean_declarations_and_unique_writers_roundtrip():
    p=graph();before=copy.deepcopy(p);text,checked=compile_workflow_plan({**context(),'workflow_plan':p});assert checked['valid']
    native=yaml.safe_load(text);rows=native['workflow']['conversation_variables']
    assert len(rows)==2 and all(r['value_type']=='boolean' and r['value'] is False for r in rows)
    writes=[i['variable_selector'][1] for n in p['nodes'] if n['type']=='assigner' for i in n['config']['items']]
    assert len(writes)==len(set(writes))==2 and validate_preserved(native)['valid'] and p==before

@pytest.mark.parametrize('query,requested,consumed',[(None,False,False),('DEMO-001',0,False),('DEMO-001',True,'false')])
def test_followup_router_does_not_coerce_query_or_boolean_state(query,requested,consumed):
    cfg=next(n for n in graph()['nodes'] if n['id']=='order_followup')['config'];scope={};exec(cfg['code'],scope)
    with pytest.raises(ValueError):scope['main'](query,requested,consumed)
