"""Task-specific intake standard, source-checked interview reviews and explicit self review."""
from __future__ import annotations
import copy,hashlib,json,re
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool,StrictStr,Field

from .discussion_mode import requirement_user

class ReviewContractError(ValueError):
    """Only deterministic, non-model-authored review diagnostics may use this type."""


def model_review_outline(task):
    """Give the model exact current identifiers instead of asking it to infer them."""
    return {
        'required_check_topics':[row['id'] for row in topics(task)],
        'topic_rule':'required_check_topics和intake_standard是更新前标准；checks必须按requirements_patch合并后的候选逐项返回。候选正文即使是拟议或needs_input，触发新专项也须增加对应检查；不添加未触发主题或为凑清单新增业务。',
        'conditional_check_topics':[{'id':key,'label':SPECIAL[key][0],'text_pattern':pattern} for key,pattern in PATTERNS.items()],
        'candidate_topic_rule':'conditional_check_topics仅为可触发的ID目录，不是全选清单；按候选需求及原需求用户消息匹配，当前图触发的主题也保留。检索或知识库触发retrieval，不能仅因knowledge已检查而省略。例：原8个基础主题，候选新增知识库检索则须9行，含retrieval；仍有缺口可标needs_input，不用建议自证complete。外部接口匹配需排除sierra_runtime_entry明确的本机空值/错误返回契约说明；真实业务接口仍需external。',
        'material_sources':[{'id':m['id'],'name':m['name']} for m in task.get('materials',[]) if m.get('status')=='parsed'],
        'source_rule':'material证据的id必须使用这里的真实id，不能使用文件名；quote必须逐字来自该来源。',
        'question_fields':['topic','question','recommendation','reason','experience','cost','manual_work'],
        'question_rule':'追问字段必须逐字使用question_fields，人工影响字段为manual_work，不能写manualWork；每个追问的topic必须对应一个status=needs_input的检查项；全部明确时questions必须为空，不能一边写complete一边追问。',
        'decision_rule':'已明确的模型和参数不是笔误推测；可用状态留待资源核对。缺少准备好的资源不自动等于业务需求不清。',
    }

