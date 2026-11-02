"""Exact saved model graph, with explicitly reviewed manual configuration; no model call."""
import copy,json
import yaml
from common import PROJECT,ReadOnly,digest,sha,require,uuid

MODEL_SHA='f7ac6d10dd986fffbfbe410ded616d4956ec7253d70fdf194ee49f3c1e39435c'
RESPONSE_SHA='c1cbc058476f4bcef1a2421dcca0a868f4ad1a80969b63957467ff62988e2b8b'
REVIEW_SHA='2d3f2a0e0ca10dd8217a41de92047ad6a28990bf697804be3c03475e196c59a3'

def build(h,fixture):
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    source=PROJECT/'work/offline-candidate409';raw=PROJECT/'work/reviewed-planning408/live-output/model-response-1.txt'
    require(sha(raw)==RESPONSE_SHA and sha(source/'root-review.json')==REVIEW_SHA,'Actual model/agent review source changed')
    rows=ReadOnly(source/'data').list('task');require(len(rows)==1,'Source Task ambiguous');saved=rows[0]
    plan=json.loads(raw.read_text('utf-8'));require(digest(plan)==digest(saved['workflow_plan'])==MODEL_SHA and saved['id']=='25ae7940-021c-4106-8779-d6e3668ededc' and saved['revision']==7 and saved['plan_source']=='manual','Exact reviewed original model graph required')
    require(fixture['source_model_plan_sha256']==MODEL_SHA and fixture['source_model_response_sha256']==RESPONSE_SHA and fixture['source_review_sha256']==REVIEW_SHA,'Fixture source changed')
    require(fixture['cases']==saved['test_cases'] and {k:v for k,v in fixture['requirements'].items() if k!='tests'}=={k:v for k,v in saved['requirements'].items() if k!='tests'},'Current saved cases/business requirements changed')
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(copy.deepcopy(fixture['configuration']))
    require({k:v for k,v in config.items() if k not in {'resource_plan','assistant_provider_id'}}=={k:v for k,v in saved['configuration'].items() if k not in {'resource_plan','assistant_provider_id'}},'Only explicit new resource scope and empty builder selection may differ from270 configuration')
    require(config.get('assistant_provider_id') is None,'New zero-builder-model Task must not select or read its Key')
    require(config['mock_dependency_bindings'][0]['node_id']=='lookup','Explicit reviewed query position required')
    task={'id':'public-contract','name':fixture['task_name'],'app_type':'advanced-chat','revision':1,'requirements':fixture['requirements'],'configuration':config,'workflow_plan':plan}
    content,checked=compile_workflow_plan(task);require(checked['valid'],'Reviewed model graph/config no longer compiles');native=yaml.safe_load(content)
    require(len(plan['nodes'])==22 and len(plan['edges'])==23,'Unexpected graph shape')
    return {'configuration':config,'original':{'plan':plan,'native':native,'core':core(native['workflow'])},'source_model_plan_sha256':MODEL_SHA,'manual_configuration_review':True}


def bind_owner(h,fixture,contract,owner):
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    from uuid import uuid5,NAMESPACE_URL
    require(uuid(owner) and 'owner_task_id' not in contract,'Unique new Task owner required')
    require(digest(contract)==digest(build(h,fixture)),'Frozen reviewed prototype changed')
    task={'id':owner,'name':fixture['task_name'],'app_type':'advanced-chat','revision':1,'requirements':fixture['requirements'],'configuration':contract['configuration'],'workflow_plan':contract['original']['plan']}
    content,checked=compile_workflow_plan(task);require(checked['valid'],'Owner native graph invalid');native=yaml.safe_load(content);expected=copy.deepcopy(contract['original']['native'])
    for row in expected['workflow']['conversation_variables']:row['id']=str(uuid5(NAMESPACE_URL,'sierra:conversation:'+owner+':'+row['name']))
    require(native==expected,'Only two deterministic state IDs may change')
    contract['original']={'plan':contract['original']['plan'],'native':native,'core':core(native['workflow'])};contract['owner_task_id']=owner
