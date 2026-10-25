"""Exact live invoke AST and pre-Store admission checks with all physical network blocked."""
import ast,asyncio,copy,json,sys,hashlib,tempfile,subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)==2 else Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(PROJECT/'backend'))
from support import snapshot,digest
from guards import Limits
from identity_preflight import verify_identity_fields,KEYS
from app.planning import reserve_cost
before=snapshot();plan=json.loads((ROOT/'plan.json').read_text('utf-8'));f=json.loads((ROOT/'fixture.json').read_text('utf-8'));checks=[]
# Demonstrate the old approved plan is rejected before any executable live stage.
try:verify_identity_fields(PROJECT/'work/complete-mainline270-replacement')
except SystemExit as exc:assert 'missing required plan fields' in str(exc)
else:raise AssertionError('Old missing keys accepted')
checks.append('original approved missing three live identities refused, original pack untouched')
for field in KEYS:
 for kind in ('missing','invalid'):
  with tempfile.TemporaryDirectory(dir=ROOT,prefix='identity-reject-') as folder:
   temp=Path(folder).resolve();assert temp.is_relative_to(ROOT)
   for name in ('server.py','support.py','guards.py','identity_preflight.py'):(temp/name).write_bytes((ROOT/name).read_bytes())
   bad=copy.deepcopy(plan)
   if kind=='missing':bad.pop(field)
   else:bad[field]='not-a-hash'
   (temp/'plan.json').write_text(json.dumps(bad),'utf-8')
   launcher="import socket,sqlite3,os,sys,runpy; os.environ['FLOWCRAFT_DATA_DIR']=sys.argv[1]+'/FORBIDDEN-STORE'; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('NETWORK FORBIDDEN')); sqlite3.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('SQLITE FORBIDDEN')); sys.argv=[sys.argv[1]+'/server.py','live']; runpy.run_path(sys.argv[0],run_name='__main__')"
   result=subprocess.run([sys.executable,'-c',launcher,str(temp)],capture_output=True,text=True,timeout=10)
   assert result.returncode!=0 and 'Frozen plan identity preflight refused' in result.stderr,result.stderr
   assert not (temp/'receipt.json').exists() and not (temp/'FORBIDDEN-STORE').exists()
  checks.append(field+' '+kind+' actual live entry refused before SQLite/network/receipt')
verify_identity_fields(ROOT)
node=next(n for n in ast.walk(ast.parse((ROOT/'server.py').read_text('utf-8'))) if isinstance(n,ast.AsyncFunctionDef) and n.name=='invoke')
async def invoke_phase(n,bad=False):
 phases=['intake','plan_first','plan_changed'];messages=json.loads((ROOT/('captured-'+phases[n]+'-messages.json')).read_text('utf-8'))
 intake=json.loads((ROOT/'rehearse-intake-stage.json').read_text('utf-8'));first=json.loads((ROOT/'rehearse-plan_first-stage.json').read_text('utf-8'));task=copy.deepcopy(intake['task'] if n<2 else first['task'])
 if n==2:
  for field in ('output','tests'):task['requirements'][field]=task['requirements'][field].replace(f['before_literal'],f['after_literal'])
 p=copy.deepcopy(plan)
 if bad:p[KEYS[n]]='0'*64
 record={'model_invocations':n,'requests':[{'reserved_estimate_usd':'0'}]*n};limits=Limits(p)
 if n==2:limits.apps.add('synthetic-app');limits.keyed.add('synthetic-app');limits.counts['run']=2
 forwarded=[]
 async def sink(*a,**kw):forwarded.append(1);return 'LIVE-BRANCH-FAKE-FINAL-CALL'
 space={'guard':lambda:None,'record':record,'f':f,'plan':p,'reserve_cost':reserve_cost,'json':json,'main':SimpleNamespace(get_task=lambda _:task),'tid':f['task']['id'],'gate':lambda phase:intake if phase=='intake' else first,'copy':copy,'digest':digest,'hashlib':hashlib,'Decimal':Decimal,'limits':limits,'save':lambda:None,'original_call':sink,'live':True,'ROOT':ROOT}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'<exact live invoke branch>','exec'),space)
 if bad:
  try:await space['invoke'](f['provider'],'FAKE-KEY-NOT-A-SECRET',messages,max_tokens=6000,timeout=120)
  except AssertionError:pass
  else:raise AssertionError('Wrong live hash accepted')
  assert not forwarded and record['model_invocations']==n and len(record['requests'])==n and limits.counts['model']==0
 else:
  assert await space['invoke'](f['provider'],'FAKE-KEY-NOT-A-SECRET',messages,max_tokens=6000,timeout=120)=='LIVE-BRANCH-FAKE-FINAL-CALL'
  assert forwarded==[1] and record['model_invocations']==n+1
 checks.append(phases[n]+(' wrong identity refused before invocation/forward' if bad else ' exact live branch identity passes captured real request construction with fake final call'))
async def run():
 for n in range(3):await invoke_phase(n);await invoke_phase(n,True)
asyncio.run(run());assert snapshot()==before
proof={'state':'passed','checks':checks,'check_count':len(checks),'physical_http':0,'source16_objects_ciphertexts_master_key_old_receipts_unknown_kept':True,'old_approved_plan_unchanged':True,'live_receipt_exists':(ROOT/'receipt.json').exists()};assert proof['live_receipt_exists'] is False
(ROOT/'live-identity-proof.json').write_text(json.dumps(proof,indent=2),'utf-8');print(json.dumps({'state':'passed','checks':len(checks),'real_http':0}))
