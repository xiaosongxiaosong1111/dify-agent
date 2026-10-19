"""Bounded, explicit three-way DSL preservation; never writes to a source app."""
import copy
import hashlib
import json
import math
import re
import yaml
from .dsl import DSL_VERSION, _contains_secret_key

MAX_BYTES=2_000_000
MISSING=object()


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def load_document(content):
    if not isinstance(content,str) or len(content.encode('utf-8'))>MAX_BYTES:
        raise ValueError('DSL 须为最多 2 MB 的 YAML 文本。')
    class StrictLoader(yaml.SafeLoader): pass
    def mapping(loader,node,deep=False):
        out={}
        for key,value in node.value:
            k=loader.construct_object(key,deep=deep)
            if not isinstance(k,str) or k in out:raise ValueError('DSL 对象键须为不重复的字符串。')
            out[k]=loader.construct_object(value,deep=deep)
        return out
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    try:root=yaml.load(content,Loader=StrictLoader)
    except (yaml.YAMLError,RecursionError) as exc:raise ValueError('DSL YAML 无法安全解析。') from exc
    budget=[40000];seen=set()
    def check(value,depth=0):
        budget[0]-=1
        if depth>60 or budget[0]<0:raise ValueError('DSL 超过结构解析上限。')
        if isinstance(value,(dict,list)):
            if id(value) in seen:raise ValueError('DSL 不接受循环或共享 YAML 锚点。')
            seen.add(id(value))
            for child in (value.values() if isinstance(value,dict) else value):check(child,depth+1)
        elif value is not None and type(value) not in (str,int,float,bool):raise ValueError('DSL 包含非 JSON 值。')
        elif type(value) is float and not math.isfinite(value):raise ValueError('DSL 不接受非有限数字。')
        elif isinstance(value,str) and (re.search(r'\bsk-[a-zA-Z0-9_-]{16,}',value) or re.search(r'(?i)\bBearer\s+[A-Za-z0-9_.-]{16,}',value)):
            raise ValueError('DSL 疑似包含明文密钥，请在 Dify 中用不包含密钥的方式导出。')
    check(root)
    if not isinstance(root,dict):raise ValueError('DSL 须为 YAML 对象。')
    if _contains_secret_key(root):raise ValueError('DSL 含密钥字段，不能进入引用、差异或成果。')
    workflow=root.get('workflow') or {}
    for value in workflow.get('environment_variables',[]) if isinstance(workflow,dict) else []:
        if isinstance(value,dict) and value.get('value_type')=='secret' and value.get('value'):
            raise ValueError('DSL 环境变量含明文秘密，请重新无密钥导出。')
    graph=workflow.get('graph',{}) if isinstance(workflow,dict) else {}
    from .http_auth_reference import secret_declarations,has_authenticated_http
    declared_secrets=secret_declarations(root) if has_authenticated_http(root) else {}
    for node in graph.get('nodes',[]) if isinstance(graph,dict) and isinstance(graph.get('nodes'),list) else []:
        data=node.get('data',{}) if isinstance(node,dict) else {}
        if isinstance(data,dict) and data.get('type')=='http-request':
            from .workflow_plan import _http_security_errors,_URL_SECRET_NAMES
            dangerous=[e for e in _http_security_errors(data,declared_secrets) if any(word in e for word in ('凭据','用户名','密码','认证','秘密变量'))]
            from .http_body import validate as validate_http_body
            body_errors,_=validate_http_body(data.get('body'))
            body=data.get('body')
            dangerous.extend(e for e in body_errors if '凭据' in e or '密钥' in e or isinstance(body,dict) and body.get('type')=='json')
            params=data.get('params','')
            if isinstance(params,str) and any(re.split(r'[:=]',line,maxsplit=1)[0].strip().lower() in _URL_SECRET_NAMES for line in params.splitlines()):dangerous.append('HTTP 查询参数含凭据字段')
            if dangerous:raise ValueError('DSL HTTP 含凭据或未适配认证，不能进入参考／保留记录；请使用无密钥导出或补充脱敏文字说明。')
    return root


