import copy,yaml
import pytest
from test_api import client
from test_api import approved
from app.workflow_plan import validate_plan,compile_workflow_plan
from app.declared_types import resolve
from app.iteration import output_type

def cfg(kind='array[number]'):
 return {'variable':['source','items'],'input_type':kind,'filter_by':{'enabled':True,'conditions':[{'key':'','comparison_operator':'>','value':'0'}] if kind=='array[number]' else [{'key':'','comparison_operator':'is','value':True if kind=='array[boolean]' else 'ok'}]},'order_by':{'enabled':True,'key':'','value':'desc'},'limit':{'enabled':True,'size':3},'extract_by':{'enabled':False,'serial':'1'}}

def plan(mode='workflow',kind='array[number]'):
 return {'schema_version':1,'nodes':[{'id':'start','type':'start','config':{'variables':[]}},{'id':'source','type':'code','config':{'code_language':'python3','code':'def main():\n    return {"items": [1, 2, 3]}','variables':[],'outputs':{'items':{'type':kind,'children':None}}}},{'id':'list','type':'list-operator','config':cfg(kind)},{'id':'end','type':'end' if mode=='workflow' else 'answer','config':{'outputs':[{'variable':'result','value_selector':['list','result']}]} if mode=='workflow' else {'answer':'{{#list.result#}}'}}],'edges':[{'source':'start','target':'source'},{'source':'source','target':'list'},{'source':'list','target':'end'}]}

@pytest.mark.parametrize('mode,kind',[('workflow','array[number]'),('advanced-chat','array[string]'),('workflow','array[boolean]')])
def test_scalar_array_compiles_exact_operations_and_type(client,mode,kind):
 task=approved(client,app_type=mode);p=plan(mode,kind);assert validate_plan(task,p)['valid']
 task['workflow_plan']=p;content,result=compile_workflow_plan(task);assert result['valid'];doc=yaml.safe_load(content);data=next(n['data'] for n in doc['workflow']['graph']['nodes'] if n['id']=='list')
 for field in ('variable','filter_by','order_by','limit','extract_by'):assert data[field]==p['nodes'][2]['config'][field]
 assert 'input_type' not in data
 nodes={n['id']:n for n in p['nodes']};assert resolve(nodes,['list','result'])==kind and output_type(nodes,['list','result'])==kind
 assert resolve(nodes,['list','first_record']) is None
 assert any('筛选→按筛后序号提取→排序→数量截取' in w for w in result['warnings'])

@pytest.mark.parametrize('mutation',['object','file','mismatch','unknown','path','in','dynamic','nonfinite','bool_string','negative','serial','missing','extra','nullable','self','branch'])
def test_unsupported_or_ambiguous_operations_refused(client,mutation):
 task=approved(client);p=plan();config=p['nodes'][2]['config'];row=config['filter_by']['conditions'][0]
 if mutation in {'object','file'}:config['input_type']='array['+mutation+']';p['nodes'][1]['config']['outputs']['items']['type']=config['input_type']
 elif mutation=='mismatch':config['input_type']='array[string]'
 elif mutation=='unknown':p['nodes'][1]['config']['outputs']['items']={}
 elif mutation=='path':row['key']='price'
 elif mutation=='in':config['input_type']='array[string]';row.update(comparison_operator='in',value='abc')
 elif mutation=='dynamic':row['value']='{{#start.query#}}'
 elif mutation=='nonfinite':row['value']='1e999'
 elif mutation=='bool_string':config['input_type']='array[boolean]';row.update(comparison_operator='is',value='false')
 elif mutation=='negative':config['limit']['size']=-1
 elif mutation=='serial':config['extract_by']['serial']='0'
 elif mutation=='missing':config.pop('filter_by')
 elif mutation=='extra':config['order_by']['logical_operator']='or'
 elif mutation=='nullable':p['nodes'][-1]['config']['outputs'][0]['value_selector']=['list','first_record']
 elif mutation=='self':config['variable']=['list','result']
 else:p['edges']=[{'source':'start','target':'list'},{'source':'list','target':'source'},{'source':'source','target':'end'}]
 result=validate_plan(task,p);assert not result['valid'] and result['errors']

def test_zero_limit_and_explicit_disabled_settings_do_not_change(client):
 task=approved(client);p=plan();config=p['nodes'][2]['config'];config['limit']['size']=0;config['filter_by']={'enabled':False,'conditions':[]};before=copy.deepcopy(p)
 assert validate_plan(task,p)['valid'] and p==before
