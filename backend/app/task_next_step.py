"""Navigation advice from saved local state; no action dispatch or readiness grant."""
import hashlib,json
from .plan_review import needed as needs_plan_review
from .workflow_publication import saved_publication

STATES={
 'plan_required':('流程','先生成并核对完整流程','当前任务尚无显式流程；基础线性模板不能自动代替需求中的分支和异常行为。',['先核对配置中的模型和知识库，再请求Sierra规划完整流程。','仅需线性步骤时可明确准备基础草稿，查看后放入编辑器并保存。','保存计划后复核配置，再生成DSL；静态有效仍不代表业务覆盖。']),
 'busy':(None,'等待当前操作结束','当前记录仍有进行中或待返回的操作；先核对结果，避免重复派发。',['可查看当前进度；已派发的请求不保证立即取消。']),
 'paused':('历史','先核对暂停或错误记录','任务已暂停或需处理，先看原因及最后一次操作，再决定补条件或修改方案。',['恢复、重试、改变方案及追加费用仍需按原入口确认。']),
 'intake':('需求','补齐并复核当前需求','当前需求标准尚未满足；先澄清输入输出、业务规则、异常和专项条件。',['可以请Sierra追问，也可逐项人工复核；未决定的规则不要填成已确认。']),
 'requirements':('需求','确认当前需求','本机准入检查未发现阻断，仍需要你确认当前需求及方案分歧。',['准入结论不证明业务正确；确认前核对模拟条件和未交付范围。']),
 'plan':('流程','复核并保存已过期的流程','需求或材料已经变化，原流程不能直接沿用；检查节点、变量与失败规则。',['保留手改内容，保存后重新确认相关配置。']),
 'configuration':('配置','核对并确认具体配置','需求已确认，下一步核对模型、参数、资料、资源方案及条件。',['模型服务与Dify应用模型分开；关键选择由你确认。','无显式复杂计划时可先到流程页准备；基础模板仍可使用。']),
 'build':('构建','生成或重新检查当前DSL','尚无当前修订的有效静态成果；可在构建页检查并生成。',['构建只在本机准备文件，不证明真实导入、依赖或业务运行。']),
 'offline':('构建','下载待验证DSL，或连接Dify继续','当前静态文件可作为待验证成果；任务尚未选择Dify环境。',['可以先下载并保留进度；要继续真实导入，请在Dify环境中连接并为任务选择环境。']),
 'schedule':('流程','核对定时专用资源与触发证据','此流程有定时入口，普通手动运行不能证明自然触发；请使用专用资源与观察入口。',['发布可能激活持续调度；核对启停责任、持续费用和未验证条件。']),
 'human':('流程','核对人工审核专用入口','此流程需人审表单及明确动作，请使用专用资源方案和动作核对入口。',['不自动替审核人决定；分别核对通过、拒绝和超时。']),
 'import':('构建','核对资源方案后导入Dify','当前修订有静态成果，尚无已记录的目标应用标识。',['在构建页核对实际环境、认证与新增／复用影响，再按原确认流程导入。']),
 'files':('运行','准备文件专用试跑条件','当前计划声明文件输入；请使用文件上传与文件流程专用入口。',['先明确文件归属、解析与出站条件、模型费用及结果规则；普通文字试跑不能代替。']),
 'publication':('运行','核对当前App发布状态','已有导入标识，但尚无匹配当前修订、环境、App及类型的发布成功回执。',['前往运行页核对发布卡；已有发布时不覆盖，不根据本机记录缺失直接重发。','需要首次发布时按具体范围明确确认；这里只导航，不请求Dify。']),
 'publication_review':('运行','先核对当前App的原发布记录','当前App发布结果未知、尚未返回或回执不匹配，不能按未发布处理。',['可能已经派发，禁止直接重发；在运行页查看原记录及Dify实际结果。','这里只读取本机进度，不查询平台或解除未知状态。']),
 'runtime_key':('运行','核对并登记当前App专属运行Key','本机已有匹配的发布成功回执，当前运行Key配对尚未确认。',['在运行页核对Key的App归属；原Key已配对时不重复创建。','登记或创建仍须原入口的明确确认；本机有配对声明不证明Key实际可用。']),
 'run':('运行','准备样例并核对一次试跑条件','本机已记录应用标识，尚无当前修订／环境／应用的普通运行记录。',['核对发布图、运行Key归属、真实／模拟依赖、费用及样例，再明确派发。']),
 'review':('运行','核对结果与尚未覆盖的场景','已有当前绑定的普通运行记录；请核对返回、错误、规则检查及待验证项。',['返回或规则通过不等于全部业务通过；自由输入、文件、人审及定时证据须分别核对。']),
 'manual':('历史','人工核对当前进度','当前本机状态无法据此给出可靠的下一步，未推断已完成或自动恢复。',['先查看历史、报告与原操作说明。'])}
BUSY={'importing','running','building','planning','interviewing'}
KNOWN=BUSY|{'requirements','configuration','ready','draft_ready','imported','run_completed','paused','error','needs_input','waiting_platform'}

