"""Submit the root agent's explicit local content decision. No network and no resource authorization."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
def submit(output,stage,source_hash,note,decision="proceed"):
 from app.publication_dispatch_receipt import strict_json
 from app.plan_drafts import inspect_text
 output=Path(output).resolve()
 if not output.is_relative_to(ROOT/'work') or stage not in ('complete_interview','first_plan','changed_requirements_manual','changed_plan'):raise ValueError('Wrong local review source')
 if decision not in ('proceed','reject'):raise ValueError('Explicit decision required')
 if not isinstance(note,str) or not note.strip() or len(note)>4000:raise ValueError('Explicit review note required')
 inspect_text(note);source=strict_json((output/('review-source-'+stage+'.json')).read_bytes())
 from reviews import digest
 if source.get('stage')!=stage or digest(source)!=source_hash:raise ValueError('Source changed')
 task=source['task'];value={'stage':stage,'task_id':task['id'],'revision':task['revision'],'source_sha256':source_hash,'decision':decision,'actor':'agent_delegated','note':note}
 destination=output/('review-'+stage+'.json');temporary=output/('review-'+stage+'.pending')
 if destination.exists():raise ValueError('Review already submitted')
 with temporary.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
 temporary.rename(destination)
 if decision=='reject':
  with (output/'stop.json').open('x',encoding='utf-8') as f:json.dump({'stage':stage,'source_sha256':source_hash,'actor':'agent_delegated','reason':note},f,ensure_ascii=False)
 return {'state':'submitted' if decision=='proceed' else 'rejected_stopped','stage':stage,'task_id':task['id'],'revision':task['revision'],'network_requested':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--stage',required=True);p.add_argument('--source-sha256',required=True);p.add_argument('--note',required=True);p.add_argument('--decision',choices=['proceed','reject'],default='proceed');args=p.parse_args()
 try:print(json.dumps(submit(args.output,args.stage,args.source_sha256,args.note,args.decision),ensure_ascii=False))
 except Exception:raise SystemExit('本机内容复核来源、说明或一次提交无效；未授权或派发任何外部请求。') from None
