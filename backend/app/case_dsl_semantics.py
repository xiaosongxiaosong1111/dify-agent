"""Explicit native fields for evaluation proposals, never generated-code execution."""
import copy,json
from fastapi import HTTPException

FIELDS={
 'start':('variables',),
 'human-input':('version','form_content','inputs','user_actions','timeout','timeout_unit','delivery_methods'),
 'trigger-schedule':('version','mode','frequency','visual_config','timezone','cron_expression'),
 'end':('outputs',),
 'answer':('answer',),
 'code':('code_language','code','variables','outputs'),
 'template-transform':('template','variables'),
 'llm':('model','prompt_template','context','memory','vision','structured_output_enabled','structured_output'),
 'question-classifier':('model','classes','instruction','query_variable_selector','memory','vision'),
 'parameter-extractor':('model','query','parameters','instruction','reasoning_mode','memory','vision'),
 'list-operator':('variable','filter_by','order_by','limit','extract_by'),
 'document-extractor':('variable_selector','is_array_file'),
 'knowledge-retrieval':('query_variable_selector','dataset_ids','retrieval_mode','multiple_retrieval_config','single_retrieval_config'),
 'if-else':('cases',),
 'http-request':('method','url','headers','params','body','timeout','authorization','ssl_verify','retry_config'),
 'variable-aggregator':('variables','output_type','advanced_settings'),
 'iteration':('start_node_id','iterator_selector','iterator_input_type','output_selector','output_type','is_parallel','parallel_nums','error_handle_mode','flatten_output'),
 'iteration-start':(),
 'loop':('start_node_id','loop_count','loop_variables','logical_operator','break_conditions'),
 'loop-start':(),
 'assigner':('version','items'),
}
FEATURES=('opening_statement','suggested_questions','suggested_questions_after_answer','retriever_resource','more_like_this','text_to_speech','speech_to_text','sensitive_word_avoidance')
MAX_BYTES=120_000


def summary(root):
    from .node_policy import require_native
    try:require_native(root)
    except ValueError as exc:raise HTTPException(422,'验收语义依据包含未适配执行策略：'+str(exc)) from None
    workflow=root['workflow'];graph=workflow['graph'];nodes=[];omitted=[]
    for raw in graph['nodes']:
        data=raw['data'];kind=data['type'];fields=FIELDS.get(kind)
        if fields is None:raise HTTPException(422,f'验收语义摘要未适配节点 {kind}，不会省略其行为后生成建议。')
        nodes.append({'id':raw['id'],'type':kind,'title':data.get('title'),'parent_id':raw.get('parentId'),
                      'config':{key:copy.deepcopy(data[key]) for key in fields if key in data}})
        extra=sorted(set(data)-set(fields)-{'type','title','desc','selected','isInIteration','iteration_id'})
        if extra:omitted.append({'id':raw['id'],'fields':extra})
    features=workflow.get('features') or {}
    classifier_fallbacks=[{'node_id':n['id'],'behavior':'native_first_class','class_id':n['config']['classes'][0]['id'],'scope':'parsed_missing_fields_or_unknown_scalar_id_not_all_errors'} for n in nodes if n['type']=='question-classifier' and isinstance(n['config'].get('classes'),list) and n['config']['classes'] and isinstance(n['config']['classes'][0],dict) and isinstance(n['config']['classes'][0].get('id'),str)]
    result={'schema_version':1,'nodes':nodes,
            'edges':[{key:copy.deepcopy(edge[key]) for key in ('source','target','sourceHandle','targetHandle') if key in edge} for edge in graph['edges']],
            'features':{key:copy.deepcopy(features[key]) for key in FEATURES if key in features},'classifier_fallbacks':classifier_fallbacks,
            'omitted_node_fields':omitted,'omitted_feature_fields':sorted(set(features)-set(FEATURES)),
            'note':'已确认保留文件的明确字段摘要。保留实际条件、代码、模板、模型／检索设置和连接；布局、平台额外字段、运行证据及知识库全文未包含。省略字段不等于功能已取消；若影响预期请列待决定事项，不能声称已执行代码、触发分支或完整覆盖。'}
    from .http_auth_reference import secret_declarations,has_authenticated_http
    from .body_http import preserved as read_policy
    repeated=[]
    for raw in graph['nodes']:
        if raw['data'].get('type')=='http-request':
            try:policy=read_policy(raw['data'],required=bool(raw.get('parentId')))
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            if policy is not None:repeated.append({'node_id':raw['id'],'parent_id':raw.get('parentId'),'policy':policy,'native_read_only_enforcement':False})
    if repeated:result['repeated_http_reads']=repeated
    if workflow.get('conversation_variables'):
        from .conversation_state import preserved
        try:preserved(workflow['conversation_variables'],root['app']['mode'])
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        result['conversation_variables']=[{key:copy.deepcopy(row.get(key)) for key in ('id','name','value_type','value','description')} for row in workflow['conversation_variables']]
        result['conversation_state_note']='原生每个conversation独立标量状态；未写时保留当前值，不是历史摘要或跨用户共享。根number常量加减乘除使用当前值，字面值限制不是动态结果范围或金额精度保证；初始/新会话/同会话多轮/分支未更新须验收；不发送运行中的对话状态。'
    if has_authenticated_http(root):
        declarations=secret_declarations(root)
        used=set()
        for raw in graph['nodes']:
            if raw['data'].get('type')=='http-request':
                from .http_auth_reference import preserved
                auth=preserved(raw['data'],declarations)
                if auth:used.add(auth['secret_variable'])
        result['http_secret_dependencies']=[{'name':name,'description':declarations[name].get('description',''),'value_included':False,'readiness':'user_must_configure_in_dify_not_verified'} for name in sorted(used)]
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8'))>MAX_BYTES:
        raise HTTPException(422,'最终 DSL 的验收语义摘要超过 120000 字节，尚未适配分块；请先缩小参考范围或人工编写样例，不会截断代码／条件后生成建议。')
    return result