BASE={'goal':('目标与范围','本次为谁解决什么问题？必须完成和不包含的功能是什么？'),'audience':('目标用户','谁使用应用，已有知识和使用方式是什么？'),'input':('输入说明','输入的字段／形式、必填条件和缺失时的处理是什么？'),'output':('输出说明','输出内容、结构、接收对象和交付方式是什么？'),'rules':('业务规则','关键分类、分支、计算、生成规则和不可违反的约束是什么？'),'knowledge':('资料与依赖','使用什么资料、库和接口？哪些可用、待补、模拟或不适用？'),'exceptions':('异常处理','输入不完整、无结果、调用失败时分别怎么处理？'),'tests':('验收场景','请给正常、关键分支和异常输入，以及各自期望结果。')}
SPECIAL={'memory':('对话上下文','是否记住上下文，参考多少轮？指代不清时是否追问？'),'dialogue':('对话行为','开场白／建议问题是什么？何时追问、结束或给出人工指引？'),'agent_tools':('Agent 行为边界','使用纯文本、知识检索还是自定义工具？工具失败怎么处理？'),'batch':('批量处理','如何分项、保留顺序／重复项？一项失败是否停整批，如何汇总？'),'retrieval':('知识检索','资料范围、选库依据、无资料／无命中行为及引用要求是什么？'),'external':('外部接口','接口输入输出、认证条件、可用性及失败行为是什么？是否明确接受模拟？'),'trigger':('自动触发','何时触发，输入来源和输出去向是什么？现有触发能力是否具备？'),'human':('人工参与','谁审核／补充，如何交接？通过、拒绝、超时各如何处理？')}
PATTERNS={'batch':r'批量|逐项|多条|数组|\bbatch\b|\biteration\b','retrieval':r'知识库|检索|引用来源|\brag\b','external':r'接口|\bapi\b|\bhttps?\b|外部系统|数据库','trigger':r'自动触发|定时|触发器|webhook|定期执行','human':r'人工审核|人工审批|人工参与|人工补充|审批流程'}
SPECIAL['loop_policy']=('循环停止与保护','初始状态和每轮更新是什么？停止条件、最大轮次、进度字段／依据、连续无进展与次数耗尽时如何处理？初始即达到目标时返回什么？')
PATTERNS['loop_policy']=r'循环|反复改写|反复修正|\bloop\b'
SPECIAL['document_processing']=('文件获取与解析','文件来自哪里、是什么格式及如何取得权限？扫描件／无文件／空文字／坏文件如何处理？目标Dify是否配置外部解析服务，文件出站、额外费用和人工替代步骤是否已经明确接受？')
PATTERNS['document_processing']=r'文档提取|文档解析|文件解析|文件输入|扫描件|扫描PDF|\bocr\b|\bdocument-extractor\b'
SPECIAL['conversation_state']=('持久会话状态','要保存哪些会话字段及string/number/boolean类型？新会话初值、更新触发与覆盖／计数规则、重置条件、未更新保留、会话隔离和敏感信息边界是什么？计数还需明确业务上限与达到上限的处理；number为float，不默认金额精度，当前仅Chatflow可生成状态写入，其他类型需讨论条件，不自动换类型。')
PATTERNS['conversation_state']=r'会话状态|持久对话|对话变量|conversation_variables|(?:多轮|会话|对话).{0,12}(?:计数|累计次数|记录次数|记住字段)'
SCHEDULE_TOPICS=('schedule_time','schedule_delivery','schedule_operations')
SPECIAL['schedule_time']=('定时规则与时间语义','是否确实由定时器自动启动？须明确时区、小时／日／周／月频次和触发时间；周几、月日／月末及短月如何处理？错过计划时间是否补跑、夏令时如何处理？当前只适配Workflow的visual UTC／Asia/Shanghai，其他方式先说明缺口和替代条件，不自动换类型或时区。')
SPECIAL['schedule_delivery']=('定时输入、输出与重复执行','每次数据从哪里取得、输出交给谁？数据为空、同一任务重复派发或上一次尚未结束时怎么办？明确并发、去重／幂等和重复通知政策；如果需要外部存储或通知接口，应列出已有资源、权限和模拟条件，不能把普通模板输出当作已送达。')
SPECIAL['schedule_operations']=('持续运行、费用与停止责任','定时持续运行多久、谁负责启停？失败如何通知、是否重试、次数／无进展限制是什么？明确每次和累计费用预期、监控与超限处置；Sierra试跑预算不限制平台后续账单，没有自动到期停用，停用不取消已入队请求。目前未适配跨次运行费用封顶、自动通知、漏跑补偿与去重控制；需说明已有外部条件及替代方案的费用、体验和人工影响，确认前不能省略。')
for schedule_topic in SCHEDULE_TOPICS:
    PATTERNS[schedule_topic]=r'定时|定期执行|trigger[-_]schedule|\bscheduled?\b|(?:每小时|每天|每日|每周|每月).{0,20}(?:自动|执行|运行|启动|发送|推送|生成)'
SPECIAL['json_input_scope']=('结构化对象输入与强制范围','对象字段、类型、必填／额外字段、数组及大小／数值规则是什么？本批先在Sierra预检，原生json_schema不证明Dify服务API强制校验；若业务要求所有Dify入口强制，须另加工作流代码方案并确认，不能省略后交付。是否接受本次范围、补代码／人工验证或调整范围？JSON金额／精度要求及敏感数据边界也须明确。')
SPECIAL['batch_outcomes']=('逐项失败与结果合同','当前计划带有逐项结果或汇总生成标识，仍须核对手改代码。是否明确接受六类计算异常作为失败记录继续，index／ok／value／error_category对象数组、原索引与重复项保留，失败值null且不复制异常正文？成功value须明确保留原文字、数值或完整Schema对象类型；对象须核对字段、额外字段禁止和大小限制，不猜Schema。数值不得为布尔、非有限数或超安全范围整数，不能悄悄转文字、舍入或把坏类型当业务失败。输入／输出格式不符、未知、沙箱及超时错误仍终止；若为多代码计算链，还须明确五字段中的failed_stage为1基失败步骤、成功时null，该项后续原计算不执行而只传递失败记录；链正文当前只支持2—8个顺序文字／数值／明确Schema对象计算，每个对象结果步骤须分别核对完整规则，后一步输入沿用前步对象合同，格式错误仍终止，不能扩大到分支或外部副作用；完整有效上游处理图保持，上游原有模型或HTTP仍须核对副作用与费用许可，不能把准备草稿当作执行批准。若有汇总，须明确原完整结果字段及successes／failures／total／succeeded／failed五字段。与旧需求的整批停止或文字数组冲突时先裁定并更新需求，不沿用旧确认；标识不证明代码规则或平台运行正确。')
PATTERNS['json_input_scope']=r'JSON对象|结构化输入|json_object|输入Schema'
UNKNOWN=('待补充','待确认','未知','建议：','建议:','草案：','草案:','假设：','假设:')

