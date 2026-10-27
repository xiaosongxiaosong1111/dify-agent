"""Frozen scope/provenance and transport admission negatives; never construct a production Store."""
import copy,json,sys,tempfile,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
import execute
from execute import FROZEN,LIMITS,validated_plan,approved,claim_attempt
from support import sha
from boundary import Boundary,require
import httpx
checks=[]
def rejected(label,fn):
 try:fn()
 except (RuntimeError,ValueError,OSError,KeyError):checks.append(label);return
 raise AssertionError('Gate accepted: '+label)
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf-8')
with tempfile.TemporaryDirectory(dir=PROJECT/'work',prefix='existing353-gates-') as folder:
 root=Path(folder)/'work/batch-platform353';root.mkdir(parents=True)
 for name in FROZEN-{'plan.json'}:(root/name).write_bytes((ROOT/name).read_bytes())
 plan={'schema_version':1,'batch_id':'existing-batch-platform353','limits':LIMITS,'wall_seconds':600,'task_id':str(uuid.uuid4()),'revision':6,'app_id':str(uuid.uuid4()),'old_publication_id':str(uuid.uuid4()),'evidence_id':str(uuid.uuid4())};write(root/'plan.json',plan)
 def manifest():write(root/'manifest.json',{'schema_version':1,'batch_id':plan['batch_id'],'files':{k:sha(root/k) for k in sorted(FROZEN)}})
 manifest();assert validated_plan(root)==plan;checks.append('valid exact scope and full frozen file set')
 rejected('missing approval',lambda:approved(root,plan))
 approval={'authorization_source':'direct_human_reply','decision':'approve','batch_id':plan['batch_id'],'plan_sha256':sha(root/'plan.json'),'manifest_sha256':sha(root/'manifest.json'),'limits':LIMITS,'explicit_zero_dispatch350_transfer_authorized':True,'old_reservations_preserved':True,'question_ref':'synthetic-question-only','reply':'isolated approval only'}
 for key,value in [('authorization_source','agent_delegated'),('decision','deny'),('batch_id','old350'),('plan_sha256','0'*64),('manifest_sha256','0'*64),('limits',LIMITS|{'import':1}),('explicit_zero_dispatch350_transfer_authorized',False),('old_reservations_preserved',False),('question_ref',' '),('reply',' ')]:
  write(root/'approval.json',approval|{key:value});rejected('bad approval '+key,lambda:approved(root,plan))
 write(root/'approval.json',approval);assert approved(root,plan)==approval;checks.append('new independent scope requires direct approval and explicit transfer')
 for key,value in [('limits',LIMITS|{'import':1}),('limits',LIMITS|{'new_tasks':True}),('limits',LIMITS|{'model':1}),('limits',LIMITS|{'reads':17}),('wall_seconds',601),('batch_id','public-batch-platform350')]:
  write(root/'plan.json',plan|{key:value});manifest();rejected('bad frozen '+key+str(value),lambda:validated_plan(root))
 write(root/'plan.json',plan);manifest()
 (root/'boundary.py').write_bytes(b'tampered');rejected('tampered source',lambda:validated_plan(root));(root/'boundary.py').write_bytes((ROOT/'boundary.py').read_bytes());manifest()
 original=json.loads((root/'manifest.json').read_text('utf-8'));bad=copy.deepcopy(original);bad['files']['../escape.py']='0'*64;write(root/'manifest.json',bad);rejected('manifest extra path',lambda:validated_plan(root));write(root/'manifest.json',original)
 write(root/'plan.json',plan);manifest();write(root/'approval.json',approval|{'manifest_sha256':sha(root/'manifest.json')})
 class StopBeforeProduction(RuntimeError):pass
 touched=[]
 def stop(plan):touched.append('runtime');raise StopBeforeProduction('synthetic admission stop')
 with patch.object(execute,'ROOT',root),patch.object(execute,'PROJECT',Path(folder)),patch.object(execute,'runtime_check',stop),patch.object(sys,'argv',['execute.py','live']):
  try:execute.main()
  except SystemExit:pass
  assert touched==['runtime'] and (root/'attempt.json').exists();old=(root/'attempt.json').read_bytes();checks.append('claim once then stop before any production Store')
  rejected('consumed attempt never overwritten',execute.main);assert (root/'attempt.json').read_bytes()==old and touched==['runtime']
 rejected('canonical directory rejects source live execution',execute.main)
 # Every boundary-negative is a new isolated instance; no network request is sent.
 def boundary():return Boundary('https://public.invalid','workspace','a'*64,{'input':{'items_json':'[]'}},{'phase':'publish'},str(uuid.uuid4()),'task','evidence')
 for method,url,body,label in [('POST','https://public.invalid/console/api/apps/imports',{},'no import'),('POST','https://wrong.invalid/console/api/login',{},'foreign origin'),('GET','https://public.invalid/console/api/apps/foreign',None,'foreign App'),('DELETE','https://public.invalid/console/api/apps',None,'no deletion')]:
  b=boundary();request=httpx.Request(method,url,json=body) if body is not None else httpx.Request(method,url);rejected(label,lambda:b.admit(request));assert sum(b.counts.values())==0
 b=boundary();url='https://public.invalid/console/api/apps/'+b.app+'/workflows/publish';request=httpx.Request('POST',url,json={'marked_name':'x','marked_comment':'y'})
 rejected('no reconnect no target read/write',lambda:b.admit(request));b.workspace_verified=True;b.counts['login']=1
 rejected('no store/declaration cannot publish',lambda:b.admit(request))
 class Empty:
  def list(self,kind):return []
 b.store=Empty();rejected('missing consumed declaration cannot publish',lambda:b.admit(request))
 b.halted=True;rejected('halted batch admits nothing',lambda:b.admit(httpx.Request('GET','https://public.invalid/console/api/apps?page=1&limit=1')))
 print(json.dumps({'state':'passed','gates':len(checks),'checks':checks,'physical_http':0,'production_store_constructed':False},ensure_ascii=False))
