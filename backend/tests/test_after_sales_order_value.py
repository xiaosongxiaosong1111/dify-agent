"""Controlled extraction outputs, no model: blank business values must never query."""
import json
import pytest
from test_after_sales_starter import context,inputs
from app.after_sales_starter import prepare


def graph():return json.loads(prepare(context(),inputs())[0])


def walk(plan,success,order_no,queries):
    """Execute only the repository-owned public order branch after extraction."""
    nodes={n['id']:n for n in plan['nodes']};values={'extract_order':{'__is_success':success,'order_no':order_no}}
    def next_node(source,handle='source'):
        edges=[e for e in plan['edges'] if e['source']==source and e.get('source_handle','source')==handle]
        assert len(edges)==1
        return edges[0]['target']
    current=next_node('extract_order')
    for _ in range(len(nodes)+1):
        node=nodes[current];cfg=node['config']
        if current=='missing_order':return cfg['template']
        if node['type']=='if-else':
            assert len(cfg['cases'])==1 and cfg['cases'][0]['logical_operator']=='and'
            case=cfg['cases'][0];checks=[]
            for c in case['conditions']:
                owner,key=c['variable_selector'];actual=values[owner][key]
                if c['comparison_operator']=='=':checks.append(float(actual)==float(c['value']))
                else:
                    assert c['comparison_operator']=='is' and type(c['value']) is bool
                    checks.append(actual is c['value'])
            current=next_node(current,case['case_id'] if all(checks) else 'false')
        elif node['type']=='code':
            assert current in {'validate_order','order_lookup'}
            if current=='order_lookup':queries.append(current)
            scope={};exec(cfg['code'],scope)
            arguments={v['variable']:values[v['value_selector'][0]][v['value_selector'][1]] for v in cfg['variables']}
            values[current]=scope['main'](**arguments)
            if current=='order_lookup':return values[current]['result']
            current=next_node(current)
        else:pytest.fail('Unexpected order branch node')
    pytest.fail('Order branch did not terminate')


@pytest.mark.parametrize('value',['',' ',' \t\r\n ','\u3000'])
def test_success_flag_with_blank_order_uses_fixed_question_without_query(value):
    calls=[]
    assert walk(graph(),1,value,calls)==inputs()['missing_order_reply']
    assert calls==[]


@pytest.mark.parametrize('value',['','DEMO-001'])
def test_extraction_failure_still_bypasses_business_values(value):
    calls=[]
    assert walk(graph(),0,value,calls)==inputs()['missing_order_reply'] and calls==[]


@pytest.mark.parametrize('value',['DEMO-001',' DEMO-001 ','UNLISTED-DEMO'])
def test_nonblank_known_and_unknown_orders_still_query_once(value):
    calls=[];answer=walk(graph(),1,value,calls)
    assert calls==['order_lookup'] and answer.startswith('【模拟订单查询，非真实订单】')
    assert ('已发货' in answer) == (value.strip()=='DEMO-001')


@pytest.mark.parametrize('value',[None,7,{}])
def test_invalid_type_stops_before_query_without_pretending_missing(value):
    calls=[]
    with pytest.raises(ValueError):walk(graph(),1,value,calls)
    assert calls==[]


def test_extraction_guard_is_unchanged_and_business_check_is_separate():
    plan=graph();nodes={n['id']:n for n in plan['nodes']}
    assert nodes['check_order']['config']['cases']==[{'case_id':'extracted','logical_operator':'and','conditions':[
        {'variable_selector':['extract_order','__is_success'],'varType':'number','comparison_operator':'=','value':'1'}]}]
    assert any(e['source']=='check_order' and e['source_handle']=='extracted' and e['target']=='validate_order' for e in plan['edges'])
    assert not any(e['source']=='check_order' and e['target']=='order_lookup' for e in plan['edges'])
