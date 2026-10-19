"""Validate the supported native text bodies without sending or repairing them."""
import json,math,re

TYPES={'none','raw-text','json','x-www-form-urlencoded','form-data'}
SECRET={'apikey','authorization','token','secret','password','credential','credentials','cookie'}


def validate(body):
    errors,warnings=[],[]
    if body is None:return errors,warnings
    if not isinstance(body,dict) or set(body)-{'type','data'} or not isinstance(body.get('type'),str) or body['type'] not in TYPES:
        return ['HTTP 请求体仅支持 none/raw-text/json/纯文字表单；文件／binary及未知字段未适配，不能忽略后通过。'],warnings
    kind=body['type'];raw=body.get('data',[])
    # Native compatibility: old exports can contain a single textual data string.
    rows=[{'type':'text','key':'','value':raw}] if isinstance(raw,str) else raw
    if not isinstance(rows,list) or len(rows)>100:return ['HTTP body.data 须为最多100项原生文字结构或兼容的单个字符串。'],warnings
    if kind=='none' and rows:errors.append('HTTP none 请求体须为空；Dify 会忽略其data，不能保存后假装已发送。')
    if kind in {'raw-text','json'} and len(rows)!=1:errors.append('HTTP raw-text/json 须恰好一个文字项；完整文本放入该项value，不按多个字段自动拼接。')
    keys=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'type','key','value','file'} or row.get('type')!='text' or row.get('file') not in (None,[]):
            errors.append('HTTP 文字请求体每项必须明确type=text；文件引用、value_selector或未知字段未适配。');continue
        key,value=row.get('key',''),row.get('value','')
        if not isinstance(key,str) or not isinstance(value,str):errors.append('HTTP 请求体key/value必须为字符串，不隐式转换。');continue
        try:key.encode('utf-8');encoded=value.encode('utf-8')
        except UnicodeEncodeError:errors.append('HTTP 请求体字段包含无法编码的Unicode，请修正文字；不会回显原值。');continue
        if len(key)>256 or len(encoded)>120000:errors.append('HTTP 请求体文字超过支持范围；key最多256字，value最多120000字节。')
        if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:\bBearer\s+[A-Za-z0-9_.-]{16,})',value):errors.append('HTTP 请求体疑似含明文密钥，不得写入DSL；请用已适配的认证秘密引用。')
        if kind in {'raw-text','json'} and key:errors.append('HTTP raw-text/json 的key会被忽略，须为空；字段对象请完整写入value。')
        if kind in {'form-data','x-www-form-urlencoded'}:
            if not key or key in keys:errors.append('HTTP 文字表单须有非空唯一key；重复键会被原生字典覆盖，不能假装全部保留。')
            keys.add(key)
            if re.sub('[^a-z0-9]','',key.lower()) in SECRET:errors.append('HTTP 表单不得嵌入凭据字段，请使用已适配的认证秘密引用。')
        if kind=='json':
            def unique(pairs):
                out={}
                for name,child in pairs:
                    try:name.encode('utf-8')
                    except UnicodeEncodeError:raise ValueError('invalid-unicode') from None
                    if name in out:raise ValueError('duplicate')
                    if re.sub('[^a-z0-9]','',name.lower()) in SECRET:raise ValueError('secret')
                    out[name]=child
                return out
            def constant(text):raise ValueError('non-finite')
            candidate=re.sub(r'\{\{#.*?#\}\}','0',value)
            try:
                parsed=json.loads(candidate,object_pairs_hook=unique,parse_constant=constant)
                pending=[(parsed,0)];count=0
                while pending:
                    item,depth=pending.pop();count+=1
                    if depth>40 or count>20000:raise ValueError('body-limit')
                    if isinstance(item,dict):pending.extend((v,depth+1) for v in item.values())
                    elif isinstance(item,list):pending.extend((v,depth+1) for v in item)
                    elif type(item) is float and not math.isfinite(item):raise ValueError('non-finite')
                    elif isinstance(item,str):
                        try:item.encode('utf-8')
                        except UnicodeEncodeError:raise ValueError('invalid-unicode') from None
                        if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:\bBearer\s+[A-Za-z0-9_.-]{16,})',item):raise ValueError('secret-literal')
            except (ValueError,RecursionError) as exc:
                reason=str(exc)
                if reason=='secret':errors.append('HTTP JSON 请求体不得嵌入凭据字段；实际密钥不能放入DSL。')
                elif reason=='secret-literal':errors.append('HTTP JSON 字符串疑似含明文密钥，包括转义后的内容；不得写入DSL。')
                elif reason=='duplicate':errors.append('HTTP JSON 请求体有重复字段，不依赖解析器覆盖或修补。')
                elif reason=='non-finite':errors.append('HTTP JSON 请求体不得包含NaN／Infinity／溢出数值。')
                elif reason=='body-limit' or isinstance(exc,RecursionError):errors.append('HTTP JSON 请求体超过40层或20000项的静态支持范围，不截断或修补后通过。')
                elif reason=='invalid-unicode':errors.append('HTTP JSON 请求体包含无法编码的Unicode，请修正文字；不会回显原值。')
                elif '{{#' not in value:errors.append('HTTP JSON 字面量不是严格有效JSON；不会自动修补后当作原业务请求。')
                else:errors.append('HTTP JSON 模板骨架无法安全核对，不依赖平台修补推断业务请求；请由代码产生完整JSON后引用。')
            if '{{#' in value:warnings.append('HTTP JSON 含动态模板，只核对结构和变量引用，最终转义／类型／序列化须实际验证；建议先由代码产生完整JSON，不保证插入任意用户文字仍合法。')
    return list(dict.fromkeys(errors)),list(dict.fromkeys(warnings))
