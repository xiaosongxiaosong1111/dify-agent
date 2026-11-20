"""Compile only actual root-reviewed model candidates; never synthesize a live graph."""
import copy
from common import digest,require

def replace_text(value,old,new):
    if isinstance(value,dict):return {k:replace_text(v,old,new) for k,v in value.items()}
    if isinstance(value,list):return [replace_text(v,old,new) for v in value]
    return value.replace(old,new) if isinstance(value,str) else value

def register(h,task,version,receipt,b,fixture,contract):
    from app.workflow_plan import compile_workflow_plan
    from app.workflow_publication import core
    import yaml
    p=task.get('workflow_plan');require(isinstance(p,dict) and digest(p) in b.candidates,'Only archived model candidate')
    require(receipt.get('decision')=='proceed' and receipt.get('actor') in {'agent_delegated','synthetic_protocol'},'Root content review missing')
    if version=='modified':
        before=contract['original']['plan'];old=fixture['inputs']['no_hit_reply'];new=fixture['changed_no_hit_reply']
        expected=replace_text(before,old,new)
        require(p==expected and p!=before,'Modified candidate must preserve complete original graph except literal')
        terminals=[n for n in before['nodes'] if n['type'] in {'template-transform','answer'} and old in str(n.get('config'))]
        llms=[n for n in before['nodes'] if n['type']=='llm' and old in str(n.get('config'))]
        require(terminals and llms,'Original direct and grounded fallback both required')
    raw,checked=compile_workflow_plan(task);require(checked['valid'],'Candidate compile refused')
    native=yaml.safe_load(raw);require(native['app']['mode']=='advanced-chat','Wrong type')
    for n in native['workflow']['graph']['nodes']:
        data=n['data']
        require(data['type']!='http-request','No real order HTTP integration approved')
        if 'model' in data:
            m=data['model'];params=m['completion_params'];cfg=fixture['configuration']
            require(m['provider']==cfg['dify_model_provider'] and m['name']==cfg['dify_model'] and params.get('temperature')==.2 and params.get('max_tokens')==512 and params.get('thinking') is False,'Dify model profile changed')
        if data['type']=='knowledge-retrieval':
            cfg=data['multiple_retrieval_config']
            require(data['dataset_ids']==fixture['configuration']['dataset_ids'] and cfg['top_k']==3 and not cfg['reranking_enable'] and not cfg.get('score_threshold_enabled') and cfg.get('score_threshold') is None,'Knowledge mapping changed')
    nodes={n['id'] for n in native['workflow']['graph']['nodes']}
    traces=receipt.get('trace_expectations')
    require(isinstance(traces,dict) and set(traces)=={c['id'] for c in fixture['cases']},'Root must declare all six native routes')
    for c in fixture['cases']:
        expected={'1','2'} if c.get('followups') else {'1'}
        require(set(traces[c['id']])==expected,'Root must declare all seven turns')
        for row in traces[c['id']].values():
            require(set(row)=={'must','must_not'} and isinstance(row['must'],list) and row['must'] and isinstance(row['must_not'],list),'Missing root branch requirements')
            require(all(isinstance(n,str) and n in nodes for n in row['must']+row['must_not']) and not set(row['must'])&set(row['must_not']),'Root branch IDs not in actual graph')
    contract['owner_task_id']=task['id'];contract['configuration']=copy.deepcopy(task['configuration'])
    value={'plan':copy.deepcopy(p),'native':native,'core':core(native['workflow']),'trace_expectations':copy.deepcopy(traces),'review_source_sha256':receipt['source_sha256']}
    contract[version]=value;b.contract_reviewed=True
    return value
