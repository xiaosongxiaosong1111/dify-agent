"""Local operator command. Never dispatches Dify/model requests or authorizes their scope."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.publication_dispatch_receipt import validate

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('project-root','data-root','bundle','source-commit','report-path','actor-note'):p.add_argument('--'+name,required=True)
 p.add_argument('--actor',choices=['user','agent_delegated'],required=True)
 p.add_argument('--acknowledge-local-source',action='store_true',required=True)
 args=p.parse_args()
 try:
  summary=validate(Path(args.project_root),Path(args.bundle),args.source_commit,args.report_path)
  data=Path(args.data_root).resolve()
  if not (data/'flowcraft.sqlite3').is_file() or not (data/'.credential-key').is_file():raise ValueError('只允许既有本机数据库和加密主Key，不创建新工作区。')
  os.environ['FLOWCRAFT_DATA_DIR']=str(data)
  import httpx
  def forbidden(*a,**k):raise RuntimeError('证据登记禁止联网或调用模型。')
  httpx.HTTPTransport.handle_request=forbidden;httpx.AsyncHTTPTransport.handle_async_request=forbidden
  from app import main as h
  h.call_model=forbidden
  from app.publication_recovery import register_evidence,public
  row,created=register_evidence(h,summary,args.actor,args.actor_note)
  print(json.dumps({'created':created,'evidence':public(h,row,h.get_task(row['task_id']))},ensure_ascii=False))
 except Exception:
  print(json.dumps({'error':'本机证据登记失败；未联网、未恢复或改变原unknown。请核对提交、冻结文件和当前来源。'},ensure_ascii=False));return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
