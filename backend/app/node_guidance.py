"""Small versioned rule lookup; examples never become task configuration or approval."""
import copy
import hashlib
import json
import re

from fastapi import HTTPException
from .dsl import TARGET_DIFY_VERSION, DSL_VERSION


KINDS = ('knowledge-retrieval', 'if-else', 'code', 'llm')
LABELS = {'knowledge-retrieval':'知识检索', 'if-else':'条件分支', 'code':'Python代码', 'llm':'文字大模型'}
RULES = {
    'knowledge-retrieval': [
        '问题来源须是明确的文字变量；检索 result 是对象数组，不能把它当问题文字直接继续检索。',
        'dataset_source=task 继承当前配置；node 必须提供明确非空的 dataset_ids，空选择不回退。示例库ID仅为占位。',
        '分数阈值与重排须明确选择；开启重排需要独立供应商和型号，不继承回答模型。检索无命中与检索失败分别处理。',
    ],
    'if-else': [
        '每个case须有独立case_id、逻辑关系和类型正确的条件，并连接每个case及false出口。',
        '布尔比较的value须是真正JSON布尔值；字符串true不是布尔值，不静默转换。',
        '不能从兄弟分支读取变量。示例各支使用独立终点；合流需要显式聚合，不能在共用end重复声明result。',
    ],
    'code': [
        'Python入口按main(**inputs_obj)调用，节点variables名称须能按关键字绑定；显式缺必填或多余输入会拒绝。',
        '返回字典的字段与outputs声明须一致，实际返回值和业务样例仍需目标沙箱验证。',
        '这里只做语法、引用和可判定入口检查；动态入口可能未核实，不执行导入、装饰器、默认值或函数体。',
    ],
    'llm': [
        'system_prompt或user_prompt至少有一项非空；引用须来自已声明且当前路径可用的变量。',
        '未指定独立model时继承任务模型；独立型号及完整参数需逐项核对资源、规则、插件与费用。',
        '仅据检索资料回答时使用context_variable_selector绑定检索结果，不能把验收期望或政策事实硬编码为补充资料。',
    ],
}
LIMITS = {
    'knowledge-retrieval':'仅Sierra已适配的multiple查询；不证明库权限、索引、Embedding兼容、检索质量或真实费用。',
    'if-else':'此示例只演示文字contains和两支连接，不代表所有比较器、容器组合或业务路径已验证。',
    'code':'不包含独立受限代码样例执行；静态有效不代表可运行、输出类型正确或业务规则通过。',
    'llm':'文字样例不证明模型可用、生成质量或结构化/图像/工具能力。',
}
ALIASES = {
    'knowledge-retrieval':('知识库','知识检索','检索资料','检索结果','knowledge-retrieval'),
    'if-else':('条件','分支','无命中','if-else'),
    'code':('代码','python','code节点'),
    'llm':('大模型','llm','回答','生成回复'),
}
NOTE = '首批四类专项规则；暂无条目不表示节点不受支持。示例是合成Workflow Plan，不是原生DSL或可直接导入的业务方案；占位资源必须由用户选择，不能自动采纳。'


def _example(kind, mode):
    query = ['sys','query'] if mode == 'advanced-chat' else ['start','query']
    token = '{{#' + '.'.join(query) + '#}}'
    start = {'id':'start','type':'start','config':{'variables':[] if mode == 'advanced-chat' else [{'variable':'query','type':'text-input','required':True}]}}
    def terminal(node_id, source, field):
        if mode == 'advanced-chat':
            return {'id':node_id,'type':'answer','config':{'answer':'{{#'+source+'.'+field+'#}}'}}
        return {'id':node_id,'type':'end','config':{'outputs':[{'variable':'result','value_selector':[source,field]}]}}
    if kind == 'if-else':
        route = {'id':'route','type':kind,'config':{'cases':[{'case_id':'match','logical_operator':'and','conditions':[{'variable_selector':query,'varType':'string','comparison_operator':'contains','value':'订单'}]}]}}
        yes = {'id':'yes','type':'template-transform','config':{'template':'订单分支示例','variables':[]}}
        no = {'id':'no','type':'template-transform','config':{'template':'其它分支示例','variables':[]}}
        nodes = [start,route,yes,no,terminal('done_yes','yes','output'),terminal('done_no','no','output')]
        edges = [{'source':'start','target':'route'}, {'source':'route','source_handle':'match','target':'yes'}, {'source':'route','source_handle':'false','target':'no'}, {'source':'yes','target':'done_yes'}, {'source':'no','target':'done_no'}]
    else:
        llm = {'id':'reply','type':'llm','config':{'system_prompt':'仅依据绑定的检索上下文回答；没有依据时明确说明，不编造。' if kind == 'knowledge-retrieval' else '按已确认规则回答。','user_prompt':token}}
        if kind == 'code':
            node = {'id':'code','type':'code','config':{'code_language':'python3','code':"def main(query):\n    return {'result': query.strip()}\n",'variables':[{'variable':'query','value_selector':query}],'outputs':{'result':{'type':'string'}}}}
            nodes = [start,node,terminal('done','code','result')]
        elif kind == 'knowledge-retrieval':
            retrieve = {'id':'retrieve','type':kind,'config':{'query_variable_selector':query,'dataset_source':'node','dataset_ids':['EXAMPLE_DATASET_ID'],'top_k':3,'score_threshold':None,'reranking_enable':False}}
            llm['config']['context_variable_selector'] = ['retrieve','result']
            nodes = [start,retrieve,llm,terminal('done','reply','text')]
        else:
            nodes = [start,llm,terminal('done','reply','text')]
        edges = [{'source':a['id'],'target':b['id']} for a,b in zip(nodes,nodes[1:])]
    return {'schema_version':1,'nodes':nodes,'edges':edges}


