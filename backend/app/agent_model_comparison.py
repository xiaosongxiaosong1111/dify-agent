"""Readonly native Agent model differences; never adopts, defaults or calls models."""
import copy,math
from .agent_preservation import model_identity
from .model_parameters import validate_node_model
from .dsl_roundtrip import digest


def configuration(model):
    value=model_identity(model);params=copy.deepcopy(value['model_settings'])
    if not {'temperature','max_tokens'}<=set(params):
        raise ValueError('原生模型缺少明确Temperature或Max tokens，请先补齐参数；不能继承另一型号的旧值。')
    if 'response_format' in params:
        fmt=params['response_format']
        if not isinstance(fmt,dict) or set(fmt)!={'type'} or not isinstance(fmt['type'],str) or fmt['type'] not in {'text','json_object'}:
            raise ValueError('原生response_format无法完整表达为当前配置表单，不删除额外规则后给出建议。')
        params['response_format']=fmt['type']
    for parameter in params.values():
        if type(parameter) in (int,float) and (abs(parameter)>9007199254740991 or not math.isfinite(parameter)):
            raise ValueError('原生模型参数超出浏览器可精确表达的数值范围，不提供会舍入的配置参考；原文件仍保留。')
    try:validate_node_model({'provider':value['model_provider'],'name':value['model'],'mode':'chat','completion_params':params})
    except OverflowError as exc:raise ValueError('原生模型参数超出当前配置表单的数值范围，不舍入或删除后给出建议。') from exc
    except ValueError as exc:raise ValueError('原生模型参数不能完整映射到当前配置表单：'+str(exc)) from exc
    return {'dify_model_provider':value['model_provider'],'dify_model':value['model'],
        'temperature':params.pop('temperature'),'max_tokens':params.pop('max_tokens'),'model_parameters':params}


def model(root):
    if root.get('app',{}).get('mode')!='agent':raise ValueError('这里只比较原生Agent，不将其他应用转换为Agent。')
    binding=root.get('agent');packages=root.get('agent_packages')
    ref=binding.get('package_ref') if isinstance(binding,dict) else None
    if not isinstance(ref,str) or not isinstance(packages,dict) or len(packages)!=1 or ref not in packages:
        raise ValueError('模型比较只识别一个明确引用的Agent包，不推测多包继承。')
    return packages[ref]['soul']['model']


def summary(cfg):
    return {'provider':cfg['dify_model_provider'],'name':cfg['dify_model'],'temperature':cfg['temperature'],'maxTokens':cfg['max_tokens']}


def compare(root,proposal):
    try:
        current_model=model(root);selected_model=model(proposal)
        if digest(model_identity(current_model))==digest(model_identity(selected_model)):return None
        current=configuration(current_model);selected=configuration(selected_model)
        before={'temperature':current['temperature'],'max_tokens':current['max_tokens'],**current['model_parameters']}
        after={'temperature':selected['temperature'],'max_tokens':selected['max_tokens'],**selected['model_parameters']}
        differences=[]
        for name in sorted(set(before)|set(after)):
            old={'present':name in before};new={'present':name in after}
            if name in before:old['value']=before[name]
            if name in after:new['value']=after[name]
            if digest(old)!=digest(new):differences.append({'name':name,'current':old,'selected':new})
        return {'available':True,'verification':'local_model_comparison_only','current':summary(current),'selected':summary(selected),
            'current_configuration':current,'selected_configuration':selected,'parameter_differences':differences,
            'note':'这里只整理当前预览文件中的模型与本次已选配置，没有核对目标环境可用性、凭据、单价或实际运行，不自动采用配置；其他合并阻止项仍需处理。'}
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        return {'available':False,'verification':'local_model_comparison_only',
            'reason':str(exc) if isinstance(exc,ValueError) else '原生模型结构不完整，无法完整比较；原始文件仍保留。'}
