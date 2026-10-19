import copy,json
import pytest,yaml
from test_api import client
from test_workflow_plan import plan_task
from test_file_inputs import plan as file_plan
from test_file_model_run import model_document
from test_file_structured_run import structured,shape
from test_file_schema_guard import guarded
from test_file_join import joined,POLICY
from test_file_joined_guard import document as combined
from test_optional_file import optional_plan
from app.file_structured_template import joined_template
from app.workflow_plan import compile_workflow_plan
from app.file_run_flow import describe
from app.dsl_roundtrip import validate_preserved
from app.file_capabilities import catalog
from app import main


def compiled(plan):
 text,checked=compile_workflow_plan(plan_task(plan));assert checked['valid'],checked
 return yaml.safe_load(text)


def graph(sid):
 if sid=='document_extraction':return compiled(file_plan('file-list'))
 if sid=='document_model':return yaml.safe_load(model_document())
 if sid=='document_model_object':
  root=yaml.safe_load(model_document());structured(root);return root
 if sid=='document_list_model':return joined()[1]
 if sid=='document_list_model_object':return compiled(joined_template(json.dumps(shape()),POLICY,['.txt']))
 if sid=='document_model_guarded_object':
  root=yaml.safe_load(model_document());guarded(root);return root
 if sid=='document_list_model_guarded_object':return combined()
 if sid=='document_optional_extraction':return compiled(optional_plan('exists'))
 raise AssertionError('unknown catalog route')


@pytest.mark.parametrize('sid',[r['id'] for r in catalog()['scenarios']])
def test_each_advertised_file_route_has_exact_preserved_graph_and_runtime_description(sid):
 row=next(r for r in catalog()['scenarios'] if r['id']==sid);root=graph(sid);before=copy.deepcopy(root)
 assert validate_preserved(root)['valid'];flow=describe(root)
 assert flow['scenario']==sid and flow['schema_version']==row['flow_schema_version'] and len(flow['node_types'])==row['node_count']
 assert flow['model_egress']==row['includes_model'] and bool(flow.get('join_policy'))==row['includes_join'] and bool(flow.get('strict_guard'))==row['includes_guard']
 assert row['platform_business_verified'] is False and root==before


@pytest.mark.parametrize('kind',['workflow','advanced-chat','agent'])
def test_scope_is_type_specific_read_only_and_never_resource_or_business_verification(client,monkeypatch,kind):
 before=copy.deepcopy(main.store.list('task'))
 def forbidden(*args,**kw):pytest.fail('范围读取不能解密或联网')
 monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.DifyClient,'request',forbidden);monkeypatch.setattr(main,'call_model',forbidden)
 r=client.get('/api/capabilities',params={'app_type':kind});assert r.status_code==200,r.text;v=r.json();assert v['schema_version']==2 and v['verification']=='compiler_scope'
 if kind=='workflow':
  f=v['file_workflows'];assert len(f['scenarios'])==8 and len(f['formats'])==6 and f['network_requested'] is False and f['platform_business_verified'] is False
  assert '用户文件上传与OCR' not in v['not_adapted'] and '人工输入／审批节点' not in v['not_adapted']
  assert any('指定身份' in text for text in v['not_adapted']) and any('真实自然定时' in text for text in v['not_adapted'])
 else:assert v['file_workflows'] is None
 assert main.store.list('task')==before


def test_catalog_does_not_share_mutable_rows_or_silently_advertise_pdf_upload():
 first=catalog();first['scenarios'][0]['platform_business_verified']=True;first['formats'][0]['extension']='.pdf'
 second=catalog();assert second['platform_business_verified'] is False and all(r['platform_business_verified'] is False for r in second['scenarios'])
 assert [r['extension'] for r in second['formats']]==['.txt','.md','.csv','.json','.yaml','.yml']
