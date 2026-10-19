"""Allow-listed Dify resource metadata. Never return provider credentials."""
from __future__ import annotations
import math
import re
from urllib.parse import quote
from .dify import DifyError

MODEL_TYPES = {'llm', 'text-embedding', 'rerank', 'speech2text', 'tts', 'moderation'}

def label(value, fallback):
    if isinstance(value, dict):
        return next((value[k] for k in ('zh_Hans','en_US') if isinstance(value.get(k), str) and value[k]), fallback)
    return value if isinstance(value, str) and value else fallback


def number(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)


def models_metadata(payload, model_type):
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise DifyError('Dify 模型目录结构不兼容，未按空目录处理。')
    rows=[]
    for group in payload['data']:
        if not isinstance(group,dict) or not isinstance(group.get('provider'),str) or not group['provider'] or not isinstance(group.get('models'),list):
            raise DifyError('Dify 模型供应商目录结构不兼容。')
        for m in group['models']:
            if not isinstance(m,dict) or not isinstance(m.get('model'),str) or not m['model'] or not isinstance(m.get('status'),str):
                raise DifyError('Dify 模型条目结构不兼容。')
            properties=m.get('model_properties') or {}
            if not isinstance(properties,dict):raise DifyError('Dify 模型属性结构不兼容。')
            mode=properties.get('mode')
            active=m['status']=='active'
            supported=active and (model_type!='llm' or mode=='chat')
            rows.append({'provider':group['provider'],'provider_label':label(group.get('label'),group['provider']),
                         'model':m['model'],'label':label(m.get('label'),m['model']),'model_type':model_type,
                         'status':m['status'],'mode':mode if isinstance(mode,str) else None,'selectable':supported,
                         'features':[f for f in (m.get('features') or []) if isinstance(f,str)] if isinstance(m.get('features') or [],list) else [],
                         'context_size':properties.get('context_size') if number(properties.get('context_size')) else None,
                         'reason':('当前状态不可用：'+m['status']) if not active else ('当前编译器仅支持 chat 模式 LLM' if not supported else 'Dify 目录声明可用，实际调用仍需试跑')})
    return rows


def provider_path(provider):
    if not isinstance(provider,str) or len(provider)>256 or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',provider) or any(p in {'.','..'} for p in provider.split('/')):
        raise ValueError('模型供应商标识格式不正确。')
    return quote(provider,safe='/')


def parameter_metadata(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):raise DifyError('Dify 参数规则结构不兼容。')
    rules=[]
    for rule in payload['data']:
        if not isinstance(rule,dict) or not isinstance(rule.get('name'),str):raise DifyError('Dify 参数规则条目不兼容。')
        out={'name':rule['name'],'label':label(rule.get('label'),rule['name'])}
        for field in ('use_template','type','required'):
            if isinstance(rule.get(field),(str,bool)):out[field]=rule[field]
        for field in ('min','max','precision'):
            if number(rule.get(field)):out[field]=rule[field]
        default=rule.get('default')
        if isinstance(default,(str,bool)) or number(default):out['default']=default
        if isinstance(rule.get('options'),list):out['options']=[v for v in rule['options'] if isinstance(v,(str,bool)) or number(v)]
        rules.append(out)
    return rules


def datasets_metadata(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),list) or not isinstance(payload.get('has_more'),bool):raise DifyError('Dify 知识库目录结构不兼容。')
    rows=[]
    for row in payload['data']:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id']:raise DifyError('Dify 知识库条目不兼容。')
        out={'id':row['id']}
        for field in ('name','description','indexing_technique','permission','embedding_model','embedding_model_provider'):
            if isinstance(row.get(field),str):out[field]=row[field]
        for field in ('document_count','available_document_count','word_count'):
            if number(row.get(field)):out[field]=row[field]
        rows.append(out)
    return {'data':rows,'has_more':payload['has_more']}
