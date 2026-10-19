import copy,json
import pytest,yaml
from test_api import client
from test_run_diagnostics import recorded,trace,diagnose,REMOTE,APP,OTHER
from app import main
from app.dify import DifyClient,DifyError
from app.diagnostic_graph_source import fingerprint,compare


def graph(task):return yaml.safe_load(main.artifact_path(task).read_text(encoding='utf-8'))['workflow']['graph']


def reader(monkeypatch,g,published=None,callback=None):
    calls=[]
    async def request(self,method,path,**kw):
        calls.append((method,path,kw));assert method=='GET'
        if callback:callback(path)
        if path.endswith('/node-executions'):return trace()
        if path.endswith('/workflows/publish'):
            if isinstance(published,Exception):raise published
            return published if published is not None else {'id':OTHER,'graph':copy.deepcopy(g),'environment_variables':[{'value':'private-variable-secret'}]}
        return {'id':REMOTE,'status':'failed','graph':copy.deepcopy(g),'inputs':{'business':'private-customer-input'},'outputs':{'business':'private-customer-output'}}
    monkeypatch.setattr(DifyClient,'request',request);return calls


def test_actual_execution_published_and_artifact_match_without_graph_payload_retention(client,monkeypatch):
    task,_=recorded(client);g=graph(task);calls=reader(monkeypatch,g)
    response=diagnose(client,task,True);assert response.status_code==200,response.text
    r=response.json();proof=r['source_graph'];assert proof['matched'] and r['current_source'] and r['snapshot_matches_current']
    assert len(calls)==3 and all(APP in path for _,path,_ in calls)
    saved=json.dumps(main.get_task(task['id'])['runs'][-1]['diagnostics']);assert 'private-customer' not in saved and 'private-variable-secret' not in saved
    assert proof['published_workflow_id']==OTHER and proof['execution']['digest']==proof['published']['digest']==proof['artifact']['digest']


def test_actual_old_published_graph_not_current_even_with_same_app_revision(client,monkeypatch):
    task,_=recorded(client);g=graph(task);pub=copy.deepcopy(g);pub['nodes'][1]['data']['code']+='\n# changed published version'
    reader(monkeypatch,g,{'id':OTHER,'graph':pub});r=diagnose(client,task,True).json()
    assert r['snapshot_matches_current'] and not r['current_source'] and r['source_graph']['state']=='different_published_graph'
    assert r['nodes'] and r['trace_state']=='read' and main.get_task(task['id'])['runs'][-1]['status']=='failed'


def test_dify_manual_graph_change_requires_artifact_review_not_automatic_patch(client,monkeypatch):
    task,_=recorded(client);g=graph(task);g['nodes'][1]['data']['code']+='\n# hand change'
    reader(monkeypatch,g);r=diagnose(client,task,True).json();assert r['source_graph']['state']=='different_artifact_graph' and not r['current_source']


def test_published_read_failure_keeps_actual_trace_but_does_not_prove_current(client,monkeypatch):
    task,_=recorded(client);reader(monkeypatch,graph(task),DifyError('Dify HTTP401'))
    r=diagnose(client,task,True).json();assert r['nodes'] and r['trace_state']=='read' and not r['current_source'] and r['source_graph']['state']=='published_read_failed'


@pytest.mark.parametrize('published',[None,{}, {'id':'foreign','graph':{}},{'id':OTHER,'graph':None}])
def test_missing_or_invalid_published_graph_not_empty_success(client,monkeypatch,published):
    task,_=recorded(client);g=graph(task)
    if published is None:
        async def request(self,method,path,**kw):
            return trace() if path.endswith('/node-executions') else None if path.endswith('/workflows/publish') else {'id':REMOTE,'status':'failed','graph':g}
        monkeypatch.setattr(DifyClient,'request',request)
    else:reader(monkeypatch,g,published)
    r=diagnose(client,task,True).json();assert not r['current_source'] and r['source_graph']['state']=='published_unavailable'


