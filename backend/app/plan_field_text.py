"""Lossless JSON-field transport for the explicit manual plan save only."""
import copy
from .plan_text_codec import parse

MAX_FIELD_BYTES = 128000
ERROR = '结构化输出JSON须为128000字节内无重复键、非有限数或坏编码的完整对象；未保存、修复或回显原文。'


def normalize(plan):
    result = copy.deepcopy(plan)

    def visit(nodes, nested=False):
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get('config'), dict):
                continue
            cfg = node['config']
            if node.get('type') == 'llm' and isinstance(cfg.get('structured_output'), str):
                try:
                    text = cfg['structured_output']
                    if len(text.encode('utf-8')) > MAX_FIELD_BYTES:
                        raise ValueError()
                    cfg['structured_output'] = parse(text)
                except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
                    raise ValueError(ERROR) from None
            if not nested and node.get('type') in {'iteration', 'loop'}:
                visit(cfg.get('nodes'), True)

    visit(result.get('nodes'))
    return result
