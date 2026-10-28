"""One isolated C1 chain. The live entry and approval are not available here."""
import argparse,contextlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;PROJECT=ROOT.parents[1];sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from guard import capture
class ReadOnly:
 def __init__(self,root):self.root=root
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
  try:yield db
  finally:db.close()
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['success','fail_login','expired_session','wrong_workspace','fail_model','invalid_plan','fail_publish','fail_run'],default='success');p.add_argument('--output',required=True);p.add_argument('--playwright',required=True);args=p.parse_args()
out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');assert Path(args.playwright).is_absolute() and Path(args.playwright).is_dir();out.mkdir(exist_ok=False,parents=True)
readonly=ReadOnly(PROJECT/'data');before=capture(readonly)
from worker import run
try:
 record=run(args.mode,out,args.playwright)
 assert args.mode=='success' and record['state']=='passed'
 print(json.dumps({'state':'passed','synthetic_counts':record['dispatch_counts'],'semantic_reviews':False,'physical_http':0}))
except Exception:
 if args.mode=='success':raise
 record=json.loads((out/'progress.json').read_text('utf-8'));assert record['state']=='stopped_needs_review';print(json.dumps({'state':'stopped_needs_review','mode':args.mode,'synthetic_counts':record['dispatch_counts'],'physical_http':0}))
finally:assert capture(readonly)==before,'Production changed in isolated rehearsal'