def describe(task,intake, *, runtime_key_paired=None):
    runs=task.get('runs') if isinstance(task.get('runs'),list) else []
    ops=task.get('planning_runs') if isinstance(task.get('planning_runs'),list) else []
    def pending(rows):return any(isinstance(r,dict) and r.get('status') in {'pending','running','ready_to_confirm'} for r in rows)
    plan=task.get('workflow_plan') or {};nodes=plan.get('nodes',[]) if isinstance(plan,dict) else []
    nodes=[n for n in nodes if isinstance(n,dict)] if isinstance(nodes,list) else []
    types={n.get('type') for n in nodes if isinstance(n.get('type'),str)}
    artifact=task.get('artifact');revision=task['revision'];status=task.get('status')
    publication=saved_publication(task)
    managed_publication=task.get('app_type') in {'workflow','advanced-chat'}
    current=[r for r in runs if isinstance(r,dict) and r.get('kind')=='run' and type(r.get('revision'))is int and r.get('revision')==revision and r.get('environment_id')==task.get('environment_id') and r.get('app_id')==task.get('dify_app_id') and r.get('app_type')==task.get('app_type')]
    from .file_inputs import has_files
    files=any(n.get('type')=='start' and isinstance(n.get('config'),dict) and has_files(n['config'].get('variables')) for n in nodes)
    if task.get('app_type') not in {'workflow','advanced-chat','agent'} or status not in KNOWN:state='manual'
    elif status in BUSY or task.get('active_interview_id') or task.get('active_image_operation_id') or pending(runs) or pending(ops):state='busy'
    elif status in {'paused','error','waiting_platform'}:state='paused'
    elif intake.get('can_confirm') is not True:state='intake'
    elif task.get('requirements_confirmed') is not True:state='requirements'
    elif task.get('plan_stale') is True:state='plan'
    elif needs_plan_review(task):state='plan_required'
    elif task.get('configuration_confirmed') is not True:state='configuration'
    elif not isinstance(artifact,dict) or type(artifact.get('revision'))is not int or artifact['revision']!=revision or not isinstance(artifact.get('validation'),dict) or artifact['validation'].get('valid') is not True:state='build'
    elif not task.get('environment_id'):state='offline'
    elif task.get('app_type')=='workflow' and 'trigger-schedule' in types:state='schedule'
    elif task.get('app_type')=='workflow' and 'human-input' in types:state='human'
    elif not task.get('dify_app_id'):state='import'
    elif task.get('app_type')=='workflow' and files:state='files'
    elif managed_publication and publication['uncertain']:state='publication_review'
    elif current:state='review'
    elif managed_publication and not publication['published']:state='publication'
    elif managed_publication and runtime_key_paired is not True:state='runtime_key'
    else:state='run'
    page,title,reason,checks=STATES[state]
    if state=='busy':page={'interviewing':'需求','planning':'流程','building':'构建','importing':'构建','running':'运行'}.get(status,'历史')
    # Bind only the observed decision facts; never return raw requirements,
    # errors, run results, credentials or customer fields.
    facts={'revision':revision,'app_type':task.get('app_type'),'status':status,'state':state,'requirements_confirmed':task.get('requirements_confirmed'),'configuration_confirmed':task.get('configuration_confirmed'),'plan_stale':task.get('plan_stale'),'environment_id':task.get('environment_id'),'dify_app_id':task.get('dify_app_id'),'artifact_revision':artifact.get('revision') if isinstance(artifact,dict) else None,'intake_context':intake.get('context_token'),'publication':publication,'runtime_key_paired':runtime_key_paired is True,'run_ids':[r.get('id') for r in current]}
    token=hashlib.sha256(json.dumps(facts,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return {'schema_version':1,'task_id':task['id'],'revision':revision,'app_type':task['app_type'],'snapshot_token':token,'state':state,'target_page':page,'title':title,'reason':reason,'checklist':list(checks),'verification':'saved_local_navigation_advice_only','task_changed':False,'network_requested':False,'automatic_execution':False,'business_verified':False,'note':'依据已保存的本机记录；执行操作时仍会核对原确认、资源和预算。建议不代表已验证或交付。'}


def register(host):
    from fastapi import APIRouter,Query
    from .plan_drafts import DraftRoute
    from .intake import summary
    router=APIRouter(route_class=DraftRoute)
    @router.get('/api/tasks/{item_id}/next-step')
    def read(item_id:str,revision:int=Query(ge=1)):
        with host.store.lock:
            task=host.get_task(item_id);host.require_revision(task,revision)
            env=host.store.get('environment',task.get('environment_id')) if task.get('environment_id') else None
            paired=bool(env and task.get('dify_app_id') and env.get('service_app_id')==task['dify_app_id']
                        and host.store.has_secret(env['id'],'service_api_key'))
            return describe(task,summary(task),runtime_key_paired=paired)
    host.app.include_router(router)
