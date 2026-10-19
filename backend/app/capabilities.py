"""Current compiler scope, independent of customer resources or runtime readiness."""
from fastapi import HTTPException
from .dsl import TARGET_DIFY_VERSION,DSL_VERSION
from .workflow_plan import SUPPORTED_PLAN_NODES
from .iteration import BODY_TYPES,BODY_GRAPH_TYPES,MAX_BODY_NODES
from .agent_plan import AGENT_RUNTIME_NOTE

LABELS={'start':'开始','trigger-schedule':'定时触发草稿','human-input':'人工审核草稿','llm':'文字大模型','question-classifier':'问题分类','parameter-extractor':'参数提取','list-operator':'标量数组处理','document-extractor':'文档提取（声明文件来源）','knowledge-retrieval':'知识检索','if-else':'条件分支','code':'代码','template-transform':'模板转换','http-request':'HTTP请求','iteration':'迭代','loop':'受保护标量循环','variable-aggregator':'变量聚合','assigner':'对话状态赋值v2','end':'结束输出','answer':'对话回答'}
APP_LABELS={'workflow':'Workflow／工作流','advanced-chat':'Chatflow／对话流','agent':'原生Agent'}


def catalog(app_type,version):
    if app_type not in APP_LABELS:raise HTTPException(422,'请明确选择已适配的Workflow、Chatflow或原生Agent；不会替换类型。')
    def rows(types):return [{'type':kind,'label':LABELS[kind]} for kind in SUPPORTED_PLAN_NODES if kind in types]
    result={'schema_version':2,'sierra_version':version,'app_type':app_type,'app_label':APP_LABELS[app_type],
            'target_dify_version':TARGET_DIFY_VERSION,'target_dsl_version':DSL_VERSION,
            'verification':'compiler_scope','root_nodes':[],'containers':[],
            'notes':['这是当前Sierra生成／静态校验范围，不是目标环境的完整节点目录，也不证明已导入、资源可用或业务样例通过。','未解析参考材料可明确提供用户文字及覆盖范围，原文件仍未读；这不是识图／OCR能力。','用户选择的应用类型不自动改变；缺条件或功能超出范围时，先讨论替代方案、费用与人工工作，再由用户确认范围。'],
            'file_workflows':None,'not_adapted':['嵌套迭代／循环','Webhook／插件触发','任意插件工具及Skills','通用自动修复和供应商账单硬上限']}
    if app_type=='workflow':
        from .file_capabilities import catalog as file_catalog
        result['file_workflows']=file_catalog()
        result['not_adapted'] += ['真实自然定时业务验收','复杂人工审核的指定身份、邮件、补充表单及容器组合','文件OCR与通用复杂文件图的实际执行']
    elif app_type=='advanced-chat':result['not_adapted'] += ['Chatflow开始文件变量、文件上传单次试跑及OCR','Chatflow定时／人工审核入口']
    else:result['not_adapted'] += ['原生Agent文件上传与专用文件试跑','Workflow定时、人工审核及容器流程']
    if app_type=='agent':
        result.update(agent_scopes=[{'scope':'text','label':'明确纯文字指令'},{'scope':'knowledge','label':'使用已明确选择的知识集'}])
        result['notes'].append(AGENT_RUNTIME_NOTE)
        return result
    result['notes'].append('流程页可手填本次迭代项数，预览声明逻辑节点执行次数的保守上界；循环使用原loop_count，未知项数不记0。不检查最终DSL／Dify手改或发布图，不读取输入／文件，不估实际API请求、Token或价格，不修改预算或批准运行。')
    result['notes'].append('文字LLM可逐节点选择有当前环境依据的供应商、型号及完整参数；只有未指定独立模型才继承任务配置，不能跨型号隐藏继承参数或编造标识；保存与确认不证明真实模型可用。')
    result['notes'].append('知识检索可逐节点明确选库或继承任务库、设置分数阈值与完整rerank型号；LLM不是重排型号，无命中行为、延迟和额外费用须确认；单库模型路由、权重重排、元数据过滤和附件尚未适配，不改变库自身策略。')
    if app_type=='workflow':result['notes'].append('保留完整有效上游处理图、经Python解析items文字数组并直连唯一End的2—8步顺序纯Python文字／数值／明确逐步Schema对象计算链，可明确改成index／ok／value／error_category／failed_stage五字段逐项结果；六类计算异常标记1基失败步骤，后续只传递失败记录，不执行该项后续原计算；其它输入输出合同、未知、沙箱和超时错误仍终止。可单独明确加同合同成功／失败列表和计数，已有规范链可精确重建后追加汇总。对象中间及最终结果须逐步明确完整Schema，输入输出错误仍终止；链正文不是通用DAG／模型／HTTP计算链；上游原有分支、汇合及其它节点原样保留，不代表获准执行上游副作用或费用，不删节点或重试，静态草稿仍须保存后重确认并按授权试跑。')
    if app_type=='workflow':result['notes'].append('四根节点JSON文字数组解析→单Python计算迭代→唯一End，可明确预览六类计算异常作为带index／ok／value／error_category的失败记录继续；成功value保留原声明文字、有限数值或明确完整Schema对象类型；对象支持受限字段规则并严格禁止额外字段，64000字节／20000值／16层限制，不猜字段或忽略未知规则。数值拒绝布尔、非有限数和超安全范围整数；结果改为对象数组，未知／沙箱／超时及输入输出合同错误仍终止，父原生策略仍terminated。可再明确增加成功／失败列表和计数汇总代码；不适用于模型／HTTP／多正文或通用原生continue，改变合同会重新要求需求复核。这里只准备未保存草稿，不执行代码或访问Dify。')
    result['notes'].append('文字LLM可显式配置有限JSON Schema的结构化对象输出；根及已适配单层容器可引用整个structured_output对象，关闭不删除原schema或下游引用。模型／插件、schema实际约束及业务仍须验证；不推断嵌套字段，不把text当对象。')
    excluded={'answer','assigner'} if app_type=='workflow' else {'end','trigger-schedule','human-input'}
    if app_type=='advanced-chat':result['notes'].append('首批conversation持久状态为按会话独立string/number/boolean（number为原生float），根v2 assigner显式覆盖或number常量加减乘除（除零拒绝，动态结果范围未静态保证）；同变量一个写节点，无根隐式并行/容器赋值；单层容器可只读已声明状态，不是历史摘要/跨用户共享。需验收新会话、同会话多轮与未写分支。')
    if app_type=='workflow':result['notes'].append('根LLM结构化对象可先预览严格Schema校验纯代码及连接方案，明确非法对象让整次运行失败后采纳到草稿；不默认补值／重试，改Schema／生成代码／前置连接使旧保护失效。尚未实际Dify沙箱与客户验收。')
    if app_type=='workflow':result['notes'].append('唯一visual定时入口可选小时／日／周／月及UTC／Asia/Shanghai；无虚构query，不能与start共存。支持生成／保留／下载、已有发布图只读证据及人工确认单触发器启停；专用三节点纯文字新建发布后核对并尝试停用已接入；发布可能直接激活，失败可能持续调度，真实自然业务尚未验收，试跑预算不限制后续持续费用，无自动停用，不能以手动run冒充。')
    if app_type=='advanced-chat':excluded.add('human-input')
    if app_type=='workflow':result['notes'].append('根人工审核草稿：文字对象、WebApp交互、approve/reject/__timeout三路；无补充表单输入／邮件／容器组合，专用纯模板单审核资源方案可独立确认创建/发布/采集表单，原动作须另行确认单次提交，再主动核对动作/分支/固定输出；不强制审核人身份、不自动决定，真实平台及客户业务尚未验收。')
    result['root_nodes']=rows(set(SUPPORTED_PLAN_NODES)-excluded)
    result['containers']=[{'type':kind,'label':LABELS[kind],'max_body_nodes':MAX_BODY_NODES,'sequence_nodes':rows(BODY_TYPES),'dag_nodes':rows(BODY_GRAPH_TYPES),'note':note} for kind,note in [
        ('iteration','对明确标量／对象数组、根Workflow明确文件列表或上游原生HTTP.files文件数组逐项处理，可顺序或明确独立性与并发数后并行；结果保留输入索引、重复项和空输入，失败终止整批，不保证立即取消已派发项。'),
        ('loop','更新明确标量状态，保留停止、次数耗尽失败和连续无进展保护；不支持并行循环，初始已达目标允许零轮完成。')]]
    result['notes'] += ['容器检索须明确本项／本轮文字query；HTTP正文仅支持声明GET／HEAD重复读取。分类／提取／条件／聚合须明确DAG，全部路径汇到共同终点，业务提取参数须必要成功门。','逐项／逐轮模型、Embedding、检索、rerank及HTTP可能产生费用与限流。并发、轮数和Sierra助手预算不是供应商账单硬上限。','文档提取支持明确的根Workflow文件／文件列表、经存在分支保护的可选单文件、受保护原生文件迭代item，以及根或同一容器全路径上游HTTP.files；不同类型不隐式互转，嵌套及OCR未适配，解析服务仍须核对；Chatflow可声明文字／数字／选项开始变量，问题仍用sys.query；query／conversation_id为传输保留名。带自定义变量支持新单轮及初始参数一致的全新固定多轮样例，先校验所有轮次再发；自由续聊只从当前App／环境／成果／运行凭据绑定的成功自由记录沿用原参数，旧记录缺绑定／参数变化／手填CID拒绝。可主动预览并替换本次自定义参数，保留当前query，不自动继承、补值或更新参数，实际平台／业务仍须验收。']
    return result
