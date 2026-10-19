"""Explicit scalar form declarations and preflight; never coerce submitted values."""
import math

TYPES = {'text-input': 'string', 'paragraph': 'string', 'select': 'string', 'number': 'number', 'checkbox':'boolean', 'json_object':'object'}


def finite_number(value):
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def declared_type(rows, name):
    matches = [row for row in rows if isinstance(row, dict) and row.get('variable') == name] if isinstance(rows, list) else []
    kind = matches[0].get('type', 'text-input') if len(matches) == 1 else None
    from .file_inputs import TYPES as FILE_TYPES
    return {**TYPES,**FILE_TYPES}.get(kind) if isinstance(kind, str) else None


def text_metadata_errors(row):
    errors=[]
    kind=row.get('type','text-input')
    if isinstance(kind,str) and kind in {'text-input','paragraph'}:
        allowed={'variable','label','type','required','default','options','max_length','description','hide'}
        if set(row)-allowed:errors.append('文字入口含未适配字段，不会省略业务约束后生成。')
        if any(key in row and not isinstance(row[key],str) for key in ('label','description')):errors.append('文字入口label／description须为文本，不自动转换。')
        if 'hide' in row and type(row['hide']) is not bool:errors.append('文字入口hide须明确布尔值。')
        limit=row.get('max_length')
        if limit is not None and (type(limit) is not int or not 0<=limit<=9007199254740991):errors.append('文字max_length须为0—9007199254740991的整数或null；上界是本批无损编辑范围而非平台全局限制，0／null表示原生不限字符，不会截断或舍入。')
        if row.get('options',[])!=[]:errors.append('文字入口不会按options限定选项；请明确使用select或移除不生效规则，不自动转换类型。')
    return errors


def validate_variable(row):
    errors = []
    kind = row.get('type', 'text-input')
    from .file_inputs import TYPES as FILE_TYPES,validate as validate_file
    from .json_inputs import validate as validate_json
    if kind=='json_object':return validate_json(row)
    if isinstance(kind,str) and kind in FILE_TYPES:return validate_file(row)
    if not isinstance(kind, str) or kind not in TYPES:
        return ['当前支持 text-input／paragraph／number／select／checkbox 输入；其他类型尚待适配']
    if type(row.get('required', True)) is not bool:
        errors.append('required 必须是布尔值')
    errors.extend(text_metadata_errors(row))
    if kind in {'number', 'select', 'checkbox'}:
        allowed = {'variable', 'label', 'type', 'required', 'default', 'options', 'max_length', 'description', 'hide'}
        if set(row) - allowed:
            errors.append('数字／选项／布尔输入含未适配字段，不会忽略后生成')
        if 'label' in row and not isinstance(row['label'], str): errors.append('label 必须是文本')
        if 'description' in row and not isinstance(row['description'], str): errors.append('description 必须是文本')
        if 'hide' in row and type(row['hide']) is not bool: errors.append('hide 必须是布尔值')
        if row.get('max_length') is not None and (type(row['max_length']) is not int or row['max_length'] <= 0):
            errors.append('max_length 如有值须为正整数；数字／选项／布尔输入不据此限制范围')
        if row.get('required', True) is False and 'default' not in row:
            errors.append('可选数字／选项／布尔输入须明确 default，首批不支持下游空值类型')
    if kind == 'checkbox':
        if row.get('options',[]) != []:errors.append('布尔输入不支持options。')
        if 'default' in row and type(row['default']) is not bool:errors.append('布尔default须为JSON true／false，不转换文本、数字或null。')
    elif kind == 'select':
        options = row.get('options')
        if not isinstance(options, list) or not 1 <= len(options) <= 100 or any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in options):
            errors.append('options 须为 1—100 项非空文本，每项最多 1000 字')
        elif len(set(options)) != len(options): errors.append('options 不能重复')
        if 'default' in row and (not isinstance(row['default'], str) or not isinstance(options, list) or row['default'] not in options):
            errors.append('select 的 default 必须属于 options，不能默选第一项')
    elif kind == 'number':
        if row.get('options', []) != []: errors.append('number 不支持 options')
        if 'default' in row and not finite_number(row['default']): errors.append('number 的 default 须为有限 JSON 数字，不能是布尔值或数字文本')
    elif 'default' in row and not isinstance(row['default'], str):
        errors.append('字符串变量的 default 必须是字符串')
    return errors


