"""Explicit source-bound local content reviews; never a platform or cost authorization."""
import hashlib,json,time
from pathlib import Path

def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def content_digest(task):
 return digest({k:task.get(k) for k in ('app_type','environment_id','requirements','configuration','workflow_plan','test_cases','materials')})

def require_reviewed_content(task,record):
 if record.get('reviewed_content_sha256')!=content_digest(task):raise ValueError('Reviewed requirements, configuration, plan or cases changed; stop before platform requests')
def public_task(task):
 keys=('id','revision','name','app_type','environment_id','requirements','configuration','messages','intake_review','workflow_plan','planning_runs','test_cases','requirements_confirmed','configuration_confirmed','plan_stale','runs','artifact','dify_app_id','plan_source')
 return {k:task.get(k) for k in keys}
class Reviews:
 def __init__(self,root,h,record,live,save):self.root=Path(root);self.h=h;self.record=record;self.live=live;self.save=save;self.current=None
 def prepare(self,name):
  if name not in ('reviewed_model_plan',):raise ValueError('Unknown content review stage')
  if self.current is not None:raise ValueError('Previous content review is still pending')
  if name in self.record.get('reviews',{}):raise ValueError('Review already consumed')
  task=self.h.get_task(self.record['task_id']);value={'stage':name,'task':public_task(task),'verification':'saved_retained_model_plan_requires_root_review_no_new_model_or_human'}
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
  if name=='reviewed_model_plan':
   candidate=task.get('workflow_plan');retained=task.get('planning_runs',[])[-1].get('last_candidate')
   if not isinstance(candidate,dict) or digest(candidate)!=digest(retained):raise ValueError('Current saved plan differs from retained model source')
   self.record.setdefault('reviewed_plan_digests',{})[name]=digest(candidate)
   self.record['reviewed_content_sha256']=content_digest(task)
  self.record.setdefault('reviews',{})[name]={'source_sha256':self.current['source_sha256'],'actor':value['actor'],'note':value['note'],'semantic_reviewed':self.live,'requirement_review_source':task.get('intake_review',{}).get('source'),'assessment_source':'retained_model_candidate','model_generated':False,'human_signoff':False};self.record.pop('waiting_review',None)
  self.save();self.current=None
  return {'ready':True,'stage':name,'task_id':task['id'],'revision':task['revision'],'semantic_reviewed':self.live}
