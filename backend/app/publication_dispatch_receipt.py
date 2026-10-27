"""Bounded, read-only consistency checks. Operator attestation, not network proof."""
import hashlib,json,re,subprocess,uuid
from pathlib import Path,PurePosixPath

def sha(raw):return hashlib.sha256(raw).hexdigest()
def reject():raise ValueError('本机证据校验失败；未登记、未联网或改变原未知发布。')
def require(value):
 if not value:reject()
def uuid_text(value):
 try:require(str(uuid.UUID(value))==value)
 except (ValueError,TypeError,AttributeError):reject()
 return value
def strict_json(raw):
 require(isinstance(raw,bytes) and len(raw)<=2_000_000)
 def pairs(items):
  out={}
  for key,value in items:
   require(key not in out);out[key]=value
  return out
 try:return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=lambda _:reject())
 except (UnicodeError,ValueError,TypeError):reject()
def safe_path(root,name):
 require(isinstance(name,str) and bool(re.fullmatch(r'[A-Za-z0-9_./-]+',name)))
 parts=PurePosixPath(name).parts
 require(parts and not name.startswith('/') and all(x not in ('.','..') for x in name.split('/')))
 path=root.joinpath(*parts)
 require(path.resolve().is_relative_to(root.resolve()))
 require(not any(x.is_symlink() or x.is_junction() for x in [root,*[root.joinpath(*parts[:i]) for i in range(1,len(parts)+1)]]))
 return path
def read(root,name):
 p=safe_path(root,name);require(p.is_file() and p.stat().st_size<=2_000_000);return p.read_bytes()
def committed_blob(project,commit,report_path):
 require(bool(re.fullmatch('[0-9a-f]{40}',commit)))
 safe_path(project,report_path);require(report_path.startswith('docs/') and report_path.endswith('.json'))
 # No shell, network, mutable working-tree report, ref shorthand or configured external diff.
 result=subprocess.run(['git','-c','safe.directory='+str(project).replace('\\','/'),'show',commit+':'+report_path],cwd=project,capture_output=True,timeout=15,check=False)
 require(result.returncode==0 and len(result.stdout)<=2_000_000);return result.stdout

def validate(project,bundle,commit,report_path):
 project=Path(project).resolve();bundle=Path(bundle)
 require(bundle.is_absolute() and bundle.resolve().is_relative_to(project/'work'))
 # Reconstruct through safe_path so junctions cannot escape the declared evidence directory.
 bundle=safe_path(project,bundle.relative_to(project).as_posix())
 raw=committed_blob(project,commit,report_path);report=strict_json(raw)
 require(isinstance(report,dict) and report.get('state')=='stopped_needs_review' and report.get('phase')=='publish')
 batch=report.get('batch_id');require(isinstance(batch,str) and re.fullmatch('[a-z0-9-]{1,100}',batch))
 files={}
 for name in ('plan','manifest','approval','attempt'):
  data=read(bundle,name+'.json');require(sha(data)==report.get(name+'_sha256'));files[name]=strict_json(data)
 plan,manifest,approval,attempt=(files[k] for k in ('plan','manifest','approval','attempt'))
 require(all(isinstance(x,dict) and x.get('batch_id')==batch for x in files.values()))
 require(manifest.get('schema_version')==1 and isinstance(manifest.get('files'),dict) and 1<=len(manifest['files'])<=100)
 for name,expected in manifest['files'].items():require(sha(read(bundle,name))==expected)
 require(manifest['files'].get('plan.json')==report['plan_sha256'])
 require(approval.get('authorization_source')=='direct_human_reply' and approval.get('decision')=='approve')
 require(isinstance(approval.get('question_ref'),str) and isinstance(approval.get('reply'),str) and bool(approval['reply'].strip()))
 require(approval['reply']==report.get('reply'))
 for key in ('plan_sha256','manifest_sha256'):
  require(approval.get(key)==report[key] and attempt.get(key)==report[key])
 require(attempt.get('state')=='stopped_needs_review' and attempt.get('phase')=='publish' and attempt.get('model_http')==0 and report.get('model_http')==0)
 task=uuid_text(report.get('task_id'));app=uuid_text(report.get('app_id'));pub=uuid_text(report.get('publication_record_id'))
 require(type(report.get('revision')) is int and report['revision']>0 and attempt.get('revision')==report['revision'])
 require(attempt.get('task_id')==task and attempt.get('new_app_id')==app and app not in plan.get('original_app_ids',[]))
 require(report.get('saved_publication_state')=='unknown' and report.get('saved_write_attempted') is True and report.get('actual_publication_http_posts')==0 and report.get('new_keys')==0 and report.get('service_runs')==0 and report.get('published_workflow_id') is None)
 counts={k:0 for k in ('reads','login','import','publish','key','run')}
 dispatches=attempt.get('dispatches');require(isinstance(dispatches,list) and 1<=len(dispatches)<=100)
 reads={'/console/api/apps','/console/api/workspaces/current/summary',f'/console/api/apps/{app}/workflows/draft',f'/console/api/apps/{app}/workflows/publish'}
 for event in dispatches:
  require(isinstance(event,dict) and event.get('response_body_read') is True and type(event.get('status')) is int and 200<=event['status']<300)
  method,path,kind=(event.get(k) for k in ('method','path','kind'))
  expected='reads' if method=='GET' and path in reads else 'login' if method=='POST' and path=='/console/api/login' else 'import' if method=='POST' and path=='/console/api/apps/imports' else None
  require(expected is not None and kind==expected);counts[kind]+=1
 for totals in (attempt.get('dispatch_counts'),report.get('counts')):
  require(isinstance(totals,dict) and set(totals)==set(counts) and all(type(n) is int for n in totals.values()))
 require(counts==attempt.get('dispatch_counts')==report.get('counts') and counts['login']==counts['import']==1 and counts['reads']>=2)
 limits=approval.get('limits') or {};require(all(type(limits.get(k)) is int and counts[k]<=limits[k] for k in counts))
 env=uuid_text(plan.get('environment_id'));graph=plan.get('graph_digest');require(isinstance(graph,str) and re.fullmatch('[0-9a-f]{64}',graph))
 return {'schema_version':1,'task_id':task,'revision':report['revision'],'app_id':app,'publication_id':pub,'environment_id':env,'graph_digest':graph,'source_commit':commit,'report_path':report_path,'report_sha256':sha(raw),'batch_id':batch,**{k:report[k] for k in ('plan_sha256','manifest_sha256','approval_sha256','attempt_sha256')},'publish_dispatches':0}
