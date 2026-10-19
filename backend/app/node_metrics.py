"""Whitelisted diagnostic measurements; never sum parent and child usage."""
import re
from .execution_costs import amount,tokens


def extract(row,sanitize):
    notes=[];meta=row.get('execution_metadata')
    if meta is None:meta={}
    elif not isinstance(meta,dict):meta={};notes.append('execution_metadata格式无效，只保留明确字段。')
    elapsed=amount(row.get('elapsed_time'));total=tokens(meta.get('total_tokens'));price=amount(meta.get('total_price'))
    currency=meta.get('currency');currency=currency if isinstance(currency,str) and re.fullmatch('[A-Z]{3}',currency) else None
    for key,value,raw in [('elapsed_time',elapsed,row.get('elapsed_time')),('total_tokens',total,meta.get('total_tokens')),('total_price',price,meta.get('total_price')),('currency',currency,meta.get('currency'))]:
        if raw is not None and value is None:notes.append(f'{key}无效或超过已支持范围，显示未知，不按0计算。')
    context={}
    for key in ('iteration_id','loop_id'):
        value=meta.get(key)
        if isinstance(value,str) and 0<len(value)<=128:context[key]=sanitize(value)
        elif value is not None:notes.append(f'{key}格式无效，不推断容器身份。')
    for key in ('iteration_index','loop_index','retry_index'):
        value=row.get(key) if key=='retry_index' else meta.get(key)
        if type(value) is int and 0<=value<=10**9:context[key]=value
        elif value is not None:notes.append(f'{key}格式无效，不推断索引。')
    return {'elapsed_seconds':elapsed,'total_tokens':total,'reported_price':price,'currency':currency,'cost_known':price is not None and currency is not None,'context':context,'notes':notes,'basis':'dify_node_execution_fields','verification':'reported_metrics_not_provider_bill'}
