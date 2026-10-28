"""Explicit source-bound local content reviews; never a platform or cost authorization."""
import hashlib,json,time
from pathlib import Path

def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def public_task(task):
 keys=('id','revision','name','app_type','environment_id','requirements','configuration','messages','intake_review','workflow_plan','planning_runs','test_cases','requirements_confirmed','configuration_confirmed','plan_stale','runs','artifact','dify_app_id','plan_source')
 return {k:task.get(k) for k in keys}
class Reviews:
 def __init__(self,root,h,record,live,save):self.root=Path(root);self.h=h;self.record=record;self.live=live;self.save=save;self.current=None
 def prepare(self,name):
  if name not in ('reviewed_requirements','first_plan','changed_requirements_manual','changed_plan'):raise ValueError('Unknown content review stage')
  if self.current is not None:raise ValueError('Previous content review is still pending')
  if name in self.record.get('reviews',{}):raise ValueError('Review already consumed')
  task=self.h.get_task(self.record['task_id']);value={'stage':name,'task':public_task(task),'verification':'agent_declared_requires_root_review_not_model_or_human' if name=='changed_requirements_manual' else 'saved_model_candidate_requires_root_review_no_new_call_or_human' if name=='reviewed_requirements' else 'model_content_requires_root_review_not_business_acceptance'}
  from app.plan_drafts import inspect_text
  inspect_text(json.dumps(value,ensure_ascii=False));source=digest(value);path=self.root/('review-source-'+name+'.json');path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
  self.current={'stage':name,'task_id':task['id'],'revision':task['revision'],'source_sha256':source};self.record['waiting_review']=self.current;self.save()
  if not self.live:
   approval={'stage':name,'task_id':task['id'],'revision':task['revision'],'source_sha256':source,'decision':'proceed','actor':'synthetic_structural_checker','note':'Synthetic structural fixture only; no semantic review or human approval claimed.'}
   (self.root/('review-'+name+'.json')).write_text(json.dumps(approval),'utf-8')
  return self.current
 def poll(self,name):
  if self.current is None or self.current['stage']!=name:raise ValueError('Review source changed')
  path=self.root/('review-'+name+'.json')
  if not path.exists():return {'ready':False,**self.current}
  from app.publication_dispatch_receipt import strict_json
  value=strict_json(path.read_bytes());task=self.h.get_task(self.current['task_id']);captured=json.loads((self.root/('review-source-'+name+'.json')).read_text('utf-8'))
  if digest(captured)!=self.current['source_sha256'] or public_task(task)!=captured['task'] or any(value.get(k)!=self.current[k] for k in ('stage','task_id','revision','source_sha256')) or value.get('decision')!='proceed' or value.get('actor')!=('agent_delegated' if self.live else 'synthetic_structural_checker') or not isinstance(value.get('note'),str) or not value['note'].strip():raise ValueError('Explicit current-source review missing or rejected')
  from app.plan_drafts import inspect_text
  inspect_text(value['note'])
  if name in ('first_plan','changed_plan'):
   candidate=task['workflow_plan'] if name=='first_plan' else task['planning_runs'][-1].get('last_candidate')
   if not isinstance(candidate,dict):raise ValueError('Model candidate missing; no manual plan replacement')
   if name=='changed_plan':
    import copy
    expected=copy.deepcopy(task['workflow_plan']);nodes=[n for n in expected['nodes'] if n['type']=='template-transform']
    if len(nodes)!=1:raise ValueError('Expected exactly one fixed no-hit template')
    nodes[0]['config']['template']=self.h.c1_fixture['changed_fallback']
    if candidate!=expected:raise ValueError('Changed model candidate exceeds the single approved no-hit text change')
   self.record.setdefault('reviewed_plan_digests',{})[name]=digest(candidate)
  if name=='changed_requirements_manual' and (task.get('intake_review',{}).get('source')!='agent_declared' or task['intake_review'].get('review_actor')!='agent_delegated'):raise ValueError('Manual review actor must be explicit agent declaration')
  self.record.setdefault('reviews',{})[name]={'source_sha256':self.current['source_sha256'],'actor':value['actor'],'note':value['note'],'semantic_reviewed':self.live,'assessment_source':'agent_declared' if name=='changed_requirements_manual' else 'saved_model_candidate' if name=='reviewed_requirements' else 'model','model_generated':name in ('first_plan','changed_plan'),'human_signoff':False};self.record.pop('waiting_review',None)
  self.save();self.current=None
  return {'ready':True,'stage':name,'task_id':task['id'],'revision':task['revision'],'semantic_reviewed':self.live}
