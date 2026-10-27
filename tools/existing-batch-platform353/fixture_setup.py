"""Normal Sierra endpoints only. Caller must gate production use before constructing this runner."""
import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REQUIREMENTS={
 'goal':'逐项处理公开文字并返回每项结果及成功失败汇总，仅验证固定公开计算合同。',
 'audience':'开发者使用公开合成文字核对处理行为，不接真实客户资料。',
 'input':'items_json为必填JSON字符串数组文字，例子为[" a ","ERR","a",""]；原顺序、重复项和空文字均保留。空白参数或错误格式必须拒绝。',
 'output':'返回results原完整逐项对象数组，以及successes、failures、total、succeeded、failed；索引为原0基，失败value为null，成功error_category为null。只返回给本次发起者。',
 'rules':'item完全等于ERR触发ValueError；其余文字去两端空白后大写。六类受控异常ValueError、TypeError、ZeroDivisionError、KeyError、IndexError、OverflowError作为失败记录继续，其他错误停止整批；不补值、不自动重试。',
 'knowledge':'采用公开自造文字，不依赖额外资料或其他业务服务。',
 'exceptions':'输入或输出格式不符、未知错误、沙箱及超时停止整批，不伪造成功。受控失败记录仅保留index、ok、value、error_category，不复制原异常正文。已派发工作不承诺即时取消。',
 'tests':'公开四项输入预期4项、3成功、1失败，原索引1为ValueError，其余成功值依次为A、A及空文字。总数和原失败位置必须一致。'
}
SPECIAL={
 'batch':'顺序逐项计算，保留原0基索引、顺序、重复项及空文字。六类受控异常作为失败记录继续，其余错误停止；输出完整逐项对象数组及成功失败和总数，不声称已执行或业务验收。',
 'batch_outcomes':'已逐项检查固定公开代码及封装。接受index/ok/value/error_category四字段、成功文字值与null错误类别、失败null值和六类异常名，不复制异常正文。输入输出不符、沙箱、未知及超时仍终止；不是多步骤计算链，不使用failed_stage。results保留全量，另有successes/failures/total/succeeded/failed；固定四项应4/3/1，失败原索引1。'
}
ROWS=[{'index':i,'ok':i!=1,'value':(['A',None,'A',''][i]),'error_category':'ValueError' if i==1 else None} for i in range(4)]
RESOURCE_PLAN='仅本批独立具体范围获批准后，新建独立Workflow App一个，首次发布一次，新建专用运行Key一个，最多一次公开数据运行。切换专用连接运行配对时旧Key加密留档，不覆盖原App，不改原任务与旧账本。Sandbox与宿主费用仍待核对，异常整批停止，不自动追加或重试。'

class LocalPipeline:
 def __init__(self,api,environment_id,record):self.api=api;self.environment_id=environment_id;self.record=record;self.task=None;self.started=False
 def call(self,method,path,body=None):
  response=self.api.request(method,path,json=body) if body is not None else self.api.request(method,path)
  self.record.setdefault('local_requests',[]).append({'method':method,'path':path,'status':response.status_code})
  if response.status_code not in (200,201):raise RuntimeError('Local batch stage rejected: '+path+' HTTP '+str(response.status_code))
  return response.json()
 def prepare(self):
  if self.started:raise RuntimeError('Local stage was already entered; no stage replay')
  self.started=True
  fixture=json.loads((ROOT/'fixture.json').read_text('utf-8'));self.task=self.call('POST','/api/tasks',{'name':fixture['task_name'],'app_type':'workflow','environment_id':self.environment_id});tid=self.task['id'];base='/api/tasks/'+tid
  if self.task.get('intake_required') is not True or self.task.get('plan_review_required') is not True:raise RuntimeError('New task gates not active')
  self.task=self.call('PATCH',base,{'expected_revision':self.task['revision'],'requirements':copy.deepcopy(REQUIREMENTS),'configuration':{'resource_plan':RESOURCE_PLAN}})
  plan_text=(ROOT/'candidate-plan.json').read_text('utf-8');self.task=self.call('POST',base+'/plan',{'revision':self.task['revision'],'plan_text':plan_text})
  self.task=self.call('POST',base+'/test-cases',{'revision':self.task['revision'],'cases':[{'id':'public-four-items','name':'公开四项受控失败','required':True,'input':fixture['input'],'expectation':{'mode':'equals','target':'results','expected':ROWS}}]})
  standard=self.call('GET',base+'/intake');answers={row['id']:REQUIREMENTS[row['id']] if row['id'] in REQUIREMENTS else SPECIAL[row['id']] for row in standard['standard']}
  self.task=self.call('POST',base+'/intake/manual',{'revision':self.task['revision'],'context_token':standard['context_token'],'answers':answers,'acknowledge_review':True,'actor':'agent_delegated','actor_note':'按用户对常规本机事项的委托，逐项复核固定公开计算、失败策略与结果合同；这是代理受托声明，不冒充人类逐项回答或实际平台签收。'})
  self.task=self.call('POST',base+'/plan',{'revision':self.task['revision'],'plan_text':plan_text})
  for kind in ('requirements','configuration'):self.task=self.call('POST',base+'/confirm',{'revision':self.task['revision'],'kind':kind})
  self.call('PATCH',base+'/execution-limits',{'revision':self.task['revision'],'policy_revision':0,'max_started_runs':1,'max_total_minutes':10,'max_reported_cost_usd':'0.01','acknowledge_scope':True,'note':'本批独立公开计算只允许运行一次；10分钟/已报告USD报价阈值0.01不是账单硬上限，不包含宿主成本。异常即停，不重试。'})
  self.task=self.call('POST',base+'/build',{'revision':self.task['revision']})
  self.record.update(task_id=tid,revision=self.task['revision'],local_prepared=True)
  return self.task
