"""Pin actual prior model evidence and its normal local draft recovery, with no new call."""
import json
from guard import digest,require

INITIAL_SOURCE='419da27d1c128e6f06112c4c2f52143397607a5e62489f812ae0b31e85ed445c'
RECOVERED_SOURCE='24ff213bdf8fd9a75327dedefe6970b8571df34b129741b07c2d8fe4dc2cd7a8'

def inherited(plan,task,project):
 old=project/'work/c1-resume360/live-output';initial=json.loads((old/'review-source-vague_interview.json').read_text('utf-8'));ack=json.loads((old/'review-vague_interview.json').read_text('utf-8'))
 require(digest(initial)==INITIAL_SOURCE and ack.get('source_sha256')==INITIAL_SOURCE and ack.get('decision')=='proceed' and ack.get('actor')=='agent_delegated' and ack.get('task_id')==plan['target_task_id'],'Original real initial review changed')
 root=project/'work/saved-intake364';preview=json.loads((root/'source.json').read_text('utf-8'));review=json.loads((root/'root-review.json').read_text('utf-8'))
 require(digest(preview)==RECOVERED_SOURCE and review.get('source_sha256')==RECOVERED_SOURCE and review.get('actor')=='agent_delegated' and review.get('decision')=='recover_unconfirmed_draft_only','Recovered source/root decision changed')
 require(task['id']==preview['task_id']==plan['target_task_id'] and preview['revision']==6 and preview['attempt_index']==2 and task['revision']==7,'Recovered draft identity changed')
 current=task.get('intake_review') or {}
 require(task['requirements']==preview['requirements'] and current.get('review')==preview['review'] and current.get('source')=='saved_model_candidate' and current.get('origin_revision')==7,'Recovered requirements or source changed')
 require(current.get('saved_candidate')=={'attempt_index':2,'source_revision':6,'candidate_sha256':preview['candidate_sha256']},'Recovered original candidate binding changed')
 return {'from_batch':'c1-remaining362','initial_source_sha256':INITIAL_SOURCE,'recovered_source_sha256':RECOVERED_SOURCE,'actor':'agent_delegated','new_model_call':False,'new_review':False,'human_signoff':False,'prior_real_first_review_and_saved_candidate_recovery':True}
