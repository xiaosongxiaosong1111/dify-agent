"""Existing App only; independent one-shot declaration, no import/new resource bypass."""
from boundary_base import Boundary as Original,require,canonical,digest

class Boundary(Original):
 def __init__(self,base,workspace,graph_digest,fixture,record,app,task_id,evidence_id,**kw):
  super().__init__(base,workspace,graph_digest,fixture,record,(),**kw)
  self.app=app;self.task_id=task_id;self.evidence_id=evidence_id;self.store=None
 def admit(self,request):
  path=request.url.path;phase=self.record.get('phase')
  require(not (request.method=='POST' and path=='/console/api/apps/imports'),'No App import allowed')
  if self.app in path:
   require(self.workspace_verified and self.counts['login']==1,'Target reads/writes require this explicit reconnect')
  if request.method=='POST' and path.endswith('/workflows/publish'):
   require(phase=='publish' and self.store is not None,'Publication outside approved phase')
   rows=self.store.list('publication_recovery');rows=[r for r in rows if r.get('id')==self.record.get('recovery_id')]
   require(len(rows)==1 and rows[0]['state']=='consumed' and rows[0].get('evidence_id')==self.evidence_id and rows[0].get('publication_proposal_id')==self.record.get('new_publication_proposal_id'),'Publication needs atomically consumed declaration')
  if request.method=='POST' and path.endswith('/api-keys'):require(phase=='create_key' and self.counts['publish']==1,'Key outside new publication phase')
  if path=='/v1/workflows/run':require(phase=='run' and self.counts['key']==1,'Run outside dedicated-key phase')
  return super().admit(request)
 def observed(self,entry,response):
  if entry['method']=='GET' and entry['path']==f'/console/api/apps/{self.app}/workflows/publish' and response.is_success and self.counts['publish']==0:
   require(response.json() is None,'Existing published App must not be overwritten')
  if entry['path'].endswith('/workflows/draft') and response.is_success:
   from app.workflow_publication import core
   value=response.json();require(isinstance(value,dict) and isinstance(value.get('hash'),str) and value['hash'] and digest(core(value))==self.graph_digest,'Current draft differs from frozen graph')
  return super().observed(entry,response)
