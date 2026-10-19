"""Value-free explanation of rejected repair changes; never executes code."""
NOTE='仅说明修复候选相对本轮参考候选的变化，不替代业务判断、确认或真实运行；不显示原代码、提示词、资源值或凭据。'

def summarize(before,after):
 result={'verification':'rejected_repair_summary','areas':[],'nodes':[],'truncated':False,'note':NOTE};areas=result['areas']
 def add(label):
  if label not in areas:areas.append(label)
 if not isinstance(before,dict) or not isinstance(after,dict):add('候选整体结构变化');return result
 def bounded(value):
  pending=[(value,0)];seen=set();count=0
  while pending:
   item,depth=pending.pop();count+=1
   if count>40000 or depth>60:return False
   if isinstance(item,(dict,list)):
    if id(item) in seen:return False
    seen.add(id(item));pending.extend((child,depth+1) for child in (item.values() if isinstance(item,dict) else item))
  return True
 if not bounded(before) or not bounded(after):result['truncated']=True;add('候选结构超出变化摘要范围，需核对完整方案');return result
 if {k:v for k,v in before.items() if k!='nodes'}!={k:v for k,v in after.items() if k!='nodes'}:add('顶层契约、连接或其他选择变化')
 count=[0]
 def visit(old,new,path='',depth=0):
  if depth>1 or not isinstance(old,list) or not isinstance(new,list):add('节点／内部列表结构变化');return
  if len(old)!=len(new):add('节点数量变化')
  ids=lambda rows:[n.get('id') if isinstance(n,dict) else None for n in rows]
  if ids(old)!=ids(new):add('节点标识或顺序变化')
  for i,(left,right) in enumerate(zip(old,new)):
   count[0]+=1
   if count[0]>1500:result['truncated']=True;return
   if left==right:continue
   if len(result['nodes'])>=100:result['truncated']=True;continue
   labels=[]
   if not isinstance(left,dict) or not isinstance(right,dict):labels.append('节点结构变化')
   else:
    if {k:v for k,v in left.items() if k!='config'}!={k:v for k,v in right.items() if k!='config'}:labels.append('节点属性、类型或名称变化')
    a,b=left.get('config'),right.get('config')
    if not isinstance(a,dict) or not isinstance(b,dict):
     if a!=b:labels.append('节点配置结构变化')
    else:
     if a.get('code')!=b.get('code'):labels.append('代码内容变化，需核对语义、调用、索引、缩进和注释')
     if {k:v for k,v in a.items() if k not in {'code','nodes'}}!={k:v for k,v in b.items() if k not in {'code','nodes'}}:labels.append('输入输出、条件、模型、资源或执行政策变化')
     if a.get('nodes')!=b.get('nodes'):visit(a.get('nodes'),b.get('nodes'),f'{path}节点 {i+1} 内部／',depth+1)
   if labels:
    if len(result['nodes'])>=100:result['truncated']=True
    else:result['nodes'].append({'position':f'{path}节点 {i+1}','areas':labels})
 visit(before.get('nodes'),after.get('nodes'))
 if not areas and not result['nodes']:add('无法完整归因的变化，需人工核对')
 return result