def parse(content, mode):
    root=load_document(content)
    if root.get('kind')!='app' or root.get('version')!=DSL_VERSION or not isinstance(root.get('app'),dict) or root['app'].get('mode')!=mode:
        raise ValueError(f'DSL 须为当前应用类型 {mode}，版本 {DSL_VERSION}；不能静默换类型或跨版本。')
    return root


def shown(value):
    if value is MISSING:return {'missing':True}
    text=json.dumps(value,ensure_ascii=False,sort_keys=True)
    return {'value':value} if len(text)<=3000 else {'preview':text[:3000],'truncated':True}


def merge(base,current,generated,choices=None):
    choices=choices or {};conflicts=[];preserved=[];changed=[];used=set();nodes=[0]
    def equal(a,b):
        if a is MISSING or b is MISSING:return a is b
        return digest(a)==digest(b)
    def clone(v):return MISSING if v is MISSING else copy.deepcopy(v)
    def visit(b,c,g,path):
        nodes[0]+=1
        if nodes[0]>40000:raise ValueError('差异分析超过结构上限。')
        if equal(c,g):return clone(c)
        if equal(c,b):
            changed.append({'path':path,'generated':shown(g)})
            return clone(g)
        if equal(g,b):
            preserved.append({'path':path,'current':shown(c)})
            return clone(c)
        if all(isinstance(v,dict) for v in (b,c,g)):
            result={}
            for key in sorted(set(b)|set(c)|set(g)):
                v=visit(b.get(key,MISSING),c.get(key,MISSING),g.get(key,MISSING),path+'/'+key.replace('~','~0').replace('/','~1'))
                if v is not MISSING:result[key]=v
            return result
        if path in {'/workflow/graph/nodes','/workflow/graph/edges'} and all(isinstance(v,list) for v in (b,c,g)):
            maps=[]
            for items in (b,c,g):
                if any(not isinstance(v,dict) or not isinstance(v.get('id'),str) or not v['id'] for v in items):break
                mapping={v['id']:v for v in items}
                if len(mapping)!=len(items):break
                maps.append(mapping)
            if len(maps)==3:
                result=[];order=list(dict.fromkeys([v['id'] for v in c]+[v['id'] for v in g]+[v['id'] for v in b]))
                for key in order:
                    v=visit(*(m.get(key,MISSING) for m in maps),path+'/@'+key.replace('~','~0').replace('/','~1'))
                    if v is not MISSING:result.append(v)
                return result
        conflict={'path':path,'base':shown(b),'current':shown(c),'generated':shown(g),'recommendation':'current','reason':'此处 Dify 当前草稿与本次生成方案均有变化；建议先保留当前值，请明确选择。'}
        pick=choices.get(path)
        if pick is not None:
            if pick not in {'current','generated'}:raise ValueError('冲突选择只能为 current 或 generated。')
            used.add(path);conflict['choice']=pick
        conflicts.append(conflict)
        return clone(g if pick=='generated' else c)
    root=visit(base,current,generated,'')
    if set(choices)-used:raise ValueError('冲突选择含过期或不存在的路径。')
    if len(conflicts)+len(preserved)+len(changed)>1000:raise ValueError('差异超过 1000 项，请缩小本次调整范围。')
    return {'root':root,'conflicts':conflicts,'preserved':preserved,'generated_changes':changed,'unresolved':sum('choice' not in v for v in conflicts)}


