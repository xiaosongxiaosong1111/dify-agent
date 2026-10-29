"""Describe saved mock bindings from built native DSL; no execution or requests."""
import json
import re

REFERENCE=re.compile(r'\{\{#([\w-]+(?:\.[\w-]+)+)#\}\}')

def label(value):return json.dumps(value,ensure_ascii=False)

def references(value,path=''):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in {'code','description','title'}:continue
            field=path+'.'+key if path else key
            if (key.endswith('selector') or key in {'query','value'}) and isinstance(item,list) and len(item)>=2 and all(isinstance(x,str) for x in item):yield field,item
            else:yield from references(item,field)
    elif isinstance(value,list):
        for index,item in enumerate(value):yield from references(item,path+'['+str(index)+']')
    elif isinstance(value,str):
        for match in REFERENCE.finditer(value):yield path,match.group(1).split('.')

def render(task,native):
    config=task.get('configuration') or {};dependencies=config.get('mock_dependencies') or []
    if not dependencies:return None
    nodes={n['id']:n['data'] for n in native.get('workflow',{}).get('graph',{}).get('nodes',[]) if isinstance(n,dict) and isinstance(n.get('data'),dict)}
    bindings=config.get('mock_dependency_bindings') or []
    lines=['# 模拟依赖接口替换指南 · r'+str(task['revision']),'',
        '本指南只整理同修订已构建DSL的结构和已声明模拟绑定；接口接入未验证，不自动连接、改图或创建资源。未提供的接口资料保持待补，不编造可调用地址或认证。模拟标记和旧试跑结果保持。','']
    for dependency in dependencies:
        lines+=['## 依赖 '+label(dependency),''];rows=[r for r in bindings if r.get('dependency')==dependency]
        if not rows:lines+=['待补：未定位到明确绑定节点，不自动从标题、代码或样例猜测位置。','']
        for row in rows:
            node_id=row.get('node_id');node=nodes.get(node_id)
            lines+=['绑定节点：'+label(node_id)+'；原接入待办：'+label(row.get('replacement_todo') or '待补明确接入安排。')+'。','']
            if node is None:lines+=['待补：在已构建DSL的根节点中未定位该绑定；容器内或其它类型须先明确适配，不自动替换。',''];continue
            lines+=['### 当前节点契约','','节点类型：'+label(node.get('type'))+'。输入引用与输出声明来自已构建DSL，不代表真实接口字段。','']
            inputs=list(references({k:v for k,v in node.items() if k!='outputs'}))
            for field,selector in inputs:lines.append('- 输入字段 '+label(field)+' ← '+label('.'.join(selector)))
            for variable in node.get('variables',[]):
                if isinstance(variable,dict) and variable.get('variable'):lines.append('- 参数名：'+label(variable['variable']))
            if not inputs:lines.append('- 输入来源未声明为可定位selector；待补，不推断接口请求。')
            outputs=node.get('outputs') or {}
            for name,schema in outputs.items():lines.append('- 输出 '+label(name)+'：'+label(schema.get('type') if isinstance(schema,dict) else '类型未声明'))
            if not outputs:lines.append('- 输出类型未声明；须按目标节点实际契约核对，不猜测标准字段。')
            downstream=[]
            for other_id,other in nodes.items():
                if other_id==node_id:continue
                for field,selector in references(other):
                    if selector[0]==node_id:downstream.append('- '+label(other_id+'.'+field)+' 使用 '+label('.'.join(selector)))
            lines+=['','### 下游引用','',*(downstream or ['未定位直接变量引用；仍须核对图上的后续分支，不据此删除节点。']),'']
    lines+=['## 接入资料（待补并确认）','',
        '- 正式接口地址、方法、允许访问范围和环境；不从模拟代码或订单表推断。',
        '- 认证方式、权限和秘密变量名称；秘密值在目标环境配置，不写入DSL、指南或样例。',
        '- 输入字段/类型与必填规则、输出字段/类型及与上述下游引用的映射。',
        '- 成功、未找到、缺号、鉴权失败、限流、超时和其它错误的处理；超时、重试、费用与次数范围须明确。','',
        '## 替换及重新验证','',
        '1. 保留当前修订和旧失败记录，在明确的新方案中逐项确认上述接入资料；本指南不授予真实请求权限。',
        '2. 对照绑定节点输入/输出和下游引用，提出替换节点及映射；分支、状态和引用不明时先补齐，不直接粘贴模拟表当真实接口。',
        '3. 保存变更并重新确认需求/配置，按当前版本检查变量、类型和分支后构建；不覆盖旧通过结论。',
        '4. 在允许的资源与费用范围内验证存在/不存在、缺号及追问补号、鉴权失败、超时等结果和实际节点轨迹；未批准不执行。',
        '5. 仅实际完成接入并明确确认后更新模拟标记、接入待办和交付文件。此处不改变任何验证结论。','']
    return '\n'.join(lines)
