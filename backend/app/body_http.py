"""Declared repeated HTTP reads; metadata is not a platform read-only guarantee."""
import copy,json,re

KEY='repeated_read_policy'
PREFIX='SIERRA_REPEAT_READ_V1:'
FIELDS={'method','url','headers','params','body','timeout','ssl_verify','retry_config','authentication','variables',KEY}
NOTE='容器HTTP首批只支持明确声明的GET／HEAD重复读取；方法名不保证无副作用，须核对接口语义、次数／并发／节点重试、限流、收费、数据出站及失败处理。此声明不是平台强制只读或费用硬上限。关闭节点重试且没有异常策略时，非2xx可能仍为HTTP节点成功；业务须检查status_code／返回体，启用节点重试时错误与请求次数行为不同。'


def validate(config,required=True):
    policy=config.get(KEY)
    if policy is None and not required:return []
    errors=[]
    if not isinstance(policy,dict) or set(policy)!={'read_only','reason'} or policy.get('read_only') is not True:
        errors.append('须明确 repeated_read_policy={read_only:true,reason:实际只读用途}，不是根据GET猜测无副作用。')
    else:
        reason=policy['reason']
        if not isinstance(reason,str) or not 0<len(reason.strip())<=2000 or '{{#' in reason:
            errors.append('重复读取 reason 须为1—2000字的明确静态用途，不使用动态模板。')
        elif re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer\s+[A-Za-z0-9_.-]{16,})',reason):
            errors.append('重复读取说明疑似包含凭据，只能描述用途。')
    method=config.get('method')
    if not isinstance(method,str) or method.lower() not in {'get','head'}:
        errors.append('容器重复HTTP首批只支持GET／HEAD读取，不支持写入方法，不会改成GET后通过。')
    return errors


def description(config):
    return PREFIX+json.dumps(config[KEY],ensure_ascii=False,separators=(',',':'))


def preserved(data,required=True):
    text=data.get('desc','')
    if not isinstance(text,str) or not text.startswith(PREFIX):
        if not required:return None
        raise ValueError('容器HTTP缺少可核对的Sierra重复读取声明；原文件保持，请先明确用途，不能默认为无副作用。')
    if len(text)>12000:raise ValueError('重复读取声明过大，不截断后采纳。')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate declaration field')
            result[key]=value
        return result
    try:policy=json.loads(text[len(PREFIX):],object_pairs_hook=unique)
    except (ValueError,TypeError) as exc:raise ValueError('重复读取声明不是完整JSON，不能沿用旧用途。') from exc
    errors=validate({KEY:policy,'method':data.get('method')})
    if errors:raise ValueError('；'.join(errors))
    return copy.deepcopy(policy)


def require_native_reads(root):
    for raw in root['workflow']['graph']['nodes']:
        data=raw['data']
        if data.get('type')!='http-request':continue
        if raw.get('parentId') or isinstance(data.get('desc'),str) and data['desc'].startswith(PREFIX):
            preserved(data,required=True)


def remap_templates(config,remap):
    def visit(value,depth=0):
        if depth>40:return value  # Root body validation rejects deeper structures.
        if isinstance(value,str):
            for source,field in re.findall(r'\{\{#([\w-]+)\.([\w]+)#\}\}',value):
                selector=remap([source,field])
                value=value.replace('{{#'+source+'.'+field+'#}}','{{#'+selector[0]+'.'+selector[1]+'#}}')
            return value
        if isinstance(value,list):return [visit(v,depth+1) for v in value]
        if isinstance(value,dict):return {k:visit(v,depth+1) for k,v in value.items()}
        return value
    for key in ('url','headers','params','body'):
        if key in config:config[key]=visit(config[key])