LOCAL_ENTRY_DECLARATION=re.compile(
    r'Sierra\s*(?:本机|本地)\s*(?:普通\s*)?(?:任务\s*)?(?:试跑\s*)?(?:HTTP\s*)?(?:API\s*)?接口'
    r'(?=\s*对(?:必填文本\s*以\s*strip\s*判空|已知平台失败\s*返回\s*错误终态))',re.I)
LOCAL_RESULT_DISTINCTION=re.compile(r'成功\s*(?:Workflow\s*)?(?:result|输出)\s*与\s*HTTP\s*错误\s*分开',re.I)

def external_business_text(text):
    """Ignore only named local-entry guarantees, retaining actual integration requests."""
    def local(match):
        prefix=text[max(0,match.start()-20):match.start()]
        if re.search(r'(?:调用|访问|请求|对接|接入|通过|使用|利用|向|从)[^。；;\n，,（）()]{0,8}$',prefix):
            return match.group()
        return ''
    return LOCAL_RESULT_DISTINCTION.sub('',LOCAL_ENTRY_DECLARATION.sub(local,text))

def topics(task):
    result=[{'id':key,'label':label,'question':question,'special':False} for key,(label,question) in BASE.items()]
    chosen=[]
    if task['app_type'] in {'advanced-chat','agent'}:chosen+=['memory','dialogue']
    if task['app_type']=='agent':chosen.append('agent_tools')
    text='\n'.join(task['requirements'].values())+'\n'+'\n'.join(m.get('content','') for m in task.get('messages',[]) if requirement_user(m))
    chosen += [key for key,pattern in PATTERNS.items() if re.search(pattern,external_business_text(text) if key=='external' else text,re.I)]
    if 'batch' not in chosen and any(n.get('type')=='iteration' for n in (task.get('workflow_plan') or {}).get('nodes',[])):chosen.append('batch')
    from .iteration_outcomes import has_protocol
    if has_protocol(task.get('workflow_plan')):chosen.append('batch_outcomes')
    if 'loop_policy' not in chosen and any(n.get('type')=='loop' for n in (task.get('workflow_plan') or {}).get('nodes',[])):chosen.append('loop_policy')
    if 'document_processing' not in chosen and any(n.get('type')=='document-extractor' for n in (task.get('workflow_plan') or {}).get('nodes',[])):chosen.append('document_processing')
    from .file_inputs import has_files
    if 'document_processing' not in chosen and any(n.get('type')=='start' and has_files(n.get('config',{}).get('variables')) for n in (task.get('workflow_plan') or {}).get('nodes',[]) if isinstance(n,dict)):chosen.append('document_processing')
    from .json_inputs import has_objects
    if 'json_input_scope' not in chosen and any(n.get('type')=='start' and has_objects(n.get('config',{}).get('variables')) for n in (task.get('workflow_plan') or {}).get('nodes',[]) if isinstance(n,dict)):chosen.append('json_input_scope')
    if 'conversation_state' not in chosen and ((task.get('workflow_plan') or {}).get('conversation_variables') or any(n.get('type')=='assigner' for n in (task.get('workflow_plan') or {}).get('nodes',[]) if isinstance(n,dict))):chosen.append('conversation_state')
    if any(isinstance(n,dict) and n.get('type')=='trigger-schedule' for n in (task.get('workflow_plan') or {}).get('nodes',[])):
        chosen += [key for key in SCHEDULE_TOPICS if key not in chosen]
    if 'human' not in chosen and any(isinstance(n,dict) and n.get('type')=='human-input' for n in (task.get('workflow_plan') or {}).get('nodes',[])):chosen.append('human')
    from .iteration import plan_nodes
    if 'external' not in chosen and any(n.get('type')=='http-request' for n in plan_nodes(task.get('workflow_plan') or {})):chosen.append('external')
    for key in chosen:
        label,question=SPECIAL[key];result.append({'id':key,'label':label,'question':question,'special':True})
    return result

