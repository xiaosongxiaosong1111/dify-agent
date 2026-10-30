"""Exact saved model graph, with explicitly reviewed manual configuration; no model call."""
import copy,json
import yaml
from common import PROJECT,ReadOnly,digest,sha,require,uuid

MODEL_SHA='1c7fd3e3d672f2d7b228453945f2379defcceaf265be72399fcea46e491fd5c4'
RESPONSE_SHA='518b17298851e2cb1f999c233fab4c133f2b1fe0b86adfdf073155bb165abbdf'
REVIEW_SHA='0b0f36c3b85f9747c5af6553254275a932b38a9cea3f78f13f16689db7ca55d2'

def build(h,fixture):
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    source=PROJECT/'work/offline-candidate405';raw=PROJECT/'work/reviewed-chatflow401/live-output/model-response-1.txt'
    require(sha(raw)==RESPONSE_SHA and sha(source/'root-review.json')==REVIEW_SHA,'Actual model/agent review source changed')
    rows=ReadOnly(source/'data').list('task');require(len(rows)==1,'Source Task ambiguous');saved=rows[0]
    plan=json.loads(raw.read_text('utf-8'));require(digest(plan)==digest(saved['workflow_plan'])==MODEL_SHA and saved['id']=='49fdee89-a30f-4e32-ab90-ea3aeb447734' and saved['revision']==6 and saved['plan_source']=='manual','Exact reviewed original model graph required')
    require(fixture['source_model_plan_sha256']==MODEL_SHA and fixture['source_model_response_sha256']==RESPONSE_SHA and fixture['source_review_sha256']==REVIEW_SHA,'Fixture source changed')
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(copy.deepcopy(fixture['configuration']))
    require({k:v for k,v in config.items() if k not in {'resource_plan','assistant_provider_id'}}=={k:v for k,v in saved['configuration'].items() if k not in {'resource_plan','assistant_provider_id'}},'Only explicit new resource scope and empty builder selection may differ from264 configuration')
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
