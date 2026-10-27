"""One sequential normal-API stage; no retries or automatic repair."""
import hashlib,json
from boundary import require,canonical
from local_pipeline import LocalPipeline,ROWS

def run(api,environment_id,record):
 def call(method,path,body=None):
  response=api.request(method,path,json=body) if body is not None else api.request(method,path)
  record.setdefault('local_requests',[]).append({'method':method,'path':path,'status':response.status_code})
  require(response.status_code in (200,201),'Normal API stage failed: '+path+' HTTP '+str(response.status_code));return response.json()
 record['phase']='reconnect';base='/api/environments/'+environment_id+'/saved-login/'
 proposal=call('POST',base+'reconnect-plan',{});reconnected=call('POST',base+'reconnect',{'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True});require(reconnected['record']['state']=='succeeded','Saved reconnect did not succeed')
 record['phase']='normal_local_prepare';runner=LocalPipeline(api,environment_id,record);task=runner.prepare();base='/api/tasks/'+task['id'];record['phase']='import'
 task=call('POST',base+'/import',{'revision':task['revision']});record['phase']='publish'
 proposal=call('POST',base+'/workflow-publication/prepare',{'revision':task['revision']});require(proposal['state']=='ready','Publication not ready')
 published=call('POST',base+'/workflow-publication/confirm',{'revision':task['revision'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'confirm_publish':True});require(published['state']=='succeeded','Publication did not succeed')
 record['phase']='create_key';proposal=call('POST',base+'/runtime-key-creation/plan',{'revision':task['revision']})
 keyed=call('POST',base+'/runtime-key-creation/confirm',{'revision':task['revision'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'confirm_create_and_bind':True});require(keyed['state']=='succeeded','Runtime Key creation not successful')
 record['phase']='run';task=call('POST',base+'/run',{'revision':task['revision'],'case_id':'public-four-items'});runs=[r for r in task['runs'] if r.get('kind')=='run'];require(len(runs)==1,'Expected one run only');run=runs[0]
 require(run['status']=='success' and run['evaluation']['status']=='passed','Saved execution or exact declared check not passed');data=run['result']['data'];rows=data['outputs']['results'];require(canonical(rows)==canonical(ROWS),'Actual per-item output differs from public declaration')
 require(data['workflow_id']==published['workflow_id'],'Actual run not bound to newly published source');outputs=data['outputs'];require(set(outputs)=={'results','successes','failures','total','succeeded','failed'},'Unexpected output fields');require(all(type(outputs[k]) in (int,float) and outputs[k]==v for k,v in [('total',4),('succeeded',3),('failed',1)]) and canonical(outputs['failures'])==canonical([ROWS[1]]) and canonical(outputs['successes'])==canonical([ROWS[0],ROWS[2],ROWS[3]]),'Actual counts or split not matched')
 record['phase']='saved_output_read';params={'revision':task['revision'],'field':'results','state':'failed'};response=api.get(base+'/runs/'+run['id']+'/iteration-results',params=params);require(response.status_code==200,'Saved per-item view failed');view=response.json();require(view['total']==4 and view['failed']==1 and [r['index'] for r in view['rows']]==[1],'Saved failure view did not preserve index')
 response=api.get(base+'/runs/'+run['id']+'/iteration-results/export',params={**params,'source':view['source_sha256']});require(response.status_code==200,'Saved failure export failed');require(response.headers['x-sierra-content-sha256']==hashlib.sha256(response.content).hexdigest() and canonical(response.json()['items'])==canonical([ROWS[1]]),'Failure export differs from complete source')
 record.update(state='passed',phase='complete',task_id=task['id'],revision=task['revision'],run_id=run['id'],declared_case_passed=True,total=4,succeeded=3,failed=1,failure_indices=[1],business_acceptance_complete=False)
 return task,response.content
