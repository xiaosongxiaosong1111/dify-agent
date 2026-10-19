"""HTTP authentication by empty, declared Dify secret references only."""
import re
import uuid

NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}')
HEADER=re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}")
KINDS={'bearer','basic','custom'}
FORBIDDEN_HEADERS={'cookie','set-cookie','proxy-authorization','host','content-length'}


def settings(config):
    value=config.get('authentication')
    if value is None:
        return None
    if not isinstance(value,dict) or set(value)!={'type','secret_variable','description','header'}:
        raise ValueError('HTTP authentication 必须完整包含 type、secret_variable、description、header；不能填写密钥或额外字段。')
    kind,name,description,header=(value[key] for key in ('type','secret_variable','description','header'))
    if not isinstance(kind,str) or kind not in KINDS or not isinstance(name,str) or not NAME.fullmatch(name):
        raise ValueError('HTTP 认证仅支持 bearer/basic/custom，秘密变量名须为 1—64 位字母、数字或下划线且不以数字开头。')
    if not isinstance(description,str) or not 1<=len(description.strip())<=2000:
        raise ValueError('HTTP 秘密变量须提供 1—2000 字的用途说明；不要填写实际凭据。')
    if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer\s+[A-Za-z0-9_.-]{16,})',description):
        raise ValueError('HTTP 用途说明疑似含明文凭据，请只描述用途，不要填入密钥。')
    if not isinstance(header,str) or not HEADER.fullmatch(header) or header.lower() in FORBIDDEN_HEADERS:
        raise ValueError('HTTP 认证 header 须为合法单一名称，不能使用 Cookie、Host、Content-Length 等字段。')
    if kind in {'bearer','basic'} and header!='Authorization':
        raise ValueError('bearer/basic 认证目前只支持标准 Authorization 头；自定义头请明确选择 custom。')
    headers=config.get('headers','')
    if isinstance(headers,str) and any(line.partition(':')[0].strip().lower()==header.lower() for line in headers.splitlines()):
        raise ValueError('HTTP 普通 headers 不能重复声明认证头，避免不明确的覆盖。')
    return value


def native(config):
    auth=settings(config)
    if auth is None:return {'type':'no-auth','config':None}
    return {'type':'api-key','config':{'type':auth['type'],'api_key':f"{{{{#env.{auth['secret_variable']}#}}}}",'header':auth['header']}}


def declarations(nodes):
    result={}
    for node in nodes:
        if not isinstance(node,dict) or node.get('type')!='http-request' or not isinstance(node.get('config'),dict):continue
        value=settings(node['config'])
        if value is None:continue
        name=value['secret_variable'];description=value['description']
        if name in result and result[name]['description']!=description:
            raise ValueError('多个 HTTP 节点引用同名秘密变量，但用途说明不同；请统一说明或使用不同名称。')
        result[name]={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'sierra/dify/http-secret/'+name)),
                      'name':name,'value_type':'secret','value':'','description':description,'selector':['env',name]}
    return list(result.values())


def secret_declarations(root):
    workflow=root.get('workflow') if isinstance(root,dict) else None
    raw=workflow.get('environment_variables',[]) if isinstance(workflow,dict) else []
    if not isinstance(raw,list) or len(raw)>100:raise ValueError('DSL 环境变量结构或数量未适配。')
    result={};all_names=set()
    for value in raw:
        if not isinstance(value,dict):raise ValueError('DSL 环境变量须为对象。')
        name=value.get('name')
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in all_names:raise ValueError('DSL 环境变量名无效或重复，不能猜测引用目标。')
        all_names.add(name)
        if value.get('value_type')!='secret':continue
        if value.get('value')!='':raise ValueError('DSL 秘密变量只能为空字符串；请在 Dify 无密钥导出，不接受明文或掩码值。')
        if set(value)-{'id','name','value_type','value','description','selector'}:raise ValueError('DSL 秘密变量含未适配字段。')
        try:uuid.UUID(value.get('id',''))
        except (ValueError,TypeError,AttributeError):raise ValueError('DSL 秘密变量 ID 无效。') from None
        desc=value.get('description','')
        if not isinstance(desc,str) or len(desc)>2000:raise ValueError('DSL 秘密变量用途说明无效。')
        selector=value.get('selector',[])
        if selector not in ([],['env',name]):raise ValueError('DSL 秘密变量 selector 与名称不一致。')
        result[name]=value
    return result


def has_authenticated_http(root):
    workflow=root.get('workflow') if isinstance(root,dict) else None
    graph=workflow.get('graph') if isinstance(workflow,dict) else None
    nodes=graph.get('nodes',[]) if isinstance(graph,dict) else []
    if not isinstance(nodes,list):return False
    for node in nodes:
        data=node.get('data') if isinstance(node,dict) else None
        auth=data.get('authorization') if isinstance(data,dict) else None
        if isinstance(data,dict) and data.get('type')=='http-request' and isinstance(auth,dict) and auth.get('type')=='api-key':return True
    return False


def preserved(data,declared):
    auth=data.get('authorization')
    if auth=={'type':'no-auth','config':None}:return None
    if not isinstance(auth,dict) or set(auth)!={'type','config'} or auth.get('type')!='api-key':raise ValueError('HTTP 认证结构尚未适配，不能删除后通过。')
    cfg=auth.get('config')
    if not isinstance(cfg,dict) or set(cfg)!={'type','api_key','header'}:raise ValueError('HTTP 认证配置须为 type/api_key/header 的秘密引用结构。')
    ref=cfg.get('api_key')
    match=re.fullmatch(r'\{\{#env\.([A-Za-z_][A-Za-z0-9_]{0,63})#\}\}',ref) if isinstance(ref,str) else None
    if not match or match[1] not in declared:raise ValueError('HTTP 认证仅接受完整引用已声明空秘密环境变量；不得写入明文、拼接或未声明变量。')
    value={'type':cfg.get('type'),'secret_variable':match[1],'header':cfg.get('header'),
           'description':declared[match[1]].get('description') or '导入后由用户在 Dify 填写认证凭据。'}
    settings({'authentication':value,'headers':data.get('headers','')})
    return value


def allowed_api_key_objects(root):
    """Only this exact graph path may use a key-shaped field with no key value."""
    try:declared=secret_declarations(root)
    except ValueError:return set()
    workflow=root.get('workflow') if isinstance(root,dict) else None
    graph=workflow.get('graph') if isinstance(workflow,dict) else None
    nodes=graph.get('nodes') if isinstance(graph,dict) else None
    allowed=set()
    for node in nodes if isinstance(nodes,list) else []:
        data=node.get('data') if isinstance(node,dict) else None
        if not isinstance(data,dict) or data.get('type')!='http-request':continue
        try:
            if preserved(data,declared) is not None:allowed.add(id(data['authorization']['config']))
        except ValueError:pass
    return allowed