def check_values(rows, values, *, file_validator=None):
    """Validate omission/default semantics without changing input or run identity."""
    from .file_inputs import has_files,RUNTIME_LIMIT
    if has_files(rows) and file_validator is None:raise ValueError(RUNTIME_LIMIT)
    names = {row['variable'] for row in rows}
    if not isinstance(values, dict) or set(values) - names:
        raise ValueError('试跑输入包含未声明变量；不会忽略后派发。')
    for row in rows:
        name, kind = row['variable'], row.get('type', 'text-input')
        value = values.get(name)
        if value is None:
            if row.get('required', True): raise ValueError(f'输入 {name} 为必填，不能以默认值替代缺失输入。')
            value = row.get('default')
            if value is None: continue
        if kind in {'file','file-list'} and file_validator is not None:
            file_validator(row,value)
        elif kind=='json_object':
            from .json_inputs import validate_value
            validate_value(row.get('json_schema'),value)
        elif kind == 'number':
            if not finite_number(value): raise ValueError(f'输入 {name} 须为有限 JSON 数字；不自动转换文本、布尔值或空串。')
        elif kind=='checkbox':
            if type(value) is not bool:raise ValueError(f'输入 {name} 须为JSON true／false；不自动转换0／1、文本或空串。')
        elif not isinstance(value, str): raise ValueError(f'输入 {name} 须为文本。')
        elif kind == 'select' and value not in row['options']: raise ValueError(f'输入 {name} 须属于已配置的 options。')
        elif kind in {'text-input', 'paragraph'} and type(row.get('max_length')) is int and row['max_length'] > 0 and len(value) > row['max_length']:
            raise ValueError(f'输入 {name} 超过已配置的 max_length。')


def preflight(root, values, *, source_inputs=None, file_validator=None):
    if root.get('app', {}).get('mode') == 'advanced-chat':
        schema = form_schema(root)
        if len(schema['fields']) > 1:
            if 'conversation_id' in values and source_inputs is None:
                raise ValueError('带自定义入口的Chatflow续聊须选择当前可信的成功自由运行来源，不能手填conversation_id；不忽略参数，可明确选择新会话或固定多轮。')
            submitted={key:value for key,value in values.items() if key!='conversation_id'} if source_inputs is not None else values
            check_values(schema['fields'], submitted)
            if source_inputs is not None:
                original={key:value for key,value in source_inputs.items() if key!='conversation_id'}
                check_values(schema['fields'],original)
                if not same_initial_parameters({k:v for k,v in submitted.items() if k!='query'},{k:v for k,v in original.items() if k!='query'}):
                    raise ValueError('本次自定义参数与所选会话原始输入不同（包括省略／null），未自动继承、修改或忽略；请明确恢复原参数或开始新会话。')
            if not values['query'].strip(): raise ValueError('Chatflow 试跑需要非空 query 文本。')
        return
    if root.get('app', {}).get('mode') != 'workflow': return
    if any(n.get('data',{}).get('type')=='trigger-schedule' for n in root['workflow']['graph']['nodes']):raise ValueError('定时触发没有普通start输入表单，手动输入不能验证实际调度。')
    starts = [n for n in root['workflow']['graph']['nodes'] if n.get('data', {}).get('type') == 'start']
    rows = starts[0]['data'].get('variables', []) if len(starts) == 1 else []
    from .file_inputs import has_files,RUNTIME_LIMIT
    if has_files(rows) and file_validator is None:raise ValueError(RUNTIME_LIMIT)
    if len(starts)!=1 or not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('variable'),str) or not row['variable'] or not isinstance(row.get('type','text-input'),str) for row in rows):
        raise ValueError('最终DSL入口声明结构不完整，未派发。')
    if len({row['variable'] for row in rows})!=len(rows):raise ValueError('最终DSL入口变量名重复，未派发。')
    metadata_errors=[message for row in rows for message in text_metadata_errors(row)]
    if metadata_errors:raise ValueError('最终DSL文字入口声明未适配：'+'；'.join(metadata_errors))
    # Preserve legacy text-only runtime behavior; typed forms use the final artifact.
    if not any(isinstance(row, dict) and row.get('type') in {'number', 'select', 'checkbox', 'json_object','file','file-list'} for row in rows): return
    if len(starts) != 1 or any(not isinstance(row, dict) or not isinstance(row.get('variable'), str) for row in rows):
        raise ValueError('最终 DSL 入口声明结构不完整。')
    for row in rows:
        errors = validate_variable(row)
        if errors: raise ValueError('最终 DSL 入口声明无效：' + '；'.join(errors))
    check_values(rows, values,file_validator=file_validator)


