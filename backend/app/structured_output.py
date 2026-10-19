"""Bounded explicit Dify LLM schema declarations, not model-output validation."""
import copy
import json
import math

FIELDS = ('structured_output_enabled', 'structured_output')
NOTE = ('结构化输出是给Dify与供应商的对象格式声明，不证明模型／插件支持或字段值符合业务。'
        '目标版本可能修复JSON或改写供应商schema（包括布尔类型）；依赖字段与类型的业务须增加明确校验并实际试跑。'
        '下游只声明整个structured_output为object，不推断嵌套属性类型，不把text当作已解析对象。')


def schema_errors(schema):
    errors = []
    try:
        if len(json.dumps(schema, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 64000:
            return ['schema最多64000字节，不截断后生成。']
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return ['schema须为有限JSON对象，不能含循环、非JSON值或非法编码。']
    remaining = [200]

    def visit(row, path, depth):
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 8:
            errors.append('schema最多200个类型节点、8层嵌套，不截断或展开外部引用。')
            return
        if not isinstance(row, dict):
            errors.append(f'{path}须为明确类型的schema对象。')
            return
        kind = row.get('type')
        if not isinstance(kind, str) or kind not in {'object', 'array', 'string', 'number', 'integer', 'boolean'}:
            errors.append(f'{path}.type仅支持object／array／string／number／integer／boolean。')
            return
        extra = {
            'object': {'properties', 'required', 'additionalProperties'},
            'array': {'items', 'minItems', 'maxItems'},
            'string': {'minLength', 'maxLength'},
            'number': {'minimum', 'maximum'},
            'integer': {'minimum', 'maximum'},
            'boolean': set(),
        }[kind]
        if set(row) - {'type', 'title', 'description', 'enum'} - extra:
            errors.append(f'{path}含未适配关键字；不支持引用、组合、正则、默认值或未知规则，不会删除后生成。')
        for field in ('title', 'description'):
            if field in row and (not isinstance(row[field], str) or len(row[field]) > 4000):
                errors.append(f'{path}.{field}须为最多4000字符文本。')
        if 'enum' in row:
            values = row['enum']
            if kind not in {'string', 'number', 'integer', 'boolean'} or not isinstance(values, list) or not 1 <= len(values) <= 100:
                errors.append(f'{path}.enum仅支持1—100项同类型标量。')
            else:
                def matches(value):
                    if kind == 'string': return isinstance(value, str)
                    if kind == 'boolean': return type(value) is bool
                    if kind == 'integer': return type(value) is int
                    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))
                if not all(matches(v) for v in values):
                    errors.append(f'{path}.enum与声明类型不一致，不转换值。')
                elif any(value == previous for i, value in enumerate(values) for previous in values[:i]):
                    errors.append(f'{path}.enum不能重复。')
        if kind == 'object':
            props = row.get('properties')
            if not isinstance(props, dict) or len(props) > 50 or any(not isinstance(k, str) or not k or len(k) > 128 or any(ord(c) < 32 for c in k) for k in props):
                errors.append(f'{path}.properties须为最多50个有效命名属性，不猜字段。')
                return
            if row.get('additionalProperties') is not False:
                errors.append(f'{path}须明确additionalProperties=false，不擅自限制或放开额外字段。')
            required = row.get('required', [])
            if not isinstance(required, list) or not all(isinstance(v, str) and v in props for v in required) or len(set(required)) != len(required):
                errors.append(f'{path}.required须为properties内的唯一属性名列表。')
            for i, child in enumerate(props.values()): visit(child, f'{path}.properties[{i+1}]', depth+1)
        elif kind == 'array':
            visit(row.get('items'), f'{path}.items', depth+1)
        if kind in {'string', 'array', 'number', 'integer'}:
            low, high = ('minLength', 'maxLength') if kind == 'string' else ('minItems', 'maxItems') if kind == 'array' else ('minimum', 'maximum')
            for field in (low, high):
                if field not in row: continue
                value = row[field]
                if kind in {'string', 'array'}:
                    valid = type(value) is int and 0 <= value <= 1000000
                else:
                    valid = type(value) in (int, float) and (type(value) is int or math.isfinite(value))
                if not valid: errors.append(f'{path}.{field}须为有效有限范围值，长度／数量限0—1000000整数。')
            if low in row and high in row and type(row[low]) in (int, float) and type(row[high]) in (int, float) and row[low] > row[high]:
                errors.append(f'{path}最小值不能大于最大值，不交换或修正。')

    if not isinstance(schema, dict) or schema.get('type') != 'object':
        return ['首批结构化输出schema根类型须为object，数组／标量根尚未适配。']
    visit(schema, 'schema', 0)
    return list(dict.fromkeys(errors))


def validate(config):
    if not any(field in config for field in FIELDS): return []
    if type(config.get('structured_output_enabled')) is not bool:
        return ['结构化输出须明确structured_output_enabled布尔值，不根据schema存在自动开启。']
    value = config.get('structured_output')
    if value is None and config['structured_output_enabled'] is False: return []
    if not isinstance(value, dict) or set(value) != {'schema'}:
        return ['structured_output须为仅包含schema的对象，不使用未解析JSON文字或忽略字段。']
    if value['schema'] == {} and config['structured_output_enabled'] is False: return []
    return schema_errors(value['schema'])


def native(config):
    errors = validate(config)
    if errors: raise ValueError('结构化输出配置无效：'+'；'.join(errors))
    return {field: copy.deepcopy(config[field]) for field in FIELDS if field in config}


def output_type(config):
    return 'object' if config.get('structured_output_enabled') is True and not validate(config) else None
