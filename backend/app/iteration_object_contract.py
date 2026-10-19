"""Explicit object outcome protocol. Generates text; never executes user code."""
import ast
import copy
import json
import re

from .structured_output import schema_errors
from .structured_guard import CHECKER

MARKER = '# Sierra per-item object outcomes v1\n'
SUMMARY_MARKER = '# Sierra object iteration result summary v1\n'
SCHEMA_PREFIX = '_sierra_schema = '
SAFE_INT = 9007199254740991


def schema_contract(schema):
    errors = schema_errors(schema)
    if errors:
        raise ValueError('对象成功结果Schema无效：' + '；'.join(errors))
    # No unsafe JSON integers, including numeric bounds and enums. Do not round.
    def visit(value):
        if type(value) is int and abs(value) > SAFE_INT:
            raise ValueError('Schema整数须在±9007199254740991内，不舍入或改写规则。')
        if isinstance(value, dict):
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(schema)
    return json.loads(json.dumps(schema, ensure_ascii=False, sort_keys=True, allow_nan=False))


def schema_from_text(text):
    from .plan_text_codec import parse
    if not isinstance(text, str) or len(text.encode('utf-8')) > 64000:
        raise ValueError('对象结果Schema须为64000 UTF-8字节内的完整JSON对象。')
    try:
        value = parse(text)
    except ValueError:
        raise ValueError('对象结果Schema须为无重复键、非有限数或坏编码的完整JSON对象，不修复或回显原文。') from None
    return schema_contract(value)


SAFETY = '''
def _sierra_safe(value, remaining, depth=0):
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 16: return False
    if type(value) is dict:
        if any(type(k) is not str for k in value): return False
        return all(_sierra_safe(v, remaining, depth+1) for v in value.values())
    if type(value) is list:
        return all(_sierra_safe(v, remaining, depth+1) for v in value)
    if type(value) in (str, bool): return True
    if type(value) is int: return -9007199254740991 <= value <= 9007199254740991
    if type(value) is float: return _sierra_math.isfinite(value)
    return False

def _sierra_object_valid(value):
    if type(value) is not dict or not _sierra_safe(value, [20000]): return False
    if not _sierra_check(value, _sierra_schema): return False
    try:
        return len(_sierra_json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')) <= 64000
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return False
'''


def guard():
    checker = CHECKER[:CHECKER.index('\n\ndef main(')]
    checker = checker.replace('_check', '_sierra_check').replace('math.', '_sierra_math.')
    checker = checker.replace('not value.is_integer()', '(not value.is_integer() or abs(value) > 9007199254740991)')
    return '\nimport json as _sierra_json\nimport math as _sierra_math\n' + checker + SAFETY


TAIL = '''
def main(item: str, sierra_index: int) -> dict:
    if type(item) is not str or type(sierra_index) is not int or sierra_index < 0:
        raise TypeError('Declared iteration input or index mismatch')
    try:
        result = _sierra_calculate(item)
    except (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError, OverflowError) as _sierra_error:
        for _sierra_kind in (ValueError, TypeError, ZeroDivisionError, KeyError, IndexError, OverflowError):
            if isinstance(_sierra_error, _sierra_kind):
                return {'outcome': {'index': sierra_index, 'ok': False, 'value': None, 'error_category': _sierra_kind.__name__}}
        raise
    if type(result) is not dict or set(result) != {'result'} or not _sierra_object_valid(result['result']):
        raise TypeError('Declared safe object output schema mismatch')
    return {'outcome': {'index': sierra_index, 'ok': True, 'value': result['result'], 'error_category': None}}
'''


def wrapped_object(code, schema):
    from .iteration_outcomes import check
    schema = schema_contract(schema)
    fn = check(code, 'item', 'result', allow_json=True)
    lines = code.splitlines(keepends=True)
    lines[fn.lineno-1], count = re.subn(r'^def[ \t]+main(?=[ \t]*\()', 'def _sierra_calculate', lines[fn.lineno-1], count=1)
    if count != 1: raise ValueError('函数头写法尚未适配，原文保持。')
    return MARKER + SCHEMA_PREFIX + repr(schema) + '\n' + ''.join(lines) + '\n' + guard() + TAIL


def original_object(code):
    if not isinstance(code, str) or not code.startswith(MARKER) or len(code.encode('utf-8')) > 180000:
        raise ValueError('对象逐项封装未匹配完整协议，未猜测Schema或覆盖手改。')
    tail = '\n' + guard() + TAIL
    try:
        header, body = code[len(MARKER):].split('\n', 1)
        if not header.startswith(SCHEMA_PREFIX) or not body.endswith(tail): raise ValueError()
        schema = schema_contract(ast.literal_eval(header[len(SCHEMA_PREFIX):]))
        raw = body[:-len(tail)]
        tree = ast.parse(raw)
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        if len(fns) != 1 or fns[0].name != '_sierra_calculate': raise ValueError()
        lines = raw.splitlines(keepends=True)
        lines[fns[0].lineno-1], count = re.subn(r'^def[ \t]+_sierra_calculate(?=[ \t]*\()', 'def main', lines[fns[0].lineno-1], count=1)
        original = ''.join(lines)
        if count != 1 or wrapped_object(original, schema) != code: raise ValueError()
        return original, copy.deepcopy(schema)
    except (ValueError, SyntaxError, TypeError, IndexError, RecursionError):
        raise ValueError('对象原代码、Schema或封装已改变，未猜测规则或覆盖手改。') from None


def summary_object(schema, summary_code):
    schema = schema_contract(schema)
    body = summary_code[summary_code.index('\ndef main('):]
    body = body.replace("not isinstance(row['value'], str)", "not _sierra_object_valid(row['value'])")
    return SUMMARY_MARKER + SCHEMA_PREFIX + repr(schema) + '\n' + guard() + body
