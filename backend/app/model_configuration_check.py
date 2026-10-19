"""Known directory-rule diagnostics only; no model execution, approvals or writes."""
import copy,hashlib,math,re
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from .agent_environment_mapping import MappingRoute,target_model
from .resources import models_metadata,parameter_metadata,provider_path


class CheckRoute(MappingRoute):
    field_error='模型配置核对字段无效，请提交完整模型JSON与目标连接修订；不回显输入，不调用模型。'
    def transport_error(self,exc):return str(exc).replace('试跑请求','模型配置核对请求').replace('派发','读取目录')


class CheckRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model_json:str=Field(min_length=1,max_length=30000)
    expected_connection_revision:str|None=Field(default=None,max_length=100)


def number(value):return type(value) is int or type(value) is float and math.isfinite(value)


def check_rules(model,rules):
    """No default inheritance. Missing or template-only rules remain unresolved."""
    params=model['completion_params'];errors=[];unknown=[];checked=[];by_name={}
    if not isinstance(rules,list) or len(rules)>128:raise ValueError('参数规则条数或结构无法完整核对，不截断后算通过。')
    for rule in rules:
        if not isinstance(rule,dict) or not isinstance(rule.get('name'),str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',rule['name']) or rule['name'] in by_name:raise ValueError('参数规则名称缺失、重复或不兼容，不能删规则后算通过。')
        by_name[rule['name']]=rule
    for name,rule in by_name.items():
        present=name in params;required=rule.get('required')
        if required is True and not present:errors.append(f'缺少目录声明必填的参数 {name}。')
        elif type(required) is not bool and not present:unknown.append(f'参数 {name} 的必填政策未明确，未假定可以省略。')
        if not present:continue
        value=params[name];kind=rule.get('type');checks=[]
        expected={'int':lambda:type(value) is int,'float':lambda:number(value),'string':lambda:isinstance(value,str),'boolean':lambda:type(value) is bool}
        if kind not in expected:
            unknown.append(f'参数 {name} 的类型未明确或尚未适配，未根据模板猜测。')
        elif not expected[kind]():errors.append(f'参数 {name} 与目录声明的 {kind} 类型不符。')
        else:checks.append('type')
        low=rule.get('min');high=rule.get('max')
        bad_range=any(key in rule and not number(rule[key]) for key in ('min','max')) or (number(low) and number(high) and low>high)
        if bad_range:unknown.append(f'参数 {name} 的目录范围不完整或矛盾，未使用错误范围。')
        elif any(k in rule for k in ('min','max')) and not number(value) and kind not in {'int','float'}:
            unknown.append(f'参数 {name} 的数值范围无法用于当前非数值类型，未忽略该规则。')
        elif number(value):
            if low is not None:
                if value<low:errors.append(f'参数 {name} 小于目录声明的下限。')
                else:checks.append('min')
            if high is not None:
                if value>high:errors.append(f'参数 {name} 大于目录声明的上限。')
                else:checks.append('max')
        if 'options' in rule:
            options=rule['options']
            if not isinstance(options,list) or any(not isinstance(v,(str,bool)) and not number(v) for v in options):unknown.append(f'参数 {name} 的目录选项不完整，未猜测合法值。')
            elif not options:unknown.append(f'参数 {name} 的目录选项为空，未假定没有选项约束。')
            else:
                equal=lambda candidate:(type(value) is type(candidate) or number(value) and number(candidate)) and value==candidate
                if not any(equal(v) for v in options):errors.append(f'参数 {name} 不在目录声明的选项内。')
                else:checks.append('options')
        checked.append({'name':name,'checks':checks})
    for name in params:
        if name not in by_name:unknown.append(f'目录没有给出参数 {name} 的规则，未将其当作已核对。')
    return {'status':'invalid' if errors else 'needs_review' if unknown else 'matches_known_rules',
            'matches_known_rules':not errors and not unknown,'errors':errors,'unresolved':unknown,'checked':checked,
            'note':'只核对读取时目录明确给出的类型、范围、选项和必填声明；不自动补默认值，不证明插件、权限、实际调用、业务效果或费用。缺失或模板规则不能猜补。'}


class ModelConfigurationCheck:
    def __init__(self,h):self.h=h

    def register(self):
        h=self.h;router=APIRouter(route_class=CheckRoute)
        @router.post('/api/environments/{item_id}/model-configuration-check')
        async def check(item_id:str,payload:CheckRequest):
            try:model=target_model(payload.model_json);path=provider_path(model['provider'])
            except (ValueError,OverflowError) as exc:raise HTTPException(422,str(exc)) from None
            with h.store.lock:
                env=copy.deepcopy(h.resource_environment(item_id))
                if env.get('connection_revision')!=payload.expected_connection_revision:raise HTTPException(409,'目标连接修订已变化，请刷新环境后重新核对模型配置。')
            try:
                adapter=h.DifyClient(env,h.store);models=models_metadata(await adapter.models('llm'),'llm')
                matches=[m for m in models if m['provider']==model['provider'] and m['model']==model['name']]
                if len(matches)!=1 or not matches[0]['selectable']:raise HTTPException(422,'目标目录中该型号缺失、标识重复或当前不可选，不按第一条猜测或替换型号。')
                rules=parameter_metadata(await adapter.model_parameters(path,model['name']))
                for rule in rules:
                    numbers=[rule[k] for k in ('min','max','precision','default') if k in rule]+(rule.get('options') if isinstance(rule.get('options'),list) else [])
                    if any(type(v) in (int,float) and (not number(v) or abs(v)>9007199254740991) for v in numbers):raise ValueError('目录参数数值超出浏览器精确范围，未舍入后核对；请人工核对完整规则。')
                result=check_rules(model,rules)
            except h.DifyError as exc:
                message='目标目录读取超时，未运行模型或写资源；请核对连接后主动重读。' if 'Dify 请求超时' in str(exc) else str(exc)
                raise HTTPException(502,message) from exc
            except OverflowError:raise HTTPException(502,'目标目录数值范围异常，未舍入或采用部分规则。') from None
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
            with h.store.lock:h.require_resource_connection(env)
            return {**result,'environment_id':item_id,'connection_revision':env.get('connection_revision'),
                    'model_document_token':hashlib.sha256(payload.model_json.encode('utf-8')).hexdigest(),
                    'provider':model['provider'],'model':model['name'],'observed_at':h.now(),'rules':rules,
                    'verification':'directory_model_rules_only','platform_verified':False,'business_verified':False,
                    'target_resources_verified':False,'task_modified':False,'model_calls':0}
        h.app.include_router(router)