def context(task):
    value={'app_type':task['app_type'],'requirements':task['requirements'],'standard_topics':[t['id'] for t in topics(task)],'materials':[{k:m.get(k) for k in ('id','name','status','reference_mode','preserve_items','text')} for m in task.get('materials',[])],'user_messages':[{'id':str(i),'text':m.get('content','')} for i,m in enumerate(task.get('messages',[])) if requirement_user(m)]}
    records=task.get('intake_history',[])+([task['intake_review']] if task.get('intake_review') else [])
    additions=[{'answers':r.get('answers',{}),'topic_resolutions':r.get('topic_resolutions',[])} for r in records if r.get('source')=='source_backed_resolution']
    if additions:value['source_backed_answers']=additions
    delegated=[{'answers':r.get('answers',{}),'actor_note':r.get('actor_note','')} for r in records if r.get('source')=='agent_declared']
    if delegated:value['agent_declared_answers']=delegated
    from .iteration_outcomes import has_protocol,semantic_digest
    if has_protocol(task.get('workflow_plan')):value['batch_plan_scope']={'semantic_sha256':semantic_digest(task['workflow_plan']),'verification':'draft_protocol_markers_only'}
    return value

def model_sources(task):
    available=sources(task);keys=list(reversed([key for key in available if key[0]=='message'][-12:]))+[key for key in available if key[0]=='requirement']+[key for key in available if key[0]=='decision'][-16:];result=[];remaining=24000
    for kind,sid in keys:
        source=available[(kind,sid)];excerpt=source[:min(6000,remaining)];remaining-=len(excerpt)
        result.append({'kind':kind,'id':sid,'text':excerpt,'full_text_length':len(source),'excerpt_truncated':len(excerpt)<len(source),'excerpt_provided':bool(excerpt)})
    return result