def validate_preserved(root,parallel_reviews=None,loop_reviews=None):
    from .workflow_plan import validate_plan
    from .model_parameters import validate_model_parameters
    errors=[];nodes=[];edges=[]
    try:
        graph=root['workflow']['graph']
        from .node_policy import require_native as require_node_policy
        require_node_policy(root)
        from .optional_file import require_native as require_optional_file_presence
        require_optional_file_presence(root)
        if not isinstance(graph.get('nodes'),list) or not isinstance(graph.get('edges'),list):raise ValueError('图节点与连接须为数组。')
        from .http_auth_reference import secret_declarations,has_authenticated_http,preserved as preserved_http_auth
        declared_secrets=secret_declarations(root) if has_authenticated_http(root) else {}
        from .preserved_loop import project as project_loops
        scope_graph,loop_configs,loop_bodies,loop_body_nodes=project_loops(root,loop_reviews)
        from .parallel_preservation import validate as validate_parallel_reviews
        reviews=validate_parallel_reviews(root,parallel_reviews or {})
        from .preserved_iteration import scopes
        containers,starts,raw_nodes,body_graphs=scopes(scope_graph,reviews)
        raw_nodes.update({n['id']:n for n in loop_body_nodes})
        for raw in [*scope_graph['nodes'],*loop_body_nodes]:
            if raw['id'] in starts:continue
            data=raw['data'];kind=data['type'];config={}
            if kind=='start':config={'variables':data.get('variables',[])}
            elif kind=='human-input':
                from .human_review import preserved as preserved_review
                config=preserved_review(data)
            elif kind=='trigger-schedule':
                if raw.get('parentId'):raise ValueError('定时触发必须为根入口，不移动容器触发后通过。')
                from .schedule_trigger import preserved as preserved_schedule
                config=preserved_schedule(data)
            elif kind=='assigner':
                if raw.get('parentId') or data.get('version')!='2':raise ValueError('首批对话赋值只保留根v2 assigner，不删除未知版本或容器状态行为。')
                if set(data)-{'type','title','desc','selected','isInIteration','isInLoop','version','items'}:raise ValueError('原对话赋值含未知执行/错误/重试设置，不省略后声称保留。')
                config={'items':copy.deepcopy(data.get('items'))}
            elif kind=='loop':config=copy.deepcopy(loop_configs[raw['id']])
            elif kind=='iteration':config={k:data.get(k) for k in ('iterator_selector','iterator_input_type','output_selector','output_type','is_parallel','error_handle_mode','flatten_output')}
            elif kind=='llm':
                prompts=data.get('prompt_template',[])
                if not isinstance(prompts,list) or any(not isinstance(p,dict) or p.get('role') not in {'system','user','assistant'} or not isinstance(p.get('text'),str) for p in prompts):raise ValueError('保留 LLM 仅支持明确的文字消息模板。')
                config={'system_prompt':'\n'.join(p['text'] for p in prompts if p['role'] in {'system','assistant'}),'user_prompt':'\n'.join(p['text'] for p in prompts if p['role']=='user')}
                from .structured_output import native as preserved_structured
                config.update(preserved_structured(data))
                model=data['model']
                if not isinstance(model.get('provider'),str) or not model['provider'].strip() or not isinstance(model.get('name'),str) or not model['name'].strip():raise ValueError('保留 LLM 缺少实际供应商／模型。')
                params=model.get('completion_params',{});extra={k:v for k,v in params.items() if k not in {'temperature','max_tokens'}};validate_model_parameters(extra)
                if type(params.get('temperature',.2)) not in {int,float} or not 0<=params.get('temperature',.2)<=2 or type(params.get('max_tokens',2048)) is not int or params.get('max_tokens',2048)<1:raise ValueError('保留 LLM 参数范围无效。')
                if (data.get('vision') or {}).get('enabled'):raise ValueError('保留合并暂不支持 LLM 视觉输入。')
                context=data.get('context') or {}
                if context.get('enabled'):config['context_variable_selector']=context.get('variable_selector')
            elif kind=='document-extractor':
                from .document_extractor import preserved as preserved_document
                config=preserved_document(data)
            elif kind=='list-operator':
                from .list_operator import FIELDS
                config={k:copy.deepcopy(data.get(k)) for k in FIELDS}
            elif kind=='parameter-extractor':
                if raw.get('parentId') and data.get('memory') is not None:raise ValueError('容器内提取不适配独立记忆，不能删除历史设置后声称保留。')
                from .parameter_extractor import preserved as preserved_extractor
                config=preserved_extractor(data,'workflow' if raw.get('parentId') else root['app']['mode'],raw['id'],graph)
            elif kind=='question-classifier':
                from .question_classifier import preserved as preserved_classifier
                if raw.get('parentId') and data.get('memory') is not None:raise ValueError('容器内分类记忆尚未适配，不能删除历史设置后声称保留。')
                config=preserved_classifier(data,'workflow' if raw.get('parentId') else root['app']['mode'])
            elif kind=='knowledge-retrieval':
                from .retrieval_settings import preserved
                config=preserved(data)
            elif kind=='if-else':
                config={'cases':[{'case_id':v.get('case_id',v.get('id')),'logical_operator':v.get('logical_operator','and'),'conditions':v.get('conditions')} for v in data.get('cases',[])]}
            elif kind=='code':
                from .structured_guard import validate_native as validate_native_guard
                from .file_join import validate_native as validate_file_join
                guard_errors=validate_native_guard(data)+validate_file_join(data)
                if guard_errors:raise ValueError('；'.join(guard_errors))
                config={k:data.get(k) for k in ('code_language','code','variables','outputs')}
            elif kind=='template-transform':config={k:data.get(k) for k in ('template','variables')}
            elif kind=='http-request':
                auth=preserved_http_auth(data,declared_secrets)
                config={k:data[k] for k in ('method','url','headers','params','body','timeout','variables') if k in data and data[k] is not None}
                if auth is not None:config['authentication']=auth
                from .http_execution import preserved as preserved_http_execution
                config.update(preserved_http_execution(data))
                from .body_http import KEY,preserved as preserved_read
                read_policy=preserved_read(data,required=bool(raw.get('parentId')))
                if read_policy is not None:config[KEY]=read_policy
                body=data.get('body')
                if isinstance(body,dict) and isinstance(body.get('data'),list) and any(isinstance(v,dict) and v.get('type')=='file' for v in body['data']):raise ValueError('保留 HTTP 的文件请求体尚未适配，不会移除文件后通过。')
            elif kind=='variable-aggregator':
                advanced=data.get('advanced_settings')
                if advanced is not None and (not isinstance(advanced,dict) or advanced.get('group_enabled') is not False):raise ValueError('保留变量聚合目前只支持明确关闭分组，不能删除分组后当作通过。')
                config={'variables':data.get('variables'),'output_type':data.get('output_type'),'selection_mode':'first_available'}
            elif kind=='end':config={'outputs':data.get('outputs')}
            elif kind=='answer':config={'answer':data.get('answer')}
            else:raise ValueError(f'保留合并尚未适配节点 {kind}；不会移除后宣称通过。原生包节点及循环等需另行适配。')
            nodes.append({'id':raw['id'],'type':kind,'config':config})
        projected={node['id']:node for node in nodes}
        for parent,children in containers.items():
            if parent in reviews:projected[parent]['config'].update(parallel_nums=raw_nodes[parent]['data']['parallel_nums'],parallel_safe=True,parallel_reason=reviews[parent]['reason'])
            projected[parent]['config']['nodes']=[projected[key] for key in children]
            projected[parent]['config'].update(body_graphs.get(parent,{}))
        for parent,body_ids in loop_bodies.items():
            projected[parent]['config']['nodes']=[projected[key] for key in body_ids]
        from .iteration import output_type,ARRAY_TYPES
        inferred=False
        for _ in range(len(projected)+1):
            changed=False
            from .declared_types import resolve as declared_type
            from .list_operator import TYPES as LIST_TYPES
            for item in projected.values():
                if item['type']=='list-operator' and 'input_type' not in item['config']:
                    declared=declared_type(projected,item['config'].get('variable'),mode=root['app']['mode'])
                    if declared in LIST_TYPES:item['config']['input_type']=declared;changed=True
            for parent,children in containers.items():
                cfg=projected[parent]['config'];data=raw_nodes[parent]['data']
                if 'output_type' not in data and cfg.get('output_type') is None:
                    declared=output_type({key:projected[key] for key in children},cfg.get('output_selector'))
                    if declared in ('string','number','object'):cfg['output_type']=f'array[{declared}]';changed=True
                if 'iterator_input_type' not in data and cfg.get('iterator_input_type') is None:
                    declared=output_type(projected,cfg.get('iterator_selector'))
                    if isinstance(declared,str) and declared in ARRAY_TYPES:cfg['iterator_input_type']=declared;changed=True
            inferred=inferred or changed
            if not changed:break
        nodes=[node for node in nodes if not raw_nodes[node['id']].get('parentId')]
        for raw in scope_graph['edges']:
            if not raw_nodes[raw['source']].get('parentId'):edges.append({'source':raw['source'],'target':raw['target'],'source_handle':raw.get('sourceHandle','source')})
        features=root['workflow'].get('features') or {}
        if (features.get('file_upload') or {}).get('enabled'):raise ValueError('文件输入的保留合并尚未适配，请保留完整文件并先明确条件。')
        from .conversation_state import preserved as conversation_preserved
        conversation_rows=conversation_preserved(root['workflow'].get('conversation_variables',[]),root['app']['mode'])
        validation=validate_plan({'app_type':root['app']['mode'],'configuration':{}},{'schema_version':1,'nodes':nodes,'edges':edges,'conversation_variables':conversation_rows})
        validation['warnings'].append('校验保留文件的已适配图、变量、文字模型参数和代码语法；平台额外字段按原文件保留，未声称完整业务／资源可用性已验证。')
        if containers:validation['warnings'].append('保留单层顺序或经明确独立性声明的并行逐项迭代的实际内部链或条件／聚合 DAG 及作用域；布局、代码、模型保持原文。尚未执行 Dify 整图；嵌套及失败继续保留未适配。')
        if loop_configs:validation['warnings'].append('仅保留完整Sierra受保护标量循环：原保护代码AST／绑定、开始／正文／v2赋值顺序、实际停止条件／最大次数和当前进度声明核对；原文件不改写。用户声明不是业务进展或实际执行证明，任意原生循环／嵌套尚未适配。')
        if inferred:validation['warnings'].append('缺失的迭代／数组处理类型元数据仅依据源 DSL 中明确的上游及所选输出声明推导，未改变原文件；未知或明确矛盾的声明不能按猜测通过。')
        if any(node['type']=='http-request' for node in nodes):validation['warnings'].append('HTTP 实际超时、证书校验与重试设置按原文件保留；max_*_timeout 仅为平台上限元数据，不作为实际超时，元数据原文未删除。业务响应和重复提交尚未实际验证。')
        return validation
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        errors.append(str(exc) if isinstance(exc,ValueError) else '保留 DSL 的字段结构不受支持，请核对图及节点。')
    return {'valid':False,'errors':errors,'warnings':[],'nodes':len(nodes),'verification':'static_only'}