def form_schema(root):
    mode = root.get('app', {}).get('mode')
    if mode not in {'workflow', 'advanced-chat'}:
        raise ValueError('入口表单仅适配 Workflow／Chatflow，不能改变用户应用类型。')
    if any(n.get('data',{}).get('type')=='trigger-schedule' for n in root['workflow']['graph']['nodes']):raise ValueError('定时触发没有普通start输入表单，手动输入不能验证实际调度。')
    starts = [n for n in root['workflow']['graph']['nodes'] if n.get('data', {}).get('type') == 'start']
    if len(starts) != 1: raise ValueError('最终成果须有唯一开始节点。')
    rows = starts[0]['data'].get('variables', [])
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('入口表单最多适配 100 个明确变量，不会截断后填写。')
    from .file_inputs import has_files,RUNTIME_LIMIT
    if has_files(rows):raise ValueError(RUNTIME_LIMIT)
    from .json_inputs import has_objects,NOTE as JSON_INPUT_NOTE
    if mode!='workflow' and has_objects(rows):raise ValueError('JSON对象入口首批仅Workflow；Chatflow初始字典参数及会话生命周期尚未适配，不自动换类型。')
    names, fields = set(), []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('variable'), str) or not row['variable'] or row['variable'] in names:
            raise ValueError('最终成果入口变量名须完整且唯一。')
        errors=validate_variable(row)
        if errors: raise ValueError('入口表单未适配该声明：'+'；'.join(errors))
        if any(key in row and not isinstance(row[key],str) for key in ('label','description')):
            raise ValueError('入口 label／description 须为文本，不会猜测显示。')
        names.add(row['variable'])
        fields.append({key:row[key] for key in ('variable','label','type','required','default','options','max_length','description','hide','json_schema') if key in row})
    if mode == 'advanced-chat':
        if names & {'query','conversation_id'}:
            raise ValueError('Chatflow 的 query／conversation_id 为试跑传输保留名，不能声明为自定义入口。')
        fields.insert(0, {'variable':'query','label':'本轮用户问题（sys.query）','type':'paragraph','required':True})
    return {'start_id':starts[0]['id'],'app_mode':mode,'fields':fields,'verification':'static_only',
            'note':'从当前最终成果读取入口，不使用旧计划。填写只改变未派发输入；没有调用模型或Dify，业务范围及默认值仍以已确认方案为准。'+('Chatflow问题经query传入sys.query；自定义入口支持新会话／参数一致的固定多轮，或选择当前可信成功来源沿用原参数续聊；初始参数须完整一致（含省略／null），不能手填会话ID、更新参数或自动填值。' if mode=='advanced-chat' and rows else '')+(JSON_INPUT_NOTE if has_objects(rows) else '')}


def same_initial_parameters(left, right):
    """JSON number is one type: 1 and 1.0 agree; bool/null/omission stay distinct."""
    if not isinstance(left,dict) or not isinstance(right,dict) or left.keys()!=right.keys(): return False
    for key,value in left.items():
        other=right[key]
        if finite_number(value) and finite_number(other):
            if value!=other:return False
        elif type(value) is not type(other) or type(value) not in (str,bool,type(None)) or value!=other:return False
    return True


def require_stable_chat_turns(case):
    """Only query changes; no implicit inheritance/default filling across turns."""
    if not isinstance(case, dict) or not isinstance(case.get('followups'), list):
        raise ValueError('固定多轮须有明确后续轮次，不猜输入。')
    first = None
    for index, turn in enumerate([case, *case['followups']]):
        value = turn.get('input') if isinstance(turn, dict) else None
        if not isinstance(value, dict) or 'conversation_id' in value:
            raise ValueError(f'第{index+1}轮须为不含conversation_id的输入对象，不能手工复用会话。')
        custom = {key:field for key,field in value.items() if key != 'query'}
        if index == 0: first = custom
        elif not same_initial_parameters(first, custom):
            raise ValueError(f'第{index+1}轮自定义初始输入与首轮不同；首批固定多轮须完全一致（含省略／null），不自动复制、忽略或更新会话参数。')


def chat_case_preflight(root, case):
    """Fresh multi-turn cases keep every custom initial input exactly stable."""
    schema = form_schema(root)
    if schema['app_mode'] != 'advanced-chat' or len(schema['fields']) <= 1: return
    require_stable_chat_turns(case)
    turns = [case, *case.get('followups', [])]
    for index, turn in enumerate(turns):
        values = turn.get('input') if isinstance(turn, dict) else None
        if not isinstance(values, dict): raise ValueError(f'第{index+1}轮输入须为JSON对象，未派发任何轮次。')
        try: check_values(schema['fields'], values)
        except ValueError as exc: raise ValueError(f'第{index+1}轮输入未通过最终入口检查：{exc} 未派发任何轮次。') from None
        if not values.get('query', '').strip():
            raise ValueError(f'第{index+1}轮须有非空query，未派发任何轮次。')
