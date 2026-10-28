"""Disposable API-only prior-state shapes. Never applied to production or called live."""
import copy,json
from guard import require

def prepare_prior(api,h,tid,fixture,provider_id):
 original=h.call_model
 def send(value,text):
  async def model(*a,**kw):return json.dumps(value,ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
  h.call_model=model
  try:r=api.post('/api/tasks/'+tid+'/messages',json={'content':text})
  finally:h.call_model=original
  require(r.status_code==200,'Synthetic prior API failed')
  return r.json()
 invalid={'message':'公开旧失败形状','requirements_patch':{'knowledge':'拟议知识库检索'},'intake_review':{'schema_version':1,'checks':[],'questions':[]}}
 t=send(invalid,'公开合成旧失败输入，不代表真实调用。')
 require(t['revision']==3 and len(t['interview_attempts'])==1,'Synthetic initial r3 missing')
 cfg=copy.deepcopy(fixture['configuration']);cfg['assistant_provider_id']=provider_id;cfg['resource_plan']='PUBLIC_PRIOR_SCOPE'
 t=api.patch('/api/tasks/'+tid,json={'expected_revision':t['revision'],'configuration':cfg}).json();require(t['revision']==4,'Synthetic prior config r4 missing')
 from app.intake import topics
 req={k:'尚未明确'+k for k in fixture['requirements']};req['knowledge']='拟议知识库检索，资源尚待明确。'
 checks=[{'topic':r['id'],'status':'needs_input','detail':'合成先前未决草案。','evidence':[]} for r in topics({**t,'requirements':req})]
 question={'topic':'goal','question':'请明确目标。','recommendation':'明确再继续。','reason':'避免提前搭建。','experience':'按主题回答。','cost':'只是合成状态。','manual_work':'需明确说明。'}
 t=send({'message':'合成初访谈形状，尚未确认。','requirements_patch':req,'intake_review':{'schema_version':1,'checks':checks,'questions':[question]}},'合成公开售后需求，请先追问，不搭建。')
 require(t['revision']==5 and t.get('intake_review',{}).get('source')=='model','Synthetic unresolved interview r5 missing')
 t=send(invalid,'公开完整答复的旧失败形状，保留但不应用。')
 require(t['revision']==5 and len(t['interview_attempts'])==2 and len(h.store.get('task_budget',tid)['entries'])==3,'Synthetic retained history incomplete')


def prepare_history(api,h,tid,fixture,provider_id):
 prepare_prior(api,h,tid,fixture,provider_id)
 t=h.get_task(tid);config=copy.deepcopy(fixture['configuration']);config['assistant_provider_id']=provider_id
 t=api.patch('/api/tasks/'+tid,json={'expected_revision':t['revision'],'configuration':config}).json();require(t['revision']==6,'Synthetic prior r6 missing')
 req=copy.deepcopy(fixture['requirements'])
 from app.intake import topics,ReviewContractError
 checks=[{'topic':r['id'],'status':'complete','detail':'合成公开完整说明。','evidence':[{'kind':'message','id':str(len(t['messages'])),'quote':req.get(r['id'],req['knowledge'])}]} for r in topics({**t,'requirements':req})]
 original_model,original_validate=h.call_model,h.validate_intake
 async def model(*a,**kw):return json.dumps({'message':'完整合成候选，待复核不搭建。','requirements_patch':req,'intake_review':{'schema_version':1,'checks':checks,'questions':[]}},ensure_ascii=False),{'prompt_tokens':100,'completion_tokens':100}
 def old_validation(*a,**kw):raise ReviewContractError('合成旧版本误加batch；候选未应用。')
 h.call_model=model;h.validate_intake=old_validation
 try:r=api.post('/api/tasks/'+tid+'/messages',json={'content':'明确公开需求：\n'+'\n'.join(req.values())})
 finally:h.call_model=original_model;h.validate_intake=original_validate
 require(r.status_code==200 and r.json()['revision']==6 and len(r.json()['interview_attempts'])==3,'Synthetic saved complete rejection missing')
 r=api.post('/api/tasks/'+tid+'/saved-intake-candidates/2/preview',json={'revision':6});require(r.status_code==200,'Synthetic normal recovery preview failed');preview=r.json()
 r=api.post('/api/tasks/'+tid+'/saved-intake-candidates/2/adopt',json={'revision':6,'review_token':preview['review_token'],'acknowledge_unconfirmed':True})
 require(r.status_code==200 and r.json()['revision']==7 and r.json()['intake_review']['source']=='saved_model_candidate' and len(h.store.get('task_budget',tid)['entries'])==4,'Synthetic API-only recovery shape missing')
