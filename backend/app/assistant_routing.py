"""Explicit lightweight suggestion routing; never a silent provider fallback."""
import copy,hashlib,json
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictBool,StrictInt

SCOPE_VERSION=18
SCOPE='还包括Workflow JSON对象入口的完整JSON Schema（字段、描述、枚举、必填及约束），以及用户自行写入已保存验收样例的对象值；不发送真实运行输入／证据或自动读取客户数据。仅验收样例建议使用所选轻量服务。包括人工审核的完整表单对象文字、批准／拒绝动作ID／标题／按钮样式、等待时间与单位、WebApp方式ID／启用配置和三路连接（没有已提交人工内容或通知凭据）。包括明确的定时入口时间／频次／日期／时区与模式规则（不发送真实运行调度凭据）。包括LLM结构化输出的开关及完整JSON Schema（字段名、描述、枚举、必填、对象／数组和声明的长度／数值约束；不发送模型实际输出）。发送当前需求、生成应用的配置、输入输出与节点结构、已有样例／覆盖条目；Workflow／Agent 计划原文可含代码、提示词及模型／选库标识，已确认保留 DSL 的明确字段摘要也包含实际条件、代码、提示词、模型／选库标识及连接，知识检索的实际问题来源selector（包含单层迭代／循环的本项／状态／外部来源，不发送检索结果或知识全文），以及问题分类的类别ID／顺序／说明／标签、指令、问题来源和记忆配置，文档提取的实际文件来源引用及输出数组标记（不发送文件内容），数组处理的实际来源／筛选条件及字面值／排序／数量截取／序号提取，以及参数提取的字段名／类型／说明／必需规则／枚举、模式／指令／来源／记忆及原生成功标识检查，包括Chatflow原始标量（string/number/boolean）对话状态声明／初始值／保留政策及根赋值的目标／来源／覆盖或数值常量加减乘除规则（不发送运行中的对话状态），循环状态声明／初始值与赋值绑定、HTTP 实际超时／证书校验／节点重试设置、容器HTTP的明确重复读取用途声明（用户声明，不是平台强制只读）、HTTP认证的秘密变量名称／用途及引用声明（无值）。不发送搭建助手密钥、管理凭据或知识库全文；用户不要在需求、代码或样例中直接填写秘密。访谈、流程规划、配置／冲突／覆盖仍使用任务主模型；配置本身不调用模型或 Dify，每次建议生成须主动操作。轻量角色不证明价格或质量，同样内容不保证 tokens 更少；用量纳入同一助手累计预算，失败不自动换主模型。'


class RoutingRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    policy_revision:StrictInt
    scope_version:StrictInt
    enabled:StrictBool
    light_provider_id:str|None=None
    provider_token:str|None=None
    acknowledge_scope:StrictBool
    note:str


