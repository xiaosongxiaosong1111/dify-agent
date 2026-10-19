"""Explicit model completion settings; connection credentials never belong here."""
import math
import re
import copy

def validate_model_parameters(parameters):
    if not isinstance(parameters,dict) or len(parameters)>30:
        raise ValueError('模型扩展参数必须为最多 30 项的对象。')
    for name,value in parameters.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',name) or name in {'temperature','max_tokens'} or (name.lower() in {'api_key','token','access_token','refresh_token','authorization','endpoint','endpoint_url','base_url'} or any(x in name.lower() for x in ('secret','credential','password'))):
            raise ValueError('扩展参数名称不支持或属于连接配置；Temperature 和 Max tokens 请用专用字段。')
        if isinstance(value,bool):continue
        if isinstance(value,(int,float)) and math.isfinite(value):continue
        if isinstance(value,str) and len(value)<=1024:continue
        raise ValueError('扩展参数仅接受布尔值、有限数字或最多 1024 字的文本。')


def completion_parameters(configuration):
    extra=configuration.get('model_parameters',{})
    validate_model_parameters(extra)
    return {'temperature':configuration.get('temperature',0.2),'max_tokens':configuration.get('max_tokens',2048),**extra}


def validate_node_model(model):
    """A selected node model replaces the whole choice, never hidden inheritance."""
    if not isinstance(model,dict) or set(model)!={'provider','name','mode','completion_params'}:
        raise ValueError('节点模型须完整填写 provider、name、mode、completion_params，不支持局部继承或其他字段。')
    if model['mode']!='chat':
        raise ValueError('节点独立模型目前只支持明确的 mode=chat。')
    if any(not isinstance(model[k],str) or not model[k] or model[k]!=model[k].strip() or len(model[k])>256 or any(ord(c)<32 for c in model[k]) for k in ('provider','name')):
        raise ValueError('节点模型供应商和型号须为明确的有效标识，不能使用空值或猜测。')
    params=model['completion_params']
    if not isinstance(params,dict) or not {'temperature','max_tokens'}<=set(params):
        raise ValueError('节点模型须明确 temperature 和 max_tokens 及完整扩展参数，不继承其他模型的旧值。')
    value=params['temperature']
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=2:
        raise ValueError('节点模型 temperature 须为 0—2 的有限数值。')
    if type(params['max_tokens']) is not int or not 1<=params['max_tokens']<=1000000:
        raise ValueError('节点模型 max_tokens 须为 1—1000000 的整数；实际上限仍须核对模型规则。')
    validate_model_parameters({k:v for k,v in params.items() if k not in {'temperature','max_tokens'}})


def resolve_node_model(config,configuration):
    if 'model' in config:
        validate_node_model(config['model'])
        return copy.deepcopy(config['model'])
    return {'provider':configuration['dify_model_provider'],'name':configuration['dify_model'],'mode':'chat','completion_params':completion_parameters(configuration)}


def needs_task_model(plan):
    if not plan:return True
    from .iteration import plan_nodes
    return any(node.get('type') in ('llm','question-classifier','parameter-extractor') and (not isinstance(node.get('config'),dict) or 'model' not in node['config']) for node in plan_nodes(plan))
