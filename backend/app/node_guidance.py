"""Small versioned rule lookup; examples never become task configuration or approval."""
import copy
import hashlib
import json
import re

from fastapi import HTTPException
from .dsl import TARGET_DIFY_VERSION, DSL_VERSION


KINDS = ('knowledge-retrieval', 'if-else', 'code', 'llm', 'start', 'parameter-extractor', 'assigner')
LABELS = {'knowledge-retrieval':'知识检索', 'if-else':'条件分支', 'code':'Python代码', 'llm':'文字大模型',
          'start':'开始入口', 'parameter-extractor':'参数提取', 'assigner':'会话赋值'}
RULES = {
    'knowledge-retrieval': [
        '问题来源须是明确的文字变量；检索 result 是对象数组，不能把它当问题文字直接继续检索。',
        'dataset_source=task 继承当前配置；node 必须提供明确非空的 dataset_ids，空选择不回退。示例库ID仅为占位。',
        '分数阈值与重排须明确选择；开启重排需要独立供应商和型号，不继承回答模型。检索无命中与检索失败分别处理。',
        '回答LLM须用context_variable_selector绑定检索result，并在system_prompt或user_prompt中精确引用{{#context#}}；只有绑定不会把资料自动插入提示。',
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
        '仅据检索资料回答时使用context_variable_selector绑定检索结果，并在system_prompt或user_prompt中引用{{#context#}}；占位也必须绑定来源，不能把验收期望或政策事实硬编码为补充资料。',
    ],
    'start': [
        'Chatflow本轮问题由sys.query提供，query和conversation_id是试跑传输保留名，不可声明为开始变量；没有额外输入时variables=[]。',
        'Workflow显式声明自定义开始输入，再使用[开始节点ID,变量名]；query可作为Workflow自定义名称，不套用Chatflow开始声明。',
        '变量选择器是JSON数组；提示文本中的{{#sys.query#}}不是可替代所有选择器字段的通用字符串。',
    ],
    'parameter-extractor': [
        'Workflow Plan参数提取使用query:[上游节点ID,文字变量]，不是query_variable_selector；reasoning_mode必须明确为prompt。',
        'parameters须逐项给name/type/description/required；失败分支不读取提取字段，required不保证提取成功或业务单号非空。',
        'failure_policy明确explicit_success_branch、guard_node_id、success_case_id；守卫只有__is_success的number = 1一条条件，不能把它当boolean。',
        '提取成功后仍按业务要求另行检查空白或格式；此规则不替用户选择业务有效性条件，不猜编号或外部接口。',
    ],
    'assigner': [
        '此条只提供Chatflow根层会话赋值；先明确conversation_variables的类型/初值/per_conversation及retain_current，不自动声明用户未确认的状态。',
        '每项完整给variable_selector:[conversation,状态名]、input_type、operation及value；variable来源使用value:[节点ID,变量名]，不是value_selector或模板宏字符串。',
        'over-write来源必须与目标标量类型一致且路径可用；每个变量全图唯一writer，同一assigner项列表不能读取正在写入的状态，不允许隐式并行竞争。',
        '不同变量可由各自唯一writer串行更新；这不授权同一变量多写、全局跨会话状态或未明确的业务转移算法。',
    ],
}
LIMITS = {
    'knowledge-retrieval':'仅Sierra已适配的multiple查询；不证明库权限、索引、Embedding兼容、检索质量或真实费用。',
    'if-else':'此示例只演示文字contains和两支连接，不代表所有比较器、容器组合或业务路径已验证。',
    'code':'不包含独立受限代码样例执行；静态有效不代表可运行、输出类型正确或业务规则通过。',
    'llm':'文字样例不证明模型可用、生成质量或结构化/图像/工具能力。',
    'start':'仅合成开始入口示例；定时Workflow按已确认trigger-schedule规则，不用本例替换触发方式或用户类型。',
    'parameter-extractor':'只演示根层文字prompt提取与严格成功分支，不证明模型提取质量或实际业务字段有效。',
    'assigner':'仅Chatflow根层标量状态演示，不提供Workflow根层赋值/容器写入或多writer支持，不证明真实会话持久性。',
}
ALIASES = {
    'knowledge-retrieval':('知识库','知识检索','检索资料','检索结果','knowledge-retrieval'),
    'if-else':('条件','分支','无命中','if-else'),
    'code':('代码','python','code节点'),
    'llm':('大模型','llm','回答','生成回复'),
    'start':('用户输入','开始变量','输入变量','query','start'),
    'parameter-extractor':('参数提取','提取明确','提取订单','提取号码','parameter-extractor','order_no'),
    'assigner':('会话状态','每会话','标记','持久状态','assigner','会话赋值'),
}
NOTE = '当前已整理的专项规则；暂无条目不表示节点不受支持，根层示例不代表容器任意组合。示例是合成Workflow Plan，不是原生DSL或可直接导入的业务方案；占位资源必须由用户选择，不能自动采纳。'


