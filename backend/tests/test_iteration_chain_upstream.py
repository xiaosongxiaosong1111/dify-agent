"""Fixed graph fixtures only, never execute upstream code, HTTP, models or Dify."""
import copy,json
from uuid import uuid4
import pytest,yaml
from test_api import client,approved
from test_iteration import task
from test_iteration_chain import chain_plan
from test_aggregation import merge_plan
from app import main
from app.iteration_chain import candidate,ChainStageError,MARKER
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.dsl_roundtrip import validate_preserved


def node(p,nid):return next(n for n in p['nodes'] if n['id']==nid)


def upstream_plan(kind):
    p=chain_plan(True);parse=node(p,'parse')
    if kind=='branch':
        prefix=merge_plan();prefix['nodes'][2]['config']['template']='[]';prefix['nodes'][3]['config']['template']='["2","0","bad"]'
        p['nodes']=prefix['nodes'][:-1]+p['nodes'][1:]
        p['edges']=prefix['edges'][:-1]+[{'source':'merge','target':'parse'}]+p['edges'][1:]
        parse['config']['variables'][0]['value_selector']=['merge','output']
        return p
    if kind=='code':
        pre={'id':'pre','type':'code','title':'保留上游清洗','config':{'code_language':'python3','code':'def main(raw):\n    return {"raw": raw.strip()}\n','variables':[{'variable':'raw','value_selector':['start','items_json']}],'outputs':{'raw':{'type':'string','children':None}}}}
        output='raw'
    elif kind=='template':
        pre={'id':'pre','type':'template-transform','title':'保留上游模板','config':{'template':'{{ raw }}','variables':[{'variable':'raw','value_selector':['start','items_json'],'value_type':'string'}]}};output='output'
    else:
        pre={'id':'pre','type':'http-request','title':'仅静态保留的HTTP','config':{'method':'get','url':'https://api.acme.test/developer-items','headers':'Accept: application/json','params':'','timeout':{'connect':10,'read':30,'write':30},'variables':[]}};output='body'
    p['nodes'].insert(1,pre);p['edges'][0]['target']='pre';p['edges'].insert(1,{'source':'pre','target':'parse'})
    parse['config']['variables'][0]['value_selector']=['pre',output]
    return p


def propose(p,summary=False,operation='wrap'):
    return candidate(task(p),p,'batch',True,summary,summary,operation)


@pytest.mark.parametrize('kind',['code','template','branch','http'])
@pytest.mark.parametrize('summary',[False,True])
def test_keep_complete_upstream_graph_and_compile_native_without_executing(kind,summary):
    p=upstream_plan(kind);before=copy.deepcopy(p);checked=validate_plan(task(p),p);assert checked['valid'],checked
    value=propose(p,summary);out=json.loads(value['plan_text']);assert p==before
    preserved=[n for n in p['nodes'] if n['id'] not in ('batch','end')]
    assert preserved==[n for n in out['nodes'] if n['id'] not in ('batch','end',value['summary_node_id'])]
    expected_edges=copy.deepcopy(p['edges'])
    if summary:
        next(e for e in expected_edges if e['source']=='batch')['target']=value['summary_node_id'];expected_edges.append({'source':value['summary_node_id'],'target':'end'})
    assert out['edges']==expected_edges
    assert all(c['config']['code'].startswith(MARKER) for c in node(out,'batch')['config']['nodes'])
    native,validation=compile_workflow_plan(task(out));assert validation['valid'],validation
    assert validate_preserved(yaml.safe_load(native))['valid']
    original_native,old_validation=compile_workflow_plan(task(p));assert old_validation['valid']
    old_nodes={n['id']:n for n in yaml.safe_load(original_native)['workflow']['graph']['nodes']}
    new_nodes={n['id']:n for n in yaml.safe_load(native)['workflow']['graph']['nodes']}
    # Positions may shift for the new summary; the upstream native data stays exact.
    for n in preserved:assert old_nodes[n['id']]['data']==new_nodes[n['id']]['data']