def preview(record, generated, revision, choices=None,parallel_reviews=None,loop_reviews=None):
    proposal=parse(generated,record['mode'])
    result=merge(record['base'],record['current'],proposal,choices)
    root=result.pop('root')
    content=yaml.safe_dump(root,allow_unicode=True,sort_keys=False)
    if record['mode']=='agent':
        from .agent_preservation import validate as validate_agent_preserved
        validation=validate_agent_preserved(root,proposal,parallel_reviews,loop_reviews)
    else:
        validation=validate_preserved(root,parallel_reviews,loop_reviews)
        from .workflow_resource_inventory import inventory
        result['workflow_resource_inventory']=inventory(root,digest(root))
        if validation['valid'] and not result.get('unresolved'):
            from .workflow_environment_mapping import source_summary as workflow_mapping_source
            result['workflow_mapping_source']=workflow_mapping_source(root)
    if record['mode']=='agent':
        from .agent_model_comparison import compare as compare_agent_model
        result['agent_model_comparison']=compare_agent_model(root,proposal)
        if validation['valid'] and not result.get('unresolved'):
            from .agent_environment_mapping import source_summary
            result['agent_mapping_source']=source_summary(root)
    token=digest({'revision':revision,'reference_id':record['id'],'base':record['base'],'current':record['current'],'generated':proposal,'parallel_reviews':parallel_reviews or {},'loop_reviews':loop_reviews or {}})
    from .parallel_preservation import candidates
    from .preserved_loop import candidates as loop_candidates
    result.update(loop_candidates=[] if record['mode']=='agent' else loop_candidates(root),loop_reviews=copy.deepcopy(loop_reviews or {}),document_token=digest(root),parallel_candidates=[] if record['mode']=='agent' else candidates(root),parallel_reviews=copy.deepcopy(parallel_reviews or {}))
    return {**result,'revision':revision,'reference_id':record['id'],'merge_token':token,'content':content,'validation':validation,'source':record['source'],'source_app_id':record.get('source_app_id'),'captured_at':record['created_at'],'baseline_note':record['baseline_note'],'note':'对照上次生成文件与 Dify 编辑草稿；导出规范化造成的差异也可能出现，不能把每项差异都断言为人工修改。确认后最终 DSL 会保留所选字段；原生成计划与配置只是生成建议，最终值以本页合并文件为准。'}
