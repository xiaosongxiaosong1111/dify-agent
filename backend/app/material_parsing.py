"""Validate uploaded text syntax without rewriting or executing its contents."""
import json
import re
import yaml

NONFINITE=re.compile(r'"(?:[^"\\]|\\.)*"|(?P<constant>-?Infinity|NaN)',re.DOTALL)


def located(format_name,line,column):
    return ValueError(f'{format_name}错误：第{line}行，第{column}列。请修正原文件后重新上传；未将本次内容标记为已解析，未展示错误附近原文。')


def decode_text(raw,suffix):
    content=raw[3:] if raw.startswith(b'\xef\xbb\xbf') else raw
    try:text=content.decode('utf-8')
    except UnicodeDecodeError as exc:
        prefix=content[:exc.start].decode('utf-8')
        raise located('UTF-8编码',prefix.count('\n')+1,len(prefix.rsplit('\n',1)[-1])+1) from None
    if len(text)>100000:raise ValueError('文本超过当前10万字处理上限，请拆分；本次没有静默截断原文。')
    try:
        if suffix=='.json':
            json.loads(text)
            # Python accepts these extensions; JSON material must use JSON syntax.
            # Quoted examples are skipped and the original text is never serialized.
            for match in NONFINITE.finditer(text):
                if match.group('constant'):
                    raise json.JSONDecodeError('nonstandard numeric constant',text,match.start())
        elif suffix in {'.yaml','.yml'}:
            # Compose nodes only: check syntax/anchors but never construct tags,
            # expand aliases, execute objects, or replace source text with values.
            for _ in yaml.compose_all(text,Loader=yaml.SafeLoader):pass
    except json.JSONDecodeError as exc:raise located('JSON格式',exc.lineno,exc.colno) from None
    except yaml.YAMLError as exc:
        mark=getattr(exc,'problem_mark',None)
        if mark is not None:raise located('YAML格式',mark.line+1,mark.column+1) from None
        raise ValueError('YAML格式无法校验，请修正原文件后重新上传；未展示原文。') from None
    except (RecursionError,ValueError,OverflowError):
        raise ValueError('结构化材料超出当前安全解析范围，请减少嵌套或拆分后重新上传；本次未解析，也未截断原文。') from None
    return text
