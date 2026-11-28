"""Existing-Task write guard for the reviewed two-version batch."""
import copy,hashlib
from datetime import datetime
from tool import capture,digest,require,uuid

MISSING=object()
TASK_PREFIX_LISTS=('confirmations','messages','versions','intake_history','runs')
TASK_FROZEN_MODEL_FIELDS=('planning_runs','interview_runs','interview_attempts','active_interview_id','active_image_operation_id')
TASK_MUTABLE={'revision','status','updated_at','requirements','requirements_confirmed','configuration_confirmed',
              'test_cases','workflow_plan','plan_source','plan_stale','artifact','dify_app_id','intake_review',
              'state_sequence',*TASK_PREFIX_LISTS}
LIMIT_KEYS=('max_started_runs','max_total_minutes','max_reported_cost_usd')

def _strict_int(value):return type(value) is int
def _timestamp(value,label):
    require(isinstance(value,str) and value.strip(),label+' missing')
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise RuntimeError(label+' invalid') from None
    require(parsed.tzinfo is not None,label+' timezone missing');return parsed

def _plan_hashes(contract):
    return {digest(contract[v]['plan']) for v in ('original','modified')}

def guarded(base,env,contract,boundary,old,initial_task,initial_budget):
    plans=_plan_hashes(contract);allowed_req=[contract[v].get('requirements') for v in ('original','modified') if contract[v].get('requirements') is not None]
    allowed_cases=[contract[v].get('cases') for v in ('original','modified') if contract[v].get('cases') is not None]
    initial_limits=None
    class Guarded(base):
        key_proposals=set();publications=set();service_writes=0;limits_written=0
        def _put_object(self,conn,states,kind,item,value):
            require(isinstance(value,dict),'Object must be mapping')
            if kind=='environment':
                require(item==env['id'],'Other connection write')
                mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','connection_revision','service_app_id','capabilities'}
                require({k:v for k,v in value.items() if k not in mutable}=={k:v for k,v in env.items() if k not in mutable},'Connection source changed')
                require(value.get('service_app_id') in {env.get('service_app_id'),*boundary.apps},'Wrong service App')
                require({k:v for k,v in value.get('capabilities',{}).items() if k not in {'console','runtime'}}=={k:v for k,v in env.get('capabilities',{}).items() if k not in {'console','runtime'}},'Other capability changed')
            elif kind+':'+item in old['objects']:
                require(item==boundary.owner and kind in {'task','task_budget','execution_limits'},'Existing object write forbidden')
                if kind=='task':self._task(item,value)
                elif kind=='task_budget':self._budget(item,value)
                else:self._limits(item,value)
            elif kind=='task':require(False,'New Task forbidden')
            elif kind=='task_budget':require(False,'New budget forbidden')
            elif kind=='execution_limits':self._limits(item,value)
            elif kind in {'saved_console_reconnect','console_saved_reconnect','console_connection_failure'}:
                require(value.get('environment_id')==env['id'],'Other authentication receipt')
            elif kind in {'workflow_publication','app_runtime_key_creation'}:
                require(value.get('task_id')==boundary.owner and value.get('environment_id')==env['id'] and value.get('app_id') in boundary.apps,'Unbound resource receipt')
                records=self.publications if kind=='workflow_publication' else self.key_proposals;records.add(item);require(len(records)<=2,'Too many proposals')
            elif kind=='app_runtime_credential':require(value.get('environment_id')==env['id'] and value.get('app_id') in boundary.apps,'Wrong key archive')
            elif kind=='runtime_key_previous_binding':require(value.get('environment_id')==env['id'] and value.get('source') in self.key_proposals and value.get('app_id') in {env.get('service_app_id'),*boundary.apps},'Wrong previous key binding')
            else:require(False,'Unapproved object kind')
            return super()._put_object(conn,states,kind,item,value)
        def _task(self,item,value):
            require(item==boundary.owner and value.get('id')==item,'Wrong Task id')
            require(value.get('app_type')=='advanced-chat' and value.get('environment_id')==env['id'],'Wrong Task/type/environment')
            require(_strict_int(value.get('revision')) and value['revision']>=initial_task.get('revision',0),'Task revision invalid')
            for key in ('revision','status','updated_at','requirements','requirements_confirmed','configuration_confirmed','test_cases','workflow_plan','plan_source','plan_stale','artifact','dify_app_id','intake_review'):
                if key in initial_task:require(key in value,'Task field deleted '+key)
            for key in set(value)|set(initial_task):
                if key in TASK_MUTABLE:continue
                require((key in value)==(key in initial_task),'Task field presence changed '+key)
                require(digest(value.get(key))==digest(initial_task.get(key)),'Task field changed '+key)
            require(isinstance(value.get('requirements'),dict),'Requirement fields changed')
            require(set(value.get('requirements',{}))==set(initial_task['requirements']),'Requirement fields changed')
            require(digest(value.get('requirements')) in {digest(item) for item in allowed_req},'Unreviewed requirement change')
            require(digest(value.get('configuration'))==digest(initial_task.get('configuration')),'Configuration changed')
            require(digest(value.get('materials'))==digest(initial_task.get('materials')),'Materials changed')
            require(digest(value.get('test_cases')) in {digest(item) for item in allowed_cases},'Unreviewed cases change')
            plan=value.get('workflow_plan')
            try:plan_ok=isinstance(plan,dict) and digest(plan) in plans
            except (TypeError,ValueError):plan_ok=False
            require(plan_ok,'Task workflow plan must be one reviewed graph')
            require(value.get('dify_app_id') in {None,*boundary.apps},'Wrong Task App')
            require(value.get('plan_source') in {'manual',initial_task.get('plan_source')},'Unexpected plan origin')
            for key in TASK_FROZEN_MODEL_FIELDS:
                require((key in value)==(key in initial_task),'Task field presence changed '+key)
                if key in initial_task:require(digest(value.get(key))==digest(initial_task.get(key)),'Task model/interview field changed '+key)
            for key in TASK_PREFIX_LISTS:
                old=initial_task.get(key,MISSING)
                if old is MISSING:
                    require(key not in value or isinstance(value[key],list),'Malformed history '+key)
                    continue
                require(isinstance(old,list) and key in value and isinstance(value[key],list),'Malformed history '+key)
                require(digest(value[key][:len(old)])==digest(old),'History prefix changed '+key)
            require(all(sum(r.get('kind')==k for r in value.get('runs',[]))<=n for k,n in [('import',2),('publish',2),('run',12)]),'Task record cap')
        def _budget(self,item,value):
            require(item==boundary.owner and value.get('id')==item,'Other budget')
            require(digest(value)==digest(initial_budget),'Budget changed')
        def _limits(self,item,value):
            nonlocal initial_limits
            require(item==boundary.owner and value.get('id')==item,'Other execution policy')
            if initial_limits is not None:
                require(digest(value)==digest(initial_limits),'Existing policy changed');return
            require(self.limits_written==0,'Policy can only be set once')
            require(set(value)=={'id','policy_revision',*LIMIT_KEYS,'updated_at','history'},'Execution policy shape changed')
            require(_strict_int(value.get('policy_revision')) and value['policy_revision']==1,'Execution policy revision must be int 1')
            after={k:value.get(k) for k in LIMIT_KEYS}
            require(after=={'max_started_runs':12,'max_total_minutes':45,'max_reported_cost_usd':None},'Execution policy mismatch')
            history=value.get('history')
            require(isinstance(history,list) and len(history)==1 and isinstance(history[0],dict),'Policy history must have exactly one record')
            record=history[0]
            require(set(record)=={'before','after','note','created_at','source'},'Policy history shape changed')
            before=record.get('before')
            require(isinstance(before,dict) and set(before)==set(LIMIT_KEYS) and all(before[k] is None for k in LIMIT_KEYS),'Policy before limits changed')
            require(record.get('after')==after,'Policy after limits changed')
            require(record.get('source')=='user','Policy source changed')
            require(isinstance(record.get('note'),str) and record['note'].strip(),'Policy note missing')
            _timestamp(record.get('created_at'),'Policy created_at');_timestamp(value.get('updated_at'),'Policy updated_at')
            self.limits_written=1;initial_limits=copy.deepcopy(value)
        def secret(self,item,key):
            allowed=item==env['id'] and key in {'console_token','csrf_token','console_login_email','console_login_password','service_api_key','dataset_api_key'}
            allowed=allowed or item in {env['id']+':app-runtime:'+a for a in boundary.apps} and key=='service_api_key'
            allowed=allowed or item.endswith(':previous-runtime-key') and item.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key'
            require(allowed,'Other credential read forbidden');return super().secret(item,key)
        def check_secrets(self,sets):
            for owner,values in sets.items():
                for key,value in values.items():
                    require(isinstance(value,str) and value,'Empty secret write')
                    if owner==env['id']:
                        require(key in {'console_token','csrf_token','service_api_key'},'Saved login/key mutation forbidden')
                        if key=='service_api_key':require(boundary.current in boundary.apps and value==boundary.apps[boundary.current]['key'] and self.service_writes<2,'Wrong service Key');self.service_writes+=1
                        else:require(boundary.workspace_verified and boundary.login_tokens and value==boundary.login_tokens[key],'Workspace proof required')
                    elif owner in {env['id']+':app-runtime:'+a for a in boundary.apps}:
                        require(key=='service_api_key' and value==boundary.apps[owner.rsplit(':',1)[1]]['key'] and owner+':'+key not in old['secrets'],'Wrong new App archive')
                    else:require(owner.endswith(':previous-runtime-key') and owner.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key','Wrong previous Key archive')
        def set_secret(self,item,key,value):self.check_secrets({item:{key:value}});return super().set_secret(item,key,value)
        def put_with_secrets(self,kind,item,value,secrets):self.check_secrets({item:secrets});return super().put_with_secrets(kind,item,value,secrets)
        def put_many_with_secrets(self,rows,item,secrets):self.check_secrets({item:secrets});return super().put_many_with_secrets(rows,item,secrets)
        def put_many_with_secret_sets(self,rows,sets):self.check_secrets(sets);return super().put_many_with_secret_sets(rows,sets)
        def delete(self,*args):raise RuntimeError('Delete forbidden')
    return Guarded

def verify(store,env,boundary,old,initial_task,initial_budget):
    now=capture(store.root)
    old_files={k:v for k,v in old['files'].items() if k!='flowcraft.sqlite3'}
    now_files={k:v for k,v in now['files'].items() if k!='flowcraft.sqlite3'}
    require(all(now['objects'].get(k)==v for k,v in old['objects'].items() if k not in {'environment:'+env['id'],'task:'+boundary.owner,'task_budget:'+boundary.owner,'execution_limits:'+boundary.owner}),'Original objects changed')
    require(all(now['secrets'].get(k)==v for k,v in old['secrets'].items() if k not in {env['id']+':console_token',env['id']+':csrf_token',env['id']+':service_api_key'}),'Original credentials changed')
    require(all(now_files.get(k)==v for k,v in old_files.items()),'Original files/assets changed')
    require(all(k in old_files or k.startswith(str(boundary.owner)+'\\') or k.startswith(str(boundary.owner)+'/') for k in now_files),'Unrelated new file')
    task=store.get('task',boundary.owner);budget=store.get('task_budget',boundary.owner)
    require(digest(task['runs'][:len(initial_task['runs'])])==digest(initial_task['runs']) and digest(task['versions'][:len(initial_task['versions'])])==digest(initial_task['versions']),'Task history prefix changed')
    require(budget.get('id')==boundary.owner and digest(budget)==digest(initial_budget),'Budget changed')
    return {'original_objects_kept':True,'old_credentials_and_assets_kept':True,'task_prefix_kept':True,'budget_kept':True}