def _entry(kind, mode):
    path = {'code':'backend/app/code_entry_contract.py','knowledge-retrieval':'backend/app/retrieval_settings.py','if-else':'backend/app/condition_settings.py','llm':'backend/app/workflow_plan.py'}[kind]
    sources = [{'kind':'sierra_adapter','path':path,'version':TARGET_DIFY_VERSION}]
    upstream = {
        'code':'api/core/helper/code_executor/python3/python3_transformer.py',
        'knowledge-retrieval':'api/core/workflow/nodes/knowledge_retrieval/knowledge_retrieval_node.py',
    }.get(kind)
    if upstream:
        sources.append({'kind':'upstream_tag','url':'https://github.com/langgenius/dify/blob/'+TARGET_DIFY_VERSION+'/'+upstream,'version':TARGET_DIFY_VERSION})
    value = {'id':'dify-'+TARGET_DIFY_VERSION+'/'+mode+'/'+kind+'/1','node_type':kind,'label':LABELS[kind], 'app_type':mode,
             'rules':copy.deepcopy(RULES[kind]), 'limitations':[LIMITS[kind]], 'sources':sources,
             'example_kind':'synthetic_plan', 'example_plan':_example(kind,mode),
             'example_configuration':{'dify_model_provider':'EXAMPLE_MODEL_PROVIDER','dify_model':'EXAMPLE_MODEL','temperature':0.2,'max_tokens':512},
             'example_note':'使用前须核对业务规则、所有变量和配置；示例不修改任务、不代表确认、执行或发布授权。'}
    value['content_sha256'] = hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value


def lookup(app_type, node_types=None, dify_version=TARGET_DIFY_VERSION):
    if app_type not in ('workflow','advanced-chat','agent'):
        raise HTTPException(422,'请明确选择Workflow、Chatflow或原生Agent，不自动替换应用类型。')
    if dify_version != TARGET_DIFY_VERSION:
        raise HTTPException(422,'节点规则仅适配Dify '+TARGET_DIFY_VERSION+'，不会用其它版本规则代替。')
    if node_types is not None and (not isinstance(node_types,list) or len(node_types)>16 or any(not isinstance(k,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}',k) for k in node_types)):
        raise HTTPException(422,'节点查询最多16项，每项须为不超过80字符的节点类型标识，不能有空项。')
    available = KINDS if app_type != 'agent' else ()
    requested = list(dict.fromkeys(available if node_types is None else node_types))
    return {'schema_version':1,'app_type':app_type,'target_dify_version':TARGET_DIFY_VERSION,'target_dsl_version':DSL_VERSION,
            'verification':'static_guidance','runtime_verified':False,'complete_catalog':False,
            'available_node_types':list(available),'missing_node_types':[k for k in requested if k not in available],
            'items':[_entry(k,app_type) for k in requested if k in available],
            'notes':[NOTE] + (['原生Agent使用独立Agent Plan，首批节点规则不适用于它，不发送Workflow示例。'] if app_type=='agent' else [])}


def for_task(task):
    mode = task['app_type']
    if mode == 'agent':
        return lookup(mode, [])
    # Use only this task's current saved requirements and plan, never messages or other tasks.
    text = '\n'.join(v for v in task.get('requirements',{}).values() if isinstance(v,str)).lower()
    from .iteration import plan_nodes
    existing = list(dict.fromkeys(n.get('type') for n in plan_nodes(task.get('workflow_plan') or {}) if isinstance(n.get('type'),str)))
    kinds = [k for k in KINDS if k in existing or any(word in text for word in ALIASES[k])]
    result = lookup(mode,kinds)
    result['missing_node_types'] = [k for k in existing if k not in KINDS and k not in ('start','end','answer','template-transform')]
    result['selection'] = 'current_saved_plan_and_requirement_keywords'
    return result


def provenance(value):
    return {key:value[key] for key in ('app_type','target_dify_version','target_dsl_version','verification')} | {
        'items':[{'id':row['id'],'content_sha256':row['content_sha256']} for row in value['items']],
        'missing_node_types':list(value['missing_node_types']), 'runtime_verified':False,
    }
