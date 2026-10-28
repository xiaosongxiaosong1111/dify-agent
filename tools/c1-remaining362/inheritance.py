"""Validate retained real prior evidence, without creating a new review or model call."""
import json
from guard import digest,require

INITIAL_SOURCE='419da27d1c128e6f06112c4c2f52143397607a5e62489f812ae0b31e85ed445c'

def inherited(plan,task,project):
 root=project/'work/c1-resume360/live-output'
 source=json.loads((root/'review-source-vague_interview.json').read_text('utf-8'))
 review=json.loads((root/'review-vague_interview.json').read_text('utf-8'))
 require(source.get('stage')=='vague_interview' and digest(source)==INITIAL_SOURCE,'Retained real initial source changed')
 require(all(review.get(k)==v for k,v in {'stage':'vague_interview','task_id':plan['target_task_id'],'revision':5,'source_sha256':INITIAL_SOURCE,'decision':'proceed','actor':'agent_delegated'}.items()) and isinstance(review.get('note'),str) and bool(review['note'].strip()),'Retained root review missing')
 prior=source['task'];require(task['id']==prior['id']==plan['target_task_id'] and task['revision']==prior['revision']==5,'Retained interview identity changed')
 require(task['requirements']==prior['requirements'] and task['intake_review']==prior['intake_review'] and task['messages'][:len(prior['messages'])]==prior['messages'],'Retained interview or history changed')
 return {'from_batch':'c1-resume360','stage':'vague_interview','source_sha256':INITIAL_SOURCE,'actor':'agent_delegated','new_model_call':False,'new_review':False,'human_signoff':False,'prior_real_root_review':True}
