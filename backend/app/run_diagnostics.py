"""Read-only Dify runtime evidence and bounded deterministic diagnostic hints."""
from __future__ import annotations
import copy,hashlib,json,re,uuid
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt
from .dify import DifyClient,DifyError


class DiagnoseRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    read_remote:StrictBool=False


def binding(env):
    return hashlib.sha256(json.dumps({k:env.get(k) for k in ('id','base_url','version')},sort_keys=True).encode()).hexdigest()


def source_hash(run):
    return hashlib.sha256(json.dumps({k:run.get(k) for k in ('id','kind','revision','environment_id','app_id','app_type','environment_binding','status','input','test_case','conversation_context','result','error','http_status','evaluation','manual_review')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def safe_text(value,secrets=(),limit=4000):
    if not isinstance(value,str):return ''
    for secret in sorted((s for s in secrets if isinstance(s,str) and len(s)>=4),key=len,reverse=True):value=value.replace(secret,'[已脱敏]')
    value=re.sub(r'\b(?:sk-|app-|dataset-)[A-Za-z0-9_-]{12,}\b','[已脱敏]',value)
    value=re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b','[已脱敏]',value)
    value=re.sub(r'(?i)\bBearer\s+[^\s,;]+','Bearer [已脱敏]',value)
    value=re.sub(r'''(?i)((?:authorization|api[_-]?key|password|token|secret)\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''',r'\1[已脱敏]',value)
    return value[:limit]+('（摘要已截断）' if len(value)>limit else '')


def selected_result(run):
    result=run.get('result')
    if not isinstance(result,dict):return {},None
    if result.get('conversation_case') is True:
        pending=result.get('pending_turn')
        if isinstance(pending,dict):return pending['result'] if isinstance(pending.get('result'),dict) else {},pending.get('index')
        turns=result.get('turns',[])
        if isinstance(turns,list) and turns:
            selected=next((t for t in reversed(turns) if isinstance(t,dict) and isinstance(t.get('evaluation'),dict) and t['evaluation'].get('status')=='failed'),turns[-1])
            if isinstance(selected,dict):return selected['result'] if isinstance(selected.get('result'),dict) else {},selected.get('index')
        return {},None
    return result,None


def remote_id(result,mode):
    if not isinstance(result,dict):return None
    ids=[result.get('workflow_run_id')]
    if mode=='workflow' and isinstance(result.get('data'),dict):ids.append(result['data'].get('id'))
    present=[value for value in ids if value is not None]
    if not present:return None
    try:normalized=[str(uuid.UUID(v)) for v in present if isinstance(v,str)]
    except (ValueError,TypeError,AttributeError):return None
    return normalized[0] if len(normalized)==len(present) and len(set(normalized))==1 else None


def classify(error,kind=None):
    text=error.lower()
    if kind=='document-extractor':
        if 'unstructured api url is not configured' in text or 'failed to extract text from doc:' in text or 'failed to extract text from xls:' in text:
            return {'category':'document_parser_service','title':'文档解析服务或格式依赖异常的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,'recommendation':'在目标Dify核对实际格式、Unstructured解析服务与授权；这些格式可能发送文件并增加费用，须先明确同意该条件。也可由用户选择提供文字版／转换为已支持格式或缩小范围；Sierra不额外开发转换服务，不改模型Key、不忽略坏文件或自动重跑。'}
        if 'unsupported extension type' in text or 'unsupported mime type' in text or 'unable to determine file type' in text:
            return {'category':'document_format','title':'文档格式无法识别或不支持的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,'recommendation':'核对原生文件的扩展名、MIME和实际内容；原生优先使用扩展名，错误标记可能导致解析失败。扫描件不等于可提取文字；选择补充可读取资料、明确外部解析条件或缩小范围，不通过改文件名、忽略文件或编造文字使流程通过。'}
        if 'failed to download file' in text or 'missing url for remote file' in text:
            return {'category':'document_download','title':'文档文件下载依赖异常的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,'recommendation':'核对上游HTTP.files及Dify保存文件的可访问性、实际权限和地址，不能把普通URL文字当文件。需要真实凭据时按原资源方案补齐；不要修改搭建助手模型Key或关闭认证、删除文档提取绕过问题。核对后另行确认运行，不自动下载或重试。'}
    if kind=='list-operator':
        if 'invalid serial index' in text:
            return {'category':'list_extract_index','title':'数组序号提取越界或无效的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,'recommendation':'核对筛选后的实际数组长度与从1开始的提取序号；原生先筛选、再按序号提取、然后排序和数量截取，序号不是排序后的名次。空数组与非空越界行为不同；不要静默改为首项、关闭筛选或删除提取。缺项该如何处理须确认业务方案，再保存验证，不自动重跑。'}
        if 'is not an array type' in text or 'invalid condition:' in text or 'invalid filter value:' in text:
            return {'category':'list_input_or_filter','title':'数组来源或筛选规则不兼容的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,'recommendation':'在数组处理卡核对实际来源、标量数组声明和筛选类型：文字用字面文字、数字用有限数字字符串、布尔用真实布尔值。对象／文件及动态条件尚未适配；不能把输入强转、删除筛选后当作完成。需要代码转换等替代方案先说明并确认，再按新修订验证。'}
    if kind=='knowledge-retrieval' and re.search(r'query variable is not string type\b',text):
        return {'category':'retrieval_query_type','title':'知识检索问题输入不是文字的迹象','basis':'error_pattern','confidence':'需核对','node_type':kind,
                'recommendation':'检查本知识检索节点的问题 selector 及实际上游输出，Dify 需要文字问题。在检索配置卡明确选对字段，或先确认提取／转换规则后编辑流程；不要自动把数组、对象或数字字符串化，也不要删除检索绕过错误。保存并重新确认后验证，不会自动重跑。'}
    # Native HTTP errors need their own remediation: a missing environment
    # secret is not evidence that the assistant's model provider key is bad.
    http_node=kind=='http-request'
    http_rules=[
      ('http_auth_missing',r'api key is required for authorization but was empty',r'authorizationconfigerror',
       'HTTP 认证秘密变量为空的迹象',
       '在 Dify 中检查该 HTTP 节点引用的秘密环境变量，补齐真实接口凭据后再发布；不要修改 Sierra 的大模型 Key、把密钥写进 DSL，或删除认证以绕过错误。核对当前已发布版本后另行确认试跑，不会自动重跑。'),
      ('http_body_json',r'failed to parse json:',r'requestbodyerror',
       'HTTP 请求体 JSON 解析失败的迹象',
       '检查该 HTTP 节点的完整 JSON 请求体及变量展开后的格式，尤其是引号、转义、空值和数据类型；敏感内容在 Dify 本机核对。不能只检查占位符文本，或直接替换为空对象、删除字段。保持业务字段，编辑后保存、确认并验证；不会自动重跑。'),
    ]
    for category,pattern,exception,title,action in http_rules:
        if re.search(pattern,text) and (http_node or re.search(exception,text)):
            return {'category':category,'title':title,'basis':'error_pattern','confidence':'需核对','recommendation':action,'node_type':kind}
    rules=[
      ('code_syntax',r'syntaxerror|indentationerror|语法错误','代码语法错误迹象','核对报错行和当前代码，仅修复明确语法问题；保存后重新静态检查并按新修订确认。'),
      ('json_parse',r'jsondecodeerror|invalid json|expecting value','JSON 解析失败迹象','检查解析节点实际接收到的数据及来源；先确认数据格式，不擅自跳过异常或替换业务数据。'),
      ('sandbox',r'sandbox.*(?:connect|unauthor|unavailable|failed)|(?:connect|unauthor|unavailable).*sandbox','Sandbox 依赖异常迹象','核对 Dify Sandbox 服务、内部连接及授权配置；不通过删除代码节点绕过。'),
      ('quota',r'rate.?limit|quota|insufficient.balance|余额不足|too many requests','调用限额或余额问题迹象','核对实际供应商余额、限流和批量用量；是否等待、充值或换模型由用户决定。'),
      ('credential',r'invalid.api.?key|invalid.credential|authentication.error|unauthorized','凭据或权限异常迹象','在对应服务配置检查凭据、应用绑定与权限；不把凭据写进 DSL，也不自动换模型。'),
      ('output_schema',r'output.*(?:variable|type|missing|not found|must)|输出.*(?:类型|缺失)','输出声明不匹配迹象','核对代码返回字段和节点输出类型；确认业务输出保持不变后修改并重新验证。'),
      ('variable',r'variable.*(?:not found|does not exist|missing)|required.*input|输入.*缺失','变量或必填输入缺失迹象','核对变量名称、上游路径和实际输入；不要以空默认值掩盖关键业务数据缺失。'),
      ('timeout',r'timeout|timed out|超时','执行超时迹象','核对远端实际状态与耗时，确认外部操作是否发生；结果未知时禁止盲目重跑。'),
      ('loop_control',r'sierra.*循环|连续无进展|最大轮数.*停止条件','循环停止／进度保护触发迹象','核对当前停止条件、状态更新、进度字段与实际目标；不要为使检查通过自动提高轮数、放宽目标或删除保护。修改方案需明确确认后按新修订试跑。'),
    ]
    for category,pattern,title,action in rules:
        if re.search(pattern,text):return {'category':category,'title':title,'basis':'error_pattern','confidence':'需核对','recommendation':action,'node_type':kind}
    return {'category':'unclassified','title':'尚不能可靠归因','basis':'insufficient_evidence','confidence':'未知','recommendation':'结合实际失败节点与 Dify 日志人工核对；不能根据泛化错误自动改业务方案。','node_type':kind}


def findings_for_display(report):
    """Replace only empty generic placeholders; never rewrite stored evidence."""
    findings=copy.deepcopy(report.get('findings',[]))
    if report.get('saved_status')!='success' or report.get('saved_error') or report.get('saved_result_status') not in (None,'','succeeded'):
        return findings
    if len(findings)!=1:return findings
    original=findings[0]
    if original.get('category') not in {'unclassified','saved_execution_success'} or any(original.get(k) for k in ('node_id','node_type','execution_id','evidence')):
        return findings
    if original.get('basis')!={'unclassified':'insufficient_evidence','saved_execution_success':'saved_execution_status'}[original['category']]:return findings
    if report.get('trace_state')=='local_only':
        return [{'category':'saved_execution_success','title':'本地记录为执行成功','basis':'saved_execution_status','confidence':'已记录','recommendation':'这里只说明保存的执行状态；尚未读取完整远端节点轨迹，仍须核对验收规则与实际输出。'}]
    nodes=report.get('nodes',[])
    if report.get('trace_state')!='read' or report.get('trace_error') or report.get('remote_status')!='succeeded' or report.get('remote_error') or report.get('truncated') is not False or not isinstance(nodes,list) or not nodes or type(report.get('node_count')) is not int or report['node_count']!=len(nodes):
        return findings
    for node in nodes:
        if not isinstance(node,dict):return findings
        observation=node.get('observations') or {}
        if not isinstance(observation,dict):return findings
        if node.get('status')!='succeeded' or node.get('error') or observation.get('extraction_status') in {'not_extracted','unknown'} or observation.get('http_status_class') in {'non_2xx','unknown'} or observation.get('retrieval_status') in {'empty','unknown','technical_failure'}:
            return findings
    return [{'category':'execution_trace_success','title':'采集轨迹未发现执行失败','basis':'complete_success_trace','confidence':'已记录','recommendation':'本次远端终态与采集到的完整节点轨迹均为成功。仍须核对验收预期、资料内容与方案来源；执行成功不等于完整业务验收通过。'}]


def analyze(run,secrets=()):
    result,turn=selected_result(run)
    data=result.get('data') if isinstance(result,dict) else None
    error=(data.get('error') if isinstance(data,dict) else None) or (result.get('error') if isinstance(result,dict) else None) or run.get('error') or ''
    text=safe_text(error,secrets)
    mismatch=run.get('status')=='success' and (run.get('evaluation') or {}).get('status')=='failed'
    finding={'category':'expectation_mismatch','title':'执行已返回，但声明的验收规则未通过','basis':'saved_evaluation','confidence':'已记录','recommendation':'核对原始需求、样例预期和实际结果；不能为使检查通过而直接放宽预期。'} if mismatch else classify(text)
    if not mismatch and run.get('http_status') in {401,403}:
        finding={'category':'dify_access','title':'Dify 接口拒绝访问','basis':'saved_http_status','confidence':'已记录','recommendation':'核对该环境的登录、应用运行凭据及权限；接口拒绝不等于应用节点执行失败。'}
    return {'selected_turn':turn,'saved_status':run.get('status'),'remote_run_id':remote_id(result,run.get('app_type')),'saved_error':text,'findings':[finding],'nodes':[],'remote_status':None,'trace_state':'local_only','notes':['诊断不会修改原运行、验收结论、DSL 或配置，也不会派发模型或重跑。','来源判断以采集时为准，使用建议前须重新核对当前环境与方案。']+(['本次结果未知；即使读取到远端终态，也仍需单独核对，重跑保护保持。'] if run.get('status')=='unknown' else []),'node_count':0,'truncated':False}


def parse_trace(detail,trace,rid,secrets):
    if not isinstance(detail,dict) or detail.get('id')!=rid or not isinstance(detail.get('status'),str):raise DifyError('Dify 运行详情标识或状态不匹配，不能关联节点轨迹。')
    if not isinstance(trace,dict) or not isinstance(trace.get('data'),list) or len(trace['data'])>2000:raise DifyError('节点轨迹格式不兼容或超过 2000 项采集上限；不能当成空轨迹。')
    nodes,seen=[],set()
    for row in trace['data']:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row['id'] in seen or any(row.get(k) is not None and not isinstance(row[k],str) for k in ('node_id','node_type','title','status','error')):
            raise DifyError('节点执行条目不完整或重复，不能声称定位完整。')
        seen.add(row['id'])
        node={k:safe_text(row.get(k),secrets,4000 if k=='error' else 200) for k in ('id','node_id','node_type','title','status','error')}
        from .node_metrics import extract
        node['metrics']=extract(row,lambda v:safe_text(v,secrets,128))
        from .node_observations import extract as observe
        observation=observe(row,secrets)
        if observation is not None:node['observations']=observation
        nodes.append(node)
    failed=[node for node in nodes if node['status'] in {'failed','exception'} or node['error']]
    chosen=(failed[:250]+[n for n in nodes if n not in failed][:250]) if len(nodes)>500 else nodes
    findings=[{**classify(n['error'],n['node_type']),'node_id':n['node_id'],'execution_id':n['id'],'evidence':n['error']} for n in failed[:250]]
    from .node_observations import finding as observe_finding
    observations=[value for n in chosen if (value:=observe_finding(n)) is not None]
    findings.extend(observations[:250])
    return {'remote_status':safe_text(detail['status'],secrets,100),'remote_error':safe_text(detail.get('error'),secrets),'nodes':chosen,'node_count':len(nodes),'truncated':len(nodes)>500,'findings':findings}


class DiagnosticsManager:
    def __init__(self,host):self.h=host

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/runs/{run_id}/diagnostics/{diagnostic_id}/presentation')
        def presentation(item_id:str,run_id:str,diagnostic_id:str):
            with h.store.lock:
                task=h.get_task(item_id)
                run=next((r for r in task.get('runs',[]) if r.get('id')==run_id and r.get('kind')=='run'),None)
                report=next((r for r in (run or {}).get('diagnostics',[]) if r.get('id')==diagnostic_id),None)
                if report is None:raise HTTPException(404,'没有该运行的已保存诊断。')
                findings=findings_for_display(report)
                return {'diagnostic_id':diagnostic_id,'source_hash':report.get('source_hash'),'findings':findings,'presentation_adjusted':findings!=report.get('findings',[])}

        @h.app.post('/api/tasks/{item_id}/runs/{run_id}/diagnose')
        async def diagnose(item_id:str,run_id:str,payload:DiagnoseRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                run=next((r for r in task['runs'] if r['id']==run_id),None)
                if not run or run.get('kind')!='run':raise HTTPException(404,'本任务没有该试跑记录；导入诊断尚未适配。')
                if run.get('status')=='pending':raise HTTPException(409,'该运行尚未结束，先保留检查点，不启动诊断。')
                run=copy.deepcopy(run);stamp=source_hash(run)
                env=h.store.get('environment',run.get('environment_id')) if run.get('environment_id') else None
                secrets=[h.store.secret(env['id'],key) for key in h.SECRET_FIELDS if key!='api_key'] if env else []
                provider=task.get('configuration',{}).get('assistant_provider_id')
                if provider:secrets.append(h.store.secret(provider,'api_key'))
                from .diagnostic_graph_source import artifact as graph_artifact,initial as graph_initial,compare as graph_compare,fingerprint
                local_graph=graph_artifact(h,task)
                current_binding=(task.get('dify_app_id'),task.get('environment_id'),copy.deepcopy(task.get('artifact')))
            report=analyze(run,secrets);detail=trace=None
            selected,_=selected_result(run);data=selected.get('data')
            report['saved_result_status']=safe_text(data.get('status'),secrets,100) if isinstance(data,dict) else None
            report['source_graph']=graph_initial(local_graph)
            if payload.read_remote:
                reason=None;message_source=None
                if run.get('app_type') not in {'workflow','advanced-chat'}:reason='该记录缺少可核对的类型快照，或属于原生 Agent；目前仅可本地诊断。'
                elif not env or run.get('environment_binding')!=binding(env):reason='历史记录缺少环境绑定或连接已变更；不会把旧记录发往当前实例。'
                elif not report['remote_run_id']:
                    if run.get('app_type')!='advanced-chat':reason='保存结果没有唯一、合法的 workflow_run_id；不能猜测远端运行。'
                    elif env.get('version')!='1.17.1':reason='消息到原生运行的只读映射仅适配已登记Dify1.17.1；不猜其它版本接口。'
                    else:
                        from .chatflow_diagnostic_source import reference
                        expected=run.get('result',{}).get('conversation_id') if report['selected_turn'] is not None else None
                        try:message_source=reference(selected,expected)
                        except DifyError as exc:reason=safe_text(str(exc),secrets)
                try:app=str(uuid.UUID(run.get('app_id')))
                except (ValueError,TypeError,AttributeError):app=None;reason=reason or '运行没有可靠 App ID 快照；不会改用当前应用。'
                if reason:report.update(trace_state='unavailable',trace_error=reason)
                else:
                    try:
                        client=DifyClient(env,h.store);rid=report['remote_run_id']
                        if message_source is not None:
                            from .chatflow_diagnostic_source import resolve
                            resolution=await resolve(client,app,message_source)
                            rid=resolution['workflow_run_id'];report.update(remote_run_id=rid,remote_id_resolution=resolution)
                            report['notes'].append('本次先按所选保存消息ID与会话ID核对消息记录，再定位原生运行；仅保留身份映射，不保存消息正文，不重跑。')
                        detail=await client.request('GET',f'/console/api/apps/{app}/workflow-runs/{rid}',credential='console_token')
                        if not isinstance(detail,dict) or detail.get('id')!=rid:raise DifyError('Dify 返回的运行标识不匹配，本次不读取节点。')
                        trace=await client.request('GET',f'/console/api/apps/{app}/workflow-runs/{rid}/node-executions',credential='console_token')
                        parsed=parse_trace(detail,trace,rid,secrets);report.update({k:v for k,v in parsed.items() if k!='findings'},trace_state='read')
                        report['notes'].append('节点耗时／用量／报价仅按明确字段展示；缺失为未知，0不证明免费。父容器可能包含子节点用量、并行耗时可能重叠，不相加为应用总费用或执行总时间。')
                        if parsed['findings']:report['findings']=parsed['findings']
                        if not parsed['nodes']:report['notes'].append('该次返回的节点列表为空；不能据此证明没有失败或流程已完成。')
                        if fingerprint(detail.get('graph')):
                            try:
                                published=await client.request('GET',f'/console/api/apps/{app}/workflows/publish',credential='console_token')
                                report['source_graph']=graph_compare(local_graph,detail['graph'],published)
                            except DifyError as exc:
                                source=graph_compare(local_graph,detail['graph'],None);source.update(state='published_read_failed',message=safe_text(str(exc),secrets));report['source_graph']=source
                        else:report['source_graph']=graph_compare(local_graph,detail.get('graph'),None)
                    except DifyError as exc:report.update(trace_state='read_failed',trace_error=safe_text(str(exc),secrets))
            report['findings']=findings_for_display(report)
            snapshot_matches=bool(env and run.get('app_id') and run.get('app_id')==task.get('dify_app_id') and run.get('revision')==task['revision'] and run.get('environment_id')==task.get('environment_id') and run.get('environment_binding')==binding(env))
            report.update(id=str(uuid.uuid4()),run_id=run_id,source_revision=run.get('revision'),captured_at_revision=payload.revision,environment_id=run.get('environment_id'),app_id=run.get('app_id'),source_hash=stamp,created_at=h.now(),snapshot_matches_current=snapshot_matches,current_source=snapshot_matches and report['source_graph']['matched'],verification='diagnostic_evidence_only')
            with h.store.lock:
                current=h.get_task(item_id);h.require_idle(current);h.require_revision(current,payload.revision)
                target=next((r for r in current['runs'] if r['id']==run_id),None)
                if not target or source_hash(target)!=stamp:raise HTTPException(409,'源运行或复核记录已变化，诊断未应用，请重新读取。')
                if current_binding!=(current.get('dify_app_id'),current.get('environment_id'),current.get('artifact')) or local_graph!=graph_artifact(h,current):raise HTTPException(409,'采集期间当前应用或成果内容已变化，诊断未保存，不能将旧来源算作当前方案。')
                latest=h.store.get('environment',run.get('environment_id')) if env else None
                if payload.read_remote and env and (not latest or binding(latest)!=binding(env)):raise HTTPException(409,'采集期间环境地址变化，诊断未保存，不能混用实例。')
                from .optional_branch_audit import audit
                branch=audit(h,current,run,report,detail,trace)
                if branch is not None:report['optional_branch_audit']=branch
                from .file_guard_audit import audit as guard_audit
                guard=guard_audit(h,current,run,report,detail,trace)
                if guard is not None:report['file_guard_audit']=guard
                target.setdefault('diagnostics',[]).append(copy.deepcopy(report));h.save_task(current)
            return report
