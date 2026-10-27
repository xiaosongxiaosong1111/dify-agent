"""Only append one publication and one run to the existing Task; preserve all old history."""
import copy,json
from boundary import require,canonical
from data_guard_base import capture,guarded_store as original_guard,verify as original_verify

def guarded_store(base,old,environment_id,boundary,source_environment,source_task,evidence):
 filtered=copy.deepcopy(old);filtered['objects'].pop('task:'+source_task['id'])
 Parent=original_guard(base,filtered,environment_id,boundary,source_environment,source_task['name'])
 class Guarded(Parent):
  owner=source_task['id'];recoveries=set()
  def object_check(self,kind,item,value):
   if kind=='task':
    require(item==self.owner,'No additional Task allowed')
    mutable={'runs','status','updated_at','state_sequence'}
    require(canonical({k:v for k,v in value.items() if k not in mutable})==canonical({k:v for k,v in source_task.items() if k not in mutable}),'Original Task source/config/messages changed')
    original=source_task['runs'];runs=value.get('runs',[]);require(runs[:len(original)]==original,'Original run history changed')
    added=runs[len(original):];require(len(added)<=2 and all(r.get('kind') in ('publish','run') and r.get('revision')==source_task['revision'] and r.get('environment_id')==environment_id and r.get('app_id')==boundary.app for r in added),'Unexpected added Task record')
    require(all(sum(r.get('kind')==k for r in added)<=1 for k in ('publish','run')),'Duplicate publication/run attempt')
    return
   if kind=='publication_recovery':
    from app.publication_recovery import verified
    from types import SimpleNamespace
    verified(SimpleNamespace(store=self),value)
    require(kind+':'+item not in old['objects'] and value.get('task_id')==self.owner and value.get('evidence_id')==evidence['id'] and value.get('binding')==evidence['binding'],'Wrong recovery source')
    self.recoveries.add(item);require(len(self.recoveries)==1 and value.get('state') in ('prepared','ready','reserved','consumed'),'Multiple or unexpected recovery declarations');return
   return super().object_check(kind,item,value)
 return Guarded

def verify(store,old,environment_id,source_task):
 filtered=copy.deepcopy(old);filtered['objects'].pop('task:'+source_task['id'])
 original_verify(store,filtered,environment_id)
 current=store.get('task',source_task['id']);store.object_check('task',source_task['id'],current)
 require(len(store.list('task'))==len([k for k in old['objects'] if k.startswith('task:')]),'Task count changed')
 require(capture(store)['files']==old['files'],'No new/changed task assets permitted')
 return {'original_other_tasks_kept':True,'current_task_source_and_all_old_runs_kept':True,'original_unknown_kept':True,'ciphertexts_kept_except_approved_auth_and_new_runtime_binding':True,'all_original_assets_masterkey_kept':True,'new_tasks':0,'new_apps':0}
