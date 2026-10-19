"""Explicit Chatflow scalar state, root overwrites and numeric constant arithmetic."""
import copy,re,uuid,math

FIELDS={'name','var_type','initial_value','description','persistence_policy','unwritten_policy'}
SECRET_NAMES={'api_key','apikey','token','password','secret','authorization','credential'}


def safe_text(value,limit):
    if not isinstance(value,str) or len(value)>limit:return False
    try:value.encode('utf-8')
    except UnicodeError:return False
    return not re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer\s+[A-Za-z0-9_.-]{16,})',value)


TYPES={'string','number','boolean'}
ARITHMETIC={'+=','-=','*=','/='}

def safe_value(kind,value):
    if kind=='string':return safe_text(value,4000)
    if kind=='boolean':return type(value)is bool
    if kind=='number':return type(value)in (int,float) and abs(value)<=10**12 and math.isfinite(value)
    return False


def declarations(plan,mode):
    rows=plan.get('conversation_variables',[]);errors=[];types={}
    if not isinstance(rows,list) or len(rows)>12:return ['对话状态须为最多12项的明确声明数组，不截断或猜测。'],types
    if rows and mode!='advanced-chat':errors.append('持久对话状态只适配Chatflow，不改变Workflow或Agent类型。')
    for row in rows:
        if not isinstance(row,dict) or set(row)!=FIELDS:errors.append('对话状态须完整name/var_type/initial_value/description/persistence_policy/unwritten_policy，不支持未知或缺失设置。');continue
        name=row['name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',name) or name.lower() in SECRET_NAMES or name.startswith('__'):errors.append('状态名称须为字母开头的ASCII字母/数字/下划线，不使用凭据或保留名称。');continue
        if name in types:errors.append('对话状态名称重复，不用最后声明覆盖前者。')
        kind=row['var_type'];types[name]=kind if isinstance(kind,str) and kind in TYPES else None
        if types[name] is None:errors.append('首批持久状态只支持明确string/number/boolean，对象/数组/文件尚未适配。')
        if not safe_value(kind,row['initial_value']) or not safe_text(row['description'],255):errors.append('初始值必须匹配声明标量类型：文字最多4000字、number有限且绝对值<=10^12（原生float）、boolean须真正布尔；说明最多255字，无凭据或隐式转换。')
        if row['persistence_policy']!='per_conversation' or row['unwritten_policy']!='retain_current':errors.append('须明确每个conversation独立保存，未执行赋值时保留当前值；不猜重置或跨会话共享。')
    return errors,types


def validate_assignment(cfg,types,mode):
    errors=[];items=cfg.get('items')
    if mode!='advanced-chat':errors.append('根持久状态赋值只适配Chatflow；Workflow/Agent/容器内赋值尚未适配。')
    if set(cfg)!={'items'} or not isinstance(items,list) or not 1<=len(items)<=12:return errors+['赋值须完整items数组（1—12项），不忽略其他参数。']
    seen=set()
    for row in items:
        if not isinstance(row,dict) or set(row)!={'variable_selector','input_type','operation','value'}:errors.append('每项赋值须完整目标/input_type/operation/value，不补造参数。');continue
        target=row['variable_selector']
        if not isinstance(target,list) or len(target)!=2 or target[0]!='conversation' or not isinstance(target[1],str) or target[1] not in types:errors.append('赋值目标只允许当前已声明conversation标量状态，不写env/sys或未声明变量。');continue
        if target[1] in seen:errors.append('同节点不能重复更新同一状态，避免隐式项间读后写依赖。')
        seen.add(target[1])
        operation=row['operation']
        if not isinstance(operation,str) or operation not in {'over-write',*ARITHMETIC}:errors.append('仅支持显式over-write或数值常量+=、-=、*=、/=运算，不适配清空/追加/数组修改。')
        elif operation in ARITHMETIC:
            if types[target[1]]!='number':errors.append('算术更新只允许已声明number状态，不转换文字或布尔。')
            if row['input_type']!='constant':errors.append('原生v2算术只支持明确数值常量，不支持variable运算或猜测表达式。')
            if not safe_value('number',row['value']):errors.append('算术常量须为真正有限JSON数值，绝对值<=10^12，不转换文字/布尔。')
            elif operation=='/=' and row['value']==0:errors.append('状态除法常量不能为零（包括-0.0），不静默换值或忽略操作。')
        if row['input_type']=='constant':
            if not safe_value(types[target[1]],row['value']):errors.append('常量赋值须匹配目标标量类型与范围，不把文字数字/真假/数组转换，文字不得嵌入凭据。')
        elif row['input_type']=='variable':
            value=row['value']
            if not isinstance(value,list) or len(value)!=2 or not all(isinstance(v,str) and v for v in value):errors.append('变量赋值须明确两段来源selector，不把模板表达式当变量。')
        else:errors.append('input_type须明确constant或variable，不自动选择。')
    for row in items:
        if isinstance(row,dict) and row.get('input_type')=='variable':
            source=row.get('value')
            if isinstance(source,list) and len(source)==2 and source[0]=='conversation' and isinstance(source[1],str) and source[1] in seen:errors.append('首批不接受同节点读取正在更新的状态；请拆为明确串行根节点，不猜项间读后写顺序。')
    return errors


def native(plan,task):
    namespace=str(task.get('id') or task.get('name') or 'sierra-local')
    return [{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'sierra:conversation:'+namespace+':'+r['name'])),'name':r['name'],'value_type':{'string':'string','number':'float','boolean':'boolean'}[r['var_type']],'value':float(r['initial_value']) if r['var_type']=='number' else r['initial_value'],'description':r['description']} for r in plan.get('conversation_variables',[])]


def preserved(rows,mode):
    if not isinstance(rows,list):raise ValueError('原对话状态须为数组，不丢弃未知结构。')
    out=[];ids=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)-{'id','name','value_type','value','description','selector'} or not isinstance(row.get('value_type'),str) or row.get('value_type') not in {'string','float','boolean'}:raise ValueError('首批只保留原生string/float/boolean状态；integer/number泛型/数组/对象等未知类型不转换或删除后算完成。')
        try:key=str(uuid.UUID(row['id']))
        except (ValueError,TypeError,KeyError):raise ValueError('原对话状态缺少有效UUID，未重新分配来源身份。') from None
        if key in ids:raise ValueError('原对话状态UUID重复，未合并。')
        ids.add(key)
        if 'selector' in row and row['selector'] not in ([],['conversation',row.get('name')]):raise ValueError('原对话变量selector与名称不一致，未改写。')
        out.append({'name':row.get('name'),'var_type':{'string':'string','float':'number','boolean':'boolean'}[row['value_type']],'initial_value':copy.deepcopy(row.get('value')),'description':row.get('description',''),'persistence_policy':'per_conversation','unwritten_policy':'retain_current'})
    errors,_=declarations({'conversation_variables':out},mode)
    if errors:raise ValueError('原对话状态无法保留：'+'；'.join(errors))
    return out
