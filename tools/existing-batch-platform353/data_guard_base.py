"""Protect every existing object/ciphertext and admit only the owned new task and connection receipts."""
import copy,hashlib,json
from pathlib import Path
from boundary import require,canonical,digest

def capture(store):
 with store.connect() as db:
  objects={k+':'+i:digest(json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')}
  secrets={i:hashlib.sha256(bytes(v)).hexdigest() for i,v in db.execute('SELECT id,value FROM secrets')}
 files={}
 for p in store.root.rglob('*'):
  if not p.is_file() or p.parent==store.root and p.name in ('flowcraft.sqlite3','flowcraft.sqlite3-wal','flowcraft.sqlite3-shm','server.out.log','server.err.log'):continue
  require(p.resolve().is_relative_to(store.root.resolve()),'Protected data file outside workspace')
  h=hashlib.sha256()
  with p.open('rb') as stream:
   for chunk in iter(lambda:stream.read(262144),b''):h.update(chunk)
  files[str(p.relative_to(store.root))]=h.hexdigest()
 return {'objects':objects,'secrets':secrets,'files':files}

def guarded_store(base,old,environment_id,boundary,source_environment,task_name):
 class Guarded(base):
  batch_boundary=boundary
  owner=None;enabled=True;env_service_writes=0;key_proposals=set();reconnects=set();publications=set();previous_key_digest=None
  def object_check(self,kind,item,value):
   if not self.enabled:return
   ident=kind+':'+item
   if kind=='environment':
    require(item==environment_id,'Other environment write refused')
    mutable={'console_checked_at','console_auth_mode','console_login_blocked','console_failure_id','connection_revision','service_app_id','capabilities'}
    require(canonical({k:v for k,v in value.items() if k not in mutable})==canonical({k:v for k,v in source_environment.items() if k not in mutable}),'Source connection identity/login binding changed')
    old_caps=source_environment.get('capabilities',{});caps=value.get('capabilities',{})
    require(isinstance(old_caps,dict) and isinstance(caps,dict) and {k:v for k,v in caps.items() if k not in ('console','runtime')}=={k:v for k,v in old_caps.items() if k not in ('console','runtime')},'Unapproved environment capability change')
    require(value.get('service_app_id') in {source_environment.get('service_app_id'),boundary.app},'Unexpected connection App binding');return
   require(ident not in old['objects'],'Protected original object write refused')
   if kind=='task':
    if self.owner is None:
     require(value.get('app_type')=='workflow' and value.get('environment_id')==environment_id and value.get('name')==task_name,'Unexpected new task identity');self.owner=item
    require(item==self.owner and value.get('intake_required') is True and value.get('plan_review_required') is True,'Other task or gate bypass refused')
    require(all(sum(r.get('kind')==name for r in value.get('runs',[]))<=1 for name in ('run','import','publish')),'Duplicate task dispatch record refused');return
   if kind in ('saved_console_reconnect','console_saved_reconnect','console_connection_failure'):
    require(value.get('environment_id')==environment_id,'Other auth receipt refused')
    if kind!='console_connection_failure':self.reconnects.add(item);require(len(self.reconnects)<=1,'More than one explicit reconnect refused')
    return
   allowed={'task_budget','execution_limits','workflow_publication','app_runtime_key_creation','app_runtime_credential','runtime_key_previous_binding'}
   require(kind in allowed,'Unapproved object kind')
   if kind in ('task_budget','execution_limits'):
    require(item==self.owner,'Other task policy/ledger write refused')
    if kind=='task_budget':require(not value.get('entries'),'No model reservation/ledger entry allowed')
   elif kind in ('workflow_publication','app_runtime_key_creation'):
    require(value.get('task_id')==self.owner and value.get('environment_id')==environment_id and value.get('app_id')==boundary.app,'Unbound resource receipt')
    entries=self.publications if kind=='workflow_publication' else self.key_proposals;entries.add(item);require(len(entries)<=1,'More than one resource proposal refused')
   elif kind=='app_runtime_credential':require(value.get('environment_id')==environment_id and value.get('app_id')==boundary.app and item==environment_id+':app-runtime:'+str(boundary.app),'Unexpected new Key archive')
   else:require(value.get('environment_id')==environment_id and value.get('source') in self.key_proposals and value.get('app_id')==source_environment.get('service_app_id'),'Unexpected previous binding archive')
  def _put_object(self,conn,states,kind,item_id,value):self.object_check(kind,item_id,value);return super()._put_object(conn,states,kind,item_id,value)
  def secret_check(self,sets):
   if not self.enabled:return
   for owner,values in sets.items():
    for name,value in values.items():
     ident=owner+':'+name;require(isinstance(value,str) and bool(value),'Empty or invalid secret mutation refused')
     if owner==environment_id:
      require(name in ('console_token','csrf_token','service_api_key'),'Original encrypted login mutation refused')
      if name=='service_api_key':
       require(value==boundary.key and self.env_service_writes==0,'Only newly created runtime key may replace connection binding');self.env_service_writes+=1
     elif owner==environment_id+':app-runtime:'+str(boundary.app):require(name=='service_api_key' and value==boundary.key and ident not in old['secrets'],'New App archive mismatch')
     else:
      self.previous_key_digest=hashlib.sha256(value.encode()).hexdigest()
      require(owner.endswith(':previous-runtime-key') and owner.removesuffix(':previous-runtime-key') in self.key_proposals and name=='service_api_key' and ident not in old['secrets'] and value==self.secret(environment_id,'service_api_key'),'Previous encrypted key archive mismatch')
  def secret(self,item,key):
   if self.enabled:
    allowed=item==environment_id and key in ('console_login_email','console_login_password','console_token','csrf_token','service_api_key') or item==environment_id+':app-runtime:'+str(boundary.app) and key=='service_api_key' or item.endswith(':previous-runtime-key') and item.removesuffix(':previous-runtime-key') in self.key_proposals and key=='service_api_key'
    require(allowed,'Unrelated credential decryption refused')
   return super().secret(item,key)
  def set_secret(self,item,key,value):self.secret_check({item:{key:value}});return super().set_secret(item,key,value)
  def put_with_secrets(self,kind,item,value,secrets):self.secret_check({item:secrets});return super().put_with_secrets(kind,item,value,secrets)
  def put_many_with_secrets(self,records,item,secrets):self.secret_check({item:secrets});return super().put_many_with_secrets(records,item,secrets)
  def put_many_with_secret_sets(self,records,sets):self.secret_check(sets);return super().put_many_with_secret_sets(records,sets)
  def delete(self,*args):raise RuntimeError('Deletion refused')
 return Guarded

def verify(store,old,environment_id):
 now=capture(store);allowed_env='environment:'+environment_id
 require(all(now['objects'].get(k)==v for k,v in old['objects'].items() if k!=allowed_env),'Protected original object hash changed')
 allowed={environment_id+':'+k for k in ('console_token','csrf_token','service_api_key')}
 require(all(now['secrets'].get(k)==v for k,v in old['secrets'].items() if k not in allowed),'Protected original ciphertext changed')
 require(all(now['files'].get(k)==v for k,v in old['files'].items()),'Protected original file or master key changed')
 with store.connect() as db:
  added=[(kind,item,json.loads(value)) for kind,item,value in db.execute('SELECT kind,id,value FROM objects') if kind+':'+item not in old['objects']]
 for kind,item,value in added:
  if kind=='task':require(item==store.owner,'Unowned additional task found')
  store.object_check(kind,item,value)
 allowed_new_owners={environment_id,environment_id+':app-runtime:'+str(store.get('environment',environment_id).get('service_app_id'))}|{i+':previous-runtime-key' for i in store.key_proposals}
 for ident in set(now['secrets'])-set(old['secrets']):
  owner,name=ident.rsplit(':',1);require(owner in allowed_new_owners and name in ('console_token','csrf_token','service_api_key'),'Unowned new ciphertext found')
 reconnects=[store.get(kind,i) for kind,i,v in added if kind in ('saved_console_reconnect','console_saved_reconnect')]
 authenticated=bool(reconnects and reconnects[0].get('state')=='succeeded')
 if authenticated:
  require(store.secret(environment_id,'console_token')==store.batch_boundary.login_tokens['console_token'] and store.secret(environment_id,'csrf_token')==store.batch_boundary.login_tokens['csrf_token'],'Authentication tokens changed outside batch')
 else:require(all(now['secrets'].get(environment_id+':'+k)==old['secrets'].get(environment_id+':'+k) for k in ('console_token','csrf_token')),'Failed admission committed new token')
 if store.env_service_writes:
  require(store.get('environment',environment_id)['service_app_id']==store.batch_boundary.app and store.secret(environment_id,'service_api_key')==store.batch_boundary.key,'Runtime binding changed outside batch')
  require(store.secret(environment_id+':app-runtime:'+store.batch_boundary.app,'service_api_key')==store.batch_boundary.key,'New App key archive mismatch')
  for i in store.key_proposals:
   require(hashlib.sha256(store.secret(i+':previous-runtime-key','service_api_key').encode()).hexdigest()==store.previous_key_digest,'Previous key archive changed')
 else:require(now['secrets'].get(environment_id+':service_api_key')==old['secrets'].get(environment_id+':service_api_key'),'Runtime key changed before confirmed creation')

 for filename in set(now['files'])-set(old['files']):require(store.owner is not None and Path(filename).parts[0]==store.owner,'New data file outside owned task')
 return {'original_objects_kept':True,'original_ciphertexts_kept_except_explicit_tokens_and_new_runtime_binding':True,'original_files_and_master_key_kept_except_operational_server_logs':True,'new_task_only':store.owner}