def test_top_level_layout_and_storage_order_do_not_change_core_fingerprint(client):
    task,_=recorded(client);g=graph(task);other=copy.deepcopy(g);other['nodes'].reverse();other['edges'].reverse();other['nodes'][0]['position']['x']+=200;other['nodes'][0]['width']=999;other['nodes'][0]['data']['selected']=True;other['viewport']={'x':100,'zoom':.5}
    assert fingerprint(g)==fingerprint(other)


@pytest.mark.parametrize('mutation',['type','code','selector','parent','handle','edge_data'])
def test_core_semantic_or_scope_changes_do_change_fingerprint(client,mutation):
    task,_=recorded(client);g=graph(task);other=copy.deepcopy(g)
    if mutation=='type':other['nodes'][1]['data']['type']='unknown'
    elif mutation=='code':other['nodes'][1]['data']['code']+='\n# code text differs'
    elif mutation=='selector':other['nodes'][1]['data']['variables'][0]['value_selector']=['start','new']
    elif mutation=='parent':other['nodes'][1]['parentId']='start'
    elif mutation=='handle':other['edges'][0]['sourceHandle']='new'
    else:other['edges'][0].setdefault('data',{})['loop_id']='new'
    assert fingerprint(g)['digest']!=fingerprint(other)['digest']


@pytest.mark.parametrize('mutation',['duplicate_node','duplicate_edge','missing_node','bad_data','nan','alias','cycle','deep'])
def test_malformed_graph_is_unknown_not_inferred(client,mutation):
    task,_=recorded(client);g=graph(task)
    if mutation=='duplicate_node':g['nodes'].append(copy.deepcopy(g['nodes'][0]))
    elif mutation=='duplicate_edge':g['edges'].append(copy.deepcopy(g['edges'][0]))
    elif mutation=='missing_node':g['edges'][0]['source']='foreign'
    elif mutation=='bad_data':g['nodes'][0]['data']='private-data'
    elif mutation=='nan':g['nodes'][0]['data']['value']=float('nan')
    elif mutation=='alias':g['nodes'][0]['data']['shared']=g['nodes'][1]['data']
    elif mutation=='cycle':g['cycle']=g
    else:
        x={};g['deep']=x
        for _ in range(65):x['next']={};x=x['next']
    assert fingerprint(g) is None


@pytest.mark.parametrize('mutation',['app','file','artifact_pointer'])
def test_source_changes_during_capture_rejects_save(client,monkeypatch,mutation):
    task,_=recorded(client);g=graph(task);changed=[False]
    def callback(path):
        if not path.endswith('/workflows/publish') or changed[0]:return
        changed[0]=True;current=main.get_task(task['id'])
        if mutation=='app':current['dify_app_id']=OTHER;main.save_task(current)
        elif mutation=='file':main.artifact_path(current).write_text(yaml.safe_dump({'kind':'bad'}),encoding='utf-8')
        else:current['artifact']['created_at']='changed-pointer';main.save_task(current)
    reader(monkeypatch,g,callback=callback);r=diagnose(client,task,True);assert r.status_code==409
    assert not main.get_task(task['id'])['runs'][-1].get('diagnostics')


def test_local_only_records_not_graph_verified_and_does_not_read_remote(client,monkeypatch):
    task,_=recorded(client)
    async def forbidden(*a,**kw):pytest.fail('本地分析不访问Dify')
    monkeypatch.setattr(DifyClient,'request',forbidden)
    r=diagnose(client,task).json();assert r['source_graph']['state']=='not_checked' and r['snapshot_matches_current'] and not r['current_source']


def test_legacy_malformed_artifact_is_unknown_not_a_diagnostic_crash(client):
    task,_=recorded(client);task['artifact']='legacy malformed value';main.save_task(task)
    response=diagnose(client,task);assert response.status_code==200,response.text
    assert response.json()['source_graph']['artifact'] is None and not response.json()['current_source']