def stamp(h,provider):
    view={k:provider.get(k) for k in ('id','provider','base_url','model','protocol','role','pricing','configuration_revision','capabilities')}
    view['has_key']=h.store.has_secret(provider['id'],'api_key')
    return hashlib.sha256(json.dumps(view,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class RoutingManager:
    def __init__(self,h):self.h=h

    def get(self,item_id):
        return self.h.store.get('assistant_routing',item_id) or {'id':item_id,'policy_revision':0,'scope_version':SCOPE_VERSION,'enabled':False,'light_provider_id':None,'provider_token':None,'history':[]}

    def state(self,task):
        h=self.h;policy=self.get(task['id']);eligible=[]
        for provider in h.store.list('provider'):
            if provider.get('role')=='light':eligible.append({**h.provider_public(provider),'provider_token':stamp(h,provider)})
        selected=h.store.get('provider',policy['light_provider_id']) if policy.get('light_provider_id') else None
        blocker=None
        if policy['enabled']:
            if policy.get('scope_version',1)!=SCOPE_VERSION:blocker='验收建议的数据范围已升级，新增Workflow JSON对象入口完整Schema与用户保存样例对象，或人工审核对象／动作／等待／送达声明，或定时入口的时间／频次／日期／时区／模式规则，或Chatflow根状态数值常量加减乘除规则，或标量状态的数值／布尔类型及初始值，或对话状态声明及根赋值规则，或扩大最终保留 DSL 的条件、代码、提示词、循环状态声明／初始值及赋值绑定、HTTP明确重复读取用途声明（不是平台强制只读）、证书校验／重试设置及认证秘密变量名称／用途／引用声明、文档文件来源引用、数组筛选／排序／截取及问题分类和参数提取的字段／规则／状态检查／模式／指令／来源／记忆范围，请重新核对并确认范围；未确认前不派发，也不回退主模型。'
            elif not selected or selected.get('role')!='light' or not h.store.has_secret(selected['id'],'api_key'):blocker='所选轻量服务缺失、角色改变或无密钥；不会换到主模型，请明确修改路由。'
            elif policy['provider_token']!=stamp(h,selected):blocker='所选服务的型号、地址、凭据、用途、单价或能力记录已变化，请重新核对并确认路由。'
        return {**copy.deepcopy(policy),'task_revision':task['revision'],'eligible':eligible,'selected_provider':h.provider_public(selected) if selected else None,
                'blocker':blocker,'scope_note':SCOPE,'required_scope_version':SCOPE_VERSION,'supported_operations':['cases'],'verification':'user_selected_route_not_quality_verified'}

    def provider(self,task,kind):
        if kind!='cases' or not self.get(task['id'])['enabled']:return self.h.main_provider(task)
        state=self.state(task)
        if state['blocker']:raise HTTPException(422,state['blocker'])
        return self.h.store.get('provider',state['light_provider_id'])

    def preview(self,task):
        state=self.state(task)
        try:
            provider=self.provider(task,'cases')
            selected={k:provider.get(k) for k in ('id','name','provider','model','pricing')}
            error=None
        except HTTPException as exc:
            selected=None;error=str(exc.detail)
        return {'policy_revision':state['policy_revision'],'role':'light' if state['enabled'] else 'main','provider':selected,'blocker':error,'scope_note':SCOPE}

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/assistant-routing')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @h.app.patch('/api/tasks/{item_id}/assistant-routing')
        def save(item_id:str,payload:RoutingRequest):
            if payload.scope_version!=SCOPE_VERSION:raise HTTPException(409,'路由数据范围版本已变化，请刷新并核对新的范围。')
            if not payload.acknowledge_scope or not payload.note.strip() or len(payload.note)>2000:raise HTTPException(422,'请明确确认数据范围／用途／费用及无自动换模型政策，并说明变更原因。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);policy=self.get(item_id)
                if policy['policy_revision']!=payload.policy_revision:raise HTTPException(409,'路由设置已变化，请重新读取。')
                if payload.enabled:
                    provider=h.store.get('provider',payload.light_provider_id) if payload.light_provider_id else None
                    if not provider or provider.get('role')!='light' or not h.store.has_secret(provider['id'],'api_key'):raise HTTPException(422,'请选择有密钥、用途为轻量的现有服务；不会复制或转移主模型密钥。')
                    token=stamp(h,provider)
                    if payload.provider_token!=token:raise HTTPException(409,'所选服务设置已变化，请刷新后确认当前型号、地址及价格。')
                elif payload.light_provider_id is not None or payload.provider_token is not None:raise HTTPException(422,'关闭路由须明确清除轻量选择，不保留未生效指向。')
                before={key:policy.get(key) for key in ('enabled','light_provider_id','provider_token','scope_version')}
                after={'enabled':payload.enabled,'light_provider_id':payload.light_provider_id,'provider_token':payload.provider_token,'scope_version':payload.scope_version}
                policy['history'].append({'before':before,'after':after,'note':payload.note.strip(),'created_at':h.now(),'task_revision':task['revision'],'source':'user_confirmed'})
                policy.update(after);policy['policy_revision']+=1;h.store.put('assistant_routing',item_id,policy)
                return self.state(task)