def digest(task):return hashlib.sha256(json.dumps(context(task),ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def sources(task):
    result={('requirement',key):value for key,value in task['requirements'].items() if value.strip()}
    result.update({('message',str(i)):m.get('content','') for i,m in enumerate(task.get('messages',[])) if requirement_user(m)})
    result.update({('material',m['id']):m.get('text','') for m in task.get('materials',[]) if m.get('status')=='parsed'})
    records=task.get('intake_history',[])+([task['intake_review']] if task.get('intake_review') else [])
    for i,record in enumerate(records):
        if record.get('source')=='user_declared':result.update({('decision',f'{i}:{key}'):value for key,value in record.get('answers',{}).items()})
        elif record.get('source')=='agent_declared':result.update({('decision',f'{i}:{key}'):'【代理受托复核，非模型验证或人类签收】\n'+value for key,value in record.get('answers',{}).items()})
        elif record.get('source')=='source_backed_resolution':result.update({('decision',f'{i}:{key}'):'【按原用户说明的操作者补充，非模型验证或人类签收】\n'+value for key,value in record.get('answers',{}).items()})
    return result

def base_gaps(task):
    gaps=[{'topic':key,'detail':f'{label}尚未明确。','question':question} for key,(label,question) in BASE.items() if not task['requirements'][key].strip() or task['requirements'][key].strip().startswith(UNKNOWN)]
    gaps += [{'topic':'materials','detail':f'材料“{m.get("name",m["id"])}”需成功解析并确认参考方式。','question':'请补充可读取资料，并明确借鉴、保留指定内容或严格复现。'} for m in task.get('materials',[]) if m.get('status')!='parsed' or not m.get('reference_mode')]
    return gaps

def validate_review(task,value,*,evidence_task=None):
    if not isinstance(value,dict) or set(value)!={'schema_version','checks','questions'} or type(value['schema_version']) is not int or value['schema_version']!=1:raise ReviewContractError('需求检查须包含 schema_version=1、checks 和 questions。')
    rows=value['checks'];expected={t['id'] for t in topics(task)};seen=set();available=sources(evidence_task if evidence_task is not None else task)
    if not isinstance(rows,list) or len(rows)!=len(expected):raise ReviewContractError(f'需求检查主题数量不匹配：当前标准为 {len(expected)} 项，须逐项覆盖，不能添加未触发主题或省略主题。')
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'topic','status','detail','evidence'}:raise ReviewContractError('需求检查项字段不符合契约。')
        key=row['topic']
        if not isinstance(key,str) or key not in expected or key in seen:raise ReviewContractError('检查主题缺失、重复或不属于当前任务。')
        seen.add(key)
        if not isinstance(row['status'],str) or row['status'] not in {'complete','needs_input','not_applicable'} or not isinstance(row['detail'],str) or not 0<len(row['detail'].strip())<=3000:raise ReviewContractError('请明确检查状态及最多 3000 字的依据／缺口。')
        if row['status']=='not_applicable' and key in BASE and key not in {'knowledge'}:raise ReviewContractError('业务目标、用户、输入输出、规则、异常和验收不能直接免除。')
        refs=row['evidence']
        if not isinstance(refs,list) or len(refs)>6 or (row['status']!='needs_input' and not refs):raise ReviewContractError('明确／不适用结论必须有具体来源，不能只猜测。')
        for ref in refs:
            if not isinstance(ref,dict) or set(ref)!={'kind','id','quote'} or not all(isinstance(ref.get(k),str) for k in ref):raise ReviewContractError('需求来源格式不正确。')
            source=available.get((ref['kind'],ref['id']))
            if not source or not ref['quote'].strip() or len(ref['quote'])>3000 or ref['quote'] not in source:raise ReviewContractError('需求来源引文不存在，不能编造已明确的依据。')
        if key in BASE and row['status']=='complete' and any(g['topic']==key for g in base_gaps(task)):raise ReviewContractError('空白／拟议字段不能标记为已明确。')
    questions=value['questions'];asked=set();gaps={r['topic'] for r in rows if r['status']=='needs_input'}
    if not isinstance(questions,list) or len(questions)>3 or (gaps and not questions) or (not gaps and questions):raise ReviewContractError('有缺口时应给 1—3 个优先问题，已齐全时不能仍有待答问题。')
    fields={'topic','question','recommendation','reason','experience','cost','manual_work'}
    for q in questions:
        if not isinstance(q,dict) or set(q)!=fields or not all(isinstance(q.get(k),str) for k in fields):raise ReviewContractError('追问须包含问题、推荐、理由及体验／费用／人工影响。')
        if q['topic'] not in gaps or q['topic'] in asked or any(not q[k].strip() or len(q[k])>3000 for k in fields):raise ReviewContractError('追问主题须对应尚未解决的缺口，内容不能为空或超长。')
        asked.add(q['topic'])
    return copy.deepcopy(value)

def summary(task):
    standard=topics(task);record=task.get('intake_review');gaps=base_gaps(task);stale=bool(record and record.get('context_digest')!=digest(task));required=bool(task.get('intake_required') or record)
    reviewed=bool(record and not stale and record.get('review'))
    if reviewed:
        gaps += [{'topic':r['topic'],'detail':r['detail']} for r in record['review']['checks'] if r['status']=='needs_input' and r['topic'] not in {g['topic'] for g in gaps}]
    blockers=[g['detail'] for g in gaps]
    if required and not reviewed:blockers.append('需求说明已变化，请按当前标准重新检查。' if stale else '尚未完成当前需求标准的模型检查或明确人工复核。')
    state='needs_input' if gaps else 'stale' if stale else 'ready_for_confirmation' if reviewed else 'unreviewed'
    questions=copy.deepcopy(record['review']['questions']) if reviewed else []
    if not questions:
        questions=[{'topic':g['topic'],'question':g.get('question') or next((t['question'] for t in standard if t['id']==g['topic']),'请说明该项处理规则。'),'recommendation':'请先明确实际需求；不适用时说明理由。','reason':'避免用未经确认的默认方案替代业务决定。','experience':'明确后才能按预期设计应用。','cost':'取决于选择，当前待核对。','manual_work':'补充规则或明确接受模拟条件。'} for g in gaps[:3]]
    return {'revision':task['revision'],'standard':standard,'state':state,'required':required,'can_confirm':not blockers,'context_token':digest(task),'stale':stale,'reviewed':reviewed,'record':record,'gaps':gaps,'questions':questions,'blockers':blockers,'verification':'source_checked_model_assessment_or_user_declaration','note':'需求检查是规划前的说明核对，不证明业务规则正确、资源已就绪或应用已可交付。'}

def require_ready(task):
    value=summary(task)
    if value['required'] and value['blockers']:raise HTTPException(422,'需求准入未通过：'+'；'.join(value['blockers'][:8]))

class ManualRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    context_token:str
    answers:dict[str,str]
    acknowledge_review:StrictBool
    actor:Literal['local_operator','agent_delegated']='local_operator'
    actor_note:StrictStr=Field(default='',max_length=1000)

class IntakeManager:
    def __init__(self,host):self.h=host

    def save(self,task,review,source):
        if task.get('intake_review'):task.setdefault('intake_history',[]).append(copy.deepcopy(task['intake_review']))
        task['intake_review']={'review':review,'source':source,'origin_revision':task['revision'],'created_at':self.h.now()}
        task['intake_review']['context_digest']=digest(task)

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/intake')
        def get_intake(item_id:str):return summary(h.get_task(item_id))

        @h.app.post('/api/tasks/{item_id}/intake/manual')
        def manual(item_id:str,payload:ManualRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                if payload.context_token!=digest(task):raise HTTPException(409,'对话、资料或需求已变化，请重新读取标准，不应用旧复核。')
                if payload.actor=='agent_delegated' and not payload.actor_note.strip():raise HTTPException(422,'代理复核须说明委托及复核依据，不能当作用户声明。')
                from .plan_drafts import inspect_text
                if payload.actor_note:inspect_text(payload.actor_note)
                standard=topics(task);expected={t['id'] for t in standard}
                if not payload.acknowledge_review or set(payload.answers)!=expected or any(not value.strip() or len(value)>16000 or value.strip().startswith(UNKNOWN) for value in payload.answers.values()):raise HTTPException(422,'请逐项填写明确说明或带理由的不适用说明，并明确接受保存及需求字段替换。')
                updated=copy.deepcopy(task);updated['requirements'].update({k:payload.answers[k].strip() for k in BASE})
                if {t['id'] for t in topics(updated)}!=expected:raise HTTPException(422,'填写内容引入了新的专项场景；请先保存到需求说明，重新读取对应标准后再复核。')
                if base_gaps(updated):raise HTTPException(422,'材料尚未解析或参考方式未确认，不能用人工声明跳过。')
                h.invalidate(task,'人工需求准入复核前保存');task['requirements']=updated['requirements']
                review={'schema_version':1,'checks':[{'topic':t['id'],'status':'complete','detail':payload.answers[t['id']].strip(),'evidence':[{'kind':'requirement','id':t['id'],'quote':task['requirements'][t['id']][:3000]}] if t['id'] in BASE else []} for t in standard],'questions':[]}
                delegated=payload.actor=='agent_delegated'
                self.save(task,review,'agent_declared' if delegated else 'user_declared');task['intake_review']['answers']=copy.deepcopy(payload.answers)
                task['intake_review'].update({'review_actor':payload.actor,'actor_note':payload.actor_note.strip()})
                task['intake_review']['context_digest']=digest(task)
                declaration='这属于代理受托复核，不是模型验证或人类签收' if delegated else '这属于用户声明，不是模型验证'
                task['messages'].append({'role':'assistant','source':'system','content':f'已保存逐项需求复核及需求说明；{declaration}。请检查当前修订，再明确确认需求。','created_at':h.now()})
                return h.save_task(task)
