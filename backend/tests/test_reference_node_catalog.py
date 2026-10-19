import copy,yaml
import pytest
from test_api import client,approved
from app.workflow_plan import compile_workflow_plan
from app.reference_dsl import summarize
from test_question_classifier import plan as classifier_plan
from test_parameter_extractor import plan as extractor_plan
from test_list_operator import plan as list_plan
from test_document_extractor import plan as document_plan
from test_reference_dsl import preview,adopt
from app import main

@pytest.mark.parametrize('factory,kind,fields,has_model',[
 (classifier_plan,'question-classifier',{'classes','query_variable_selector','instruction'},True),
 (extractor_plan,'parameter-extractor',{'parameters','query','reasoning_mode'},True),
 (list_plan,'list-operator',{'filter_by','extract_by','limit'},False),
 (document_plan,'document-extractor',{'variable_selector','is_array_file'},False),
])
def test_known_types_and_actual_rules_are_structurally_identified_without_runtime_claim(client,factory,kind,fields,has_model):
 task=approved(client);task['workflow_plan']=factory();content,result=compile_workflow_plan(task);assert result['valid'],result
 root=yaml.safe_load(content);before=copy.deepcopy(root);value=summarize(content,'workflow','reference.yaml');node=next(n for n in value['nodes'] if n['type']==kind)
 assert node['planning_supported_type'] and node['label']!='未适配节点' and fields<={d['field'] for d in node['details']}
 assert any(row['node_id']==node['id'] and row['kind']=='model' for row in value['resources'])==has_model
 assert value['verification']=='local_structure_only' and not any(f'类型 {kind} 尚未适配' in w for w in value['warnings']) and root==before
 assert any('未核对' in w for w in value['warnings'])

def test_document_reference_preview_and_material_adoption_are_local_and_preserve_file(client,monkeypatch):
 task=approved(client);staged=copy.deepcopy(task);staged['workflow_plan']=document_plan();content,result=compile_workflow_plan(staged);assert result['valid'];calls=[]
 async def unexpected(*a,**kw):calls.append(1);pytest.fail('结构预览与材料采纳不得调用模型')
 monkeypatch.setattr(main,'call_model',unexpected);before=copy.deepcopy(main.get_task(task['id']));response=preview(client,task,content);assert response.status_code==200,response.text
 assert main.get_task(task['id'])==before and not calls
 response=adopt(client,task);assert response.status_code==200,response.text;updated=response.json()
 material=updated['materials'][-1];assert material['reference_mode']=='borrow' and '文档文件提取' in material['text'] and 'variable_selector' in material['text']
 assert updated['app_type']==task['app_type'] and not updated['requirements_confirmed'] and updated['dify_app_id'] is None and not calls