def _example(kind, mode):
    query = ['sys','query'] if mode == 'advanced-chat' else ['start','query']
    token = '{{#' + '.'.join(query) + '#}}'
    start = {'id':'start','type':'start','config':{'variables':[] if mode == 'advanced-chat' else [{'variable':'query','type':'text-input','required':True}]}}
    def terminal(node_id, source, field):
        if mode == 'advanced-chat':
            return {'id':node_id,'type':'answer','config':{'answer':'{{#'+source+'.'+field+'#}}'}}
        return {'id':node_id,'type':'end','config':{'outputs':[{'variable':'result','value_selector':[source,field]}]}}
    states = None
    if kind == 'start':
        echo = {'id':'echo','type':'template-transform','config':{'template':'收到：{{ text }}','variables':[{'variable':'text','value_selector':query}]}}
        nodes = [start,echo,terminal('done','echo','output')]
        edges = [{'source':'start','target':'echo'},{'source':'echo','target':'done'}]
    elif kind == 'parameter-extractor':
        extract = {'id':'extract','type':kind,'config':{'query':query,'reasoning_mode':'prompt',
            'parameters':[{'name':'order_no','type':'string','description':'提取明确给出的合成订单号，不编造。','required':True}],
            'instruction':'信息不足时不猜订单号。','failure_policy':{'behavior':'explicit_success_branch','guard_node_id':'check','success_case_id':'ok'}}}
        check = {'id':'check','type':'if-else','config':{'cases':[{'case_id':'ok','logical_operator':'and','conditions':[{'variable_selector':['extract','__is_success'],'varType':'number','comparison_operator':'=','value':'1'}]}]}}
        success = {'id':'success','type':'template-transform','config':{'template':'收到订单号 {{ order }}','variables':[{'variable':'order','value_selector':['extract','order_no']}]}}
        failure = {'id':'failure','type':'template-transform','config':{'template':'请补充明确订单号。','variables':[]}}
        nodes = [start,extract,check,success,failure,terminal('done_success','success','output'),terminal('done_failure','failure','output')]
        edges = [{'source':'start','target':'extract'},{'source':'extract','target':'check'},
            {'source':'check','source_handle':'ok','target':'success'},{'source':'check','source_handle':'false','target':'failure'},
            {'source':'success','target':'done_success'},{'source':'failure','target':'done_failure'}]
    elif kind == 'assigner':
        states = [{'name':'input_present','var_type':'boolean','initial_value':False,'description':'仅演示本会话输入是否非空',
            'persistence_policy':'per_conversation','unwritten_policy':'retain_current'}]
        presence = {'id':'presence','type':'code','config':{'code_language':'python3','code':"def main(text):\n    return {'present': bool(text.strip())}\n",'variables':[{'variable':'text','value_selector':query}],'outputs':{'present':{'type':'boolean'}}}}
        assign = {'id':'remember','type':'assigner','config':{'items':[{'variable_selector':['conversation','input_present'],'input_type':'variable','operation':'over-write','value':['presence','present']}]}}
        nodes = [start,presence,assign,terminal('done','conversation','input_present')]
        edges = [{'source':'start','target':'presence'},{'source':'presence','target':'remember'},{'source':'remember','target':'done'}]
    elif kind == 'if-else':
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
            llm['config']['system_prompt'] += '\n检索资料：\n{{#context#}}'
            nodes = [start,retrieve,llm,terminal('done','reply','text')]
        else:
            nodes = [start,llm,terminal('done','reply','text')]
        edges = [{'source':a['id'],'target':b['id']} for a,b in zip(nodes,nodes[1:])]
    result = {'schema_version':1,'nodes':nodes,'edges':edges}
    if states is not None:result['conversation_variables'] = states
    return result


def _entry(kind, mode):
    path = {'code':'backend/app/code_entry_contract.py','knowledge-retrieval':'backend/app/retrieval_settings.py','if-else':'backend/app/condition_settings.py','llm':'backend/app/workflow_plan.py',
            'start':'backend/app/workflow_plan.py','parameter-extractor':'backend/app/parameter_extractor.py','assigner':'backend/app/conversation_state.py'}[kind]
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
    available = tuple(k for k in KINDS if k != 'assigner' or app_type == 'advanced-chat') if app_type != 'agent' else ()
    requested = list(dict.fromkeys(available if node_types is None else node_types))
    return {'schema_version':1,'app_type':app_type,'target_dify_version':TARGET_DIFY_VERSION,'target_dsl_version':DSL_VERSION,
            'verification':'static_guidance','runtime_verified':False,'complete_catalog':False,
            'available_node_types':list(available),'missing_node_types':[k for k in requested if k not in available],
            'items':[_entry(k,app_type) for k in requested if k in available],
            'notes':[NOTE] + (['原生Agent使用独立Agent Plan，首批节点规则不适用于它，不发送Workflow示例。'] if app_type=='agent' else [])
                + (['会话赋值条目仅提供Chatflow根层示例；Workflow容器使用独立有限契约，不用Chatflow示例替换。'] if app_type=='workflow' else [])}


def for_task(task):
    mode = task['app_type']
    if mode == 'agent':
        return lookup(mode, [])
    # Use only this task's current saved requirements and plan, never messages or other tasks.
    text = '\n'.join(v for v in task.get('requirements',{}).values() if isinstance(v,str)).lower()
    from .iteration import plan_nodes
    existing = list(dict.fromkeys(n.get('type') for n in plan_nodes(task.get('workflow_plan') or {}) if isinstance(n.get('type'),str)))
    available = lookup(mode,[])['available_node_types']
    kinds = [k for k in available if k in existing or any(word in text for word in ALIASES[k])]
    result = lookup(mode,kinds)
    result['missing_node_types'] = [k for k in existing if k not in available and k not in ('start','end','answer','template-transform')]
    result['selection'] = 'current_saved_plan_and_requirement_keywords'
    return result


def provenance(value):
    return {key:value[key] for key in ('app_type','target_dify_version','target_dsl_version','verification')} | {
        'items':[{'id':row['id'],'content_sha256':row['content_sha256']} for row in value['items']],
        'missing_node_types':list(value['missing_node_types']), 'runtime_verified':False,
    }