@pytest.mark.parametrize('kind',['code','template','branch','http'])
def test_append_rebuilds_complete_graph_and_retains_upstream_manual_settings(kind):
    p=json.loads(propose(upstream_plan(kind))['plan_text']);node(p,'parse')['title']='手动保留解析标题'
    source=node(p,'parse')['config']['variables'][0]['value_selector'][0]
    if node(p,source)['type']=='http-request':node(p,source)['config']['timeout']['read']=42
    before=copy.deepcopy(p);out=json.loads(propose(p,True,'append_summary')['plan_text'])
    assert p==before and node(out,'batch')==node(p,'batch')
    for n in p['nodes']:
        if n['id']!='end':assert node(out,n['id'])==n


@pytest.mark.parametrize('change',['second_end','after_chain','side_consumer','source_field','non_dominating_branch'])
def test_no_silent_drop_or_reinterpretation_of_other_paths_and_consumers(change):
    p=upstream_plan('branch' if change=='non_dominating_branch' else 'code')
    if change=='second_end':
        p['nodes'].append({'id':'other_end','type':'end','config':{'outputs':[{'variable':'raw','value_selector':['start','items_json']}]}});p['edges'].append({'source':'start','target':'other_end'})
    elif change in ('after_chain','side_consumer'):
        p['nodes'].insert(-1,{'id':'consume','type':'code','config':{'code_language':'python3','code':'def main(rows):\n return {"size": len(rows)}\n','variables':[{'variable':'rows','value_selector':['batch','output']}],'outputs':{'size':{'type':'number','children':None}}}})
        p['edges'].extend([{'source':'batch','target':'consume'},{'source':'consume','target':'end'}])
        if change=='after_chain':
            p['edges']=[e for e in p['edges'] if (e['source'],e['target'])!=('batch','end')];node(p,'end')['config']['outputs'][0]['value_selector']=['consume','size']
    elif change=='source_field':
        cfg=node(p,'parse')['config'];cfg['outputs']['other']=cfg['outputs'].pop('items');cfg['code']=cfg['code'].replace('return {"items": items}','return {"other": items}');node(p,'batch')['config']['iterator_selector']=['parse','other']
    else:node(p,'parse')['config']['variables'][0]['value_selector']=['ask','output']
    before=copy.deepcopy(p)
    if change!='non_dominating_branch':assert validate_plan(task(p),p)['valid']
    else:assert not validate_plan(task(p),p)['valid']
    with pytest.raises(ValueError) as caught:propose(p)
    assert not isinstance(caught.value,ChainStageError) and p==before


@pytest.mark.parametrize('kind',['code','branch','http'])
def test_upstream_api_is_stateless_and_no_resource_or_model_call(client,monkeypatch,kind):
    t=approved(client);before=copy.deepcopy(main.store.get('task',t['id']));p=upstream_plan(kind)
    def forbidden(*a,**kw):raise AssertionError('No upstream execution or model/Dify access')
    monkeypatch.setattr(main,'call_model',forbidden);monkeypatch.setattr(main,'DifyClient',forbidden)
    payload={'revision':t['revision'],'plan_text':json.dumps(p),'node_id':'batch','acknowledge_chain_contract':True,'include_summary':True,'acknowledge_summary_outputs':True,'request_nonce':str(uuid4())}
    response=client.post(f"/api/tasks/{t['id']}/iteration-chain-outcomes",json=payload);assert response.status_code==200,response.text
    value=response.json();assert all(value[k] is False for k in ('task_changed','network_requested','platform_checked','business_verified'))
    out=json.loads(value['plan_text']);assert node(out,'parse')==node(p,'parse') and main.store.get('task',t['id'])==before


def test_known_step_diagnostics_remain_correct_with_arbitrary_root_order_and_upstream():
    p=upstream_plan('branch');node(p,'batch')['config']['nodes'][1]['config']['code']='def main(value):\n print("private")\n return {"result": 1}\n'
    p['nodes'].reverse();before=copy.deepcopy(p)
    with pytest.raises(ChainStageError) as caught:propose(p)
    assert caught.value.diagnostic()=={'code':'calculation_scope','stage_position':2,'stage_count':3}
    assert p==before and 'private' not in str(caught.value)
