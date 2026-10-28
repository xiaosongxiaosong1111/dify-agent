"""Replay the HTTP200/rejected-candidate shape through the immutable local UI chain."""
import argparse,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT/'work/c1-existing357'
sys.path[:0]=[str(ROOT),str(PROJECT/'backend')]
from execute import validated
from support import current
from synthetic import Synthetic
from worker import run
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--playwright',required=True);args=p.parse_args()
out=Path(args.output).resolve();assert out.is_relative_to(PROJECT/'work');out.mkdir(exist_ok=False,parents=True)
plan=validated(ROOT);current(PROJECT,plan);original=Synthetic.model
def missing_topic(self):
 value=original(self)
 if self.b.record['phase']=='vague_interview':value['requirements_patch']={'knowledge':'拟议（待确认）：知识库检索。'}
 return value
Synthetic.model=missing_topic
try:
 try:run('isolated_intake_contract_rejection',out,args.playwright)
 except RuntimeError:pass
 else:raise AssertionError('Rejected candidate advanced through the chain')
 value=json.loads((out/'progress.json').read_text('utf-8'))
 assert value['state']=='stopped_needs_review' and value['phase']=='vague_interview'
 assert value['dispatch_counts']=={'model':1,'reads':2,'login':1,'import':0,'publish':0,'key':0,'run':0}
 assert value['physical_http']==0 and not value.get('reviews')
 assert value['protection']['existing_failed_history_and_ledger_kept'] and value['protection']['new_tasks']==0
 assert value['protection']['other_original_tasks_objects_and_ledgers_kept']
 assert len([d for d in value['dispatches'] if d['kind']=='model' and d['status']==200])==1
 proof={'state':'passed','stage':'vague_interview','http200_candidate_rejected':True,'no_content_review_or_next_stage':True,'new_model_dispatches':1,'new_tasks':0,'old_failure_and_settled_cost_kept':True,'physical_http':0}
 (out/'proof.json').write_text(json.dumps(proof,indent=2),'utf-8');print(json.dumps(proof))
finally:
 Synthetic.model=original;current(PROJECT,plan)
