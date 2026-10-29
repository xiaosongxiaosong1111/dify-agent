"""Allow only the new Task and its declared connection/resource receipts."""
import copy
import hashlib
from common import capture,digest,require,uuid


def guarded(base,env,fixture,contract,boundary,old):
    expected_config=contract['configuration']
    allowed_requirements=[fixture['requirements'],{**fixture['requirements'],'output':fixture['requirements']['output'].replace(fixture['inputs']['no_hit_reply'],fixture['changed_no_hit_reply'])}]
    class Guarded(base):
        key_proposals=set();publications=set();service_writes=0
        def _put_object(self,conn,states,kind,item,value):
            if kind=='environment':
                require(item==env['id'],'Other connection write')
                mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','connection_revision','service_app_id','capabilities'}
                require({k:v for k,v in value.items() if k not in mutable}=={k:v for k,v in env.items() if k not in mutable},'Connection source changed')
                require(value.get('service_app_id') in {env.get('service_app_id'),*boundary.apps},'Wrong service App')
                require({k:v for k,v in value.get('capabilities',{}).items() if k not in {'console','runtime'}}=={k:v for k,v in env.get('capabilities',{}).items() if k not in {'console','runtime'}},'Other capability changed')
            else:
                require(kind+':'+item not in old['objects'],'Existing object write forbidden')
                if kind=='task':
                    if boundary.owner is None:
                        require(uuid(item) and value.get('name')==fixture['task_name'] and value.get('app_type')=='advanced-chat','Wrong new Task');boundary.owner=item
                    require(item==boundary.owner and value.get('app_type')=='advanced-chat' and value.get('environment_id')==env['id'] and not value.get('materials') and not value.get('planning_runs') and not value.get('interview_attempts'),'Wrong Task/type/material/model history')
                    req=value.get('requirements');bootstrap=all(v=='' for v in req.values())
                    require(bootstrap or req in allowed_requirements,'Unapproved business change')
                    require(value.get('configuration')==expected_config or bootstrap and not value.get('workflow_plan'),'Unapproved configuration')
                    plan=value.get('workflow_plan');require(plan is None or digest(plan) in {digest(contract[v]['plan']) for v in ('original','modified')},'Unexpected plan edit')
                    require(value.get('dify_app_id') in {None,*boundary.apps},'Wrong Task App')
                    require(all(sum(r.get('kind')==k for r in value.get('runs',[]))<=n for k,n in [('import',2),('publish',2),('run',12)]),'Task record cap')
                elif kind in {'execution_limits','task_budget'}:
                    require(item==boundary.owner,'Other Task control')
                    if kind=='task_budget':require(not value.get('entries'),'Sierra model usage forbidden')
                    else:require(value.get('max_started_runs')==12 and value.get('max_total_minutes')==45 and value.get('max_reported_cost_usd') is None,'Execution policy changed')
                elif kind in {'saved_console_reconnect','console_saved_reconnect','console_connection_failure'}:require(value.get('environment_id')==env['id'],'Other authentication receipt')
                elif kind in {'workflow_publication','app_runtime_key_creation'}:
                    require(value.get('task_id')==boundary.owner and value.get('environment_id')==env['id'] and value.get('app_id') in boundary.apps,'Unbound resource receipt')
                    records=self.publications if kind=='workflow_publication' else self.key_proposals;records.add(item);require(len(records)<=2,'Too many proposals')
                elif kind=='app_runtime_credential':require(value.get('environment_id')==env['id'] and value.get('app_id') in boundary.apps,'Wrong key archive')
                elif kind=='runtime_key_previous_binding':require(value.get('environment_id')==env['id'] and value.get('source') in self.key_proposals and value.get('app_id') in {env.get('service_app_id'),*boundary.apps},'Wrong previous key binding')
                else:require(False,'Unapproved object kind')
            return super()._put_object(conn,states,kind,item,value)

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
                        else:require(boundary.workspace_verified and boundary.login_tokens and value==boundary.login_tokens[key],'Workspace proof required before tokens saved')
                    elif owner in {env['id']+':app-runtime:'+a for a in boundary.apps}:
                        require(key=='service_api_key' and value==boundary.apps[owner.rsplit(':',1)[1]]['key'] and owner+':'+key not in old['secrets'],'Wrong new App archive')
                    else:require(owner.endswith(':previous-runtime-key') and owner.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key' and value==self.secret(env['id'],'service_api_key'),'Wrong previous Key archive')
        def set_secret(self,item,key,value):self.check_secrets({item:{key:value}});return super().set_secret(item,key,value)
        def put_with_secrets(self,kind,item,value,secrets):self.check_secrets({item:secrets});return super().put_with_secrets(kind,item,value,secrets)
        def put_many_with_secrets(self,rows,item,secrets):self.check_secrets({item:secrets});return super().put_many_with_secrets(rows,item,secrets)
        def put_many_with_secret_sets(self,rows,sets):self.check_secrets(sets);return super().put_many_with_secret_sets(rows,sets)
        def delete(self,*args):raise RuntimeError('Delete forbidden')
    return Guarded


def verify(store,env,boundary,old):
    now=capture(store)
    require(all(now['objects'].get(k)==v for k,v in old['objects'].items() if k!='environment:'+env['id']),'Original objects changed')
    require(all(now['secrets'].get(k)==v for k,v in old['secrets'].items() if k not in {env['id']+':console_token',env['id']+':csrf_token',env['id']+':service_api_key'}),'Original credentials changed')
    require(all(now['files'].get(k)==v for k,v in old['files'].items()),'Original files/assets changed')
    require(all(k in old['files'] or k.startswith(str(boundary.owner)+'\\') or k.startswith(str(boundary.owner)+'/') for k in now['files']),'Unrelated new file')
    return {'original_objects_kept':True,'old_credentials_and_assets_kept':True,'dedicated_connection_only':True}
