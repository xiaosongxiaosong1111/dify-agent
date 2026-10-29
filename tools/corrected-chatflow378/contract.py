"""Compile the existing opt-in template; no model or platform operations."""
import copy
import json
import yaml
from common import require


def build(h,fixture):
    from app.after_sales_starter import prepare
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    config=copy.deepcopy(h.CONFIG_DEFAULT);config.update(copy.deepcopy(fixture['configuration']))
    task={'id':'public-contract','name':fixture['task_name'],'app_type':'advanced-chat','revision':1,'requirements':fixture['requirements'],'configuration':config}
    text,validation=prepare(task,fixture['inputs']);require(validation['valid'],'Public template invalid')
    original=json.loads(text);modified=copy.deepcopy(original);changes=0
    answer=next(n for n in original['nodes'] if n['id']=='grounded_answer')['config']
    require(answer.get('context_variable_selector')==['retrieve','result'] and '{{#context#}}' in answer.get('user_prompt',''),'Corrected retrieval context must enter answer prompt')
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
