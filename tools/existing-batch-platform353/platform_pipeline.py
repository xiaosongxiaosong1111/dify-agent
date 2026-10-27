"""One new sequence against an already imported App; old batch is never executed."""
import hashlib,json
from boundary import require,canonical
from local_pipeline import ROWS

def run(api,plan,record):
 def call(method,path,body=None):
  response=api.request(method,path,json=body) if body is not None else api.request(method,path)
  record.setdefault('local_requests',[]).append({'method':method,'path':path,'status':response.status_code})
  require(response.status_code in (200,201),'Normal API stage failed: '+path+' HTTP '+str(response.status_code));return response.json()
 task=call('GET','/api/tasks/'+plan['task_id']);require(task['revision']==plan['revision'] and task['dify_app_id']==plan['app_id'],'Existing Task binding changed')
 base='/api/tasks/'+task['id'];record.update(task_id=task['id'],revision=task['revision'],existing_app_id=task['dify_app_id'])
 record['phase']='reconnect';auth='/api/environments/'+plan['environment_id']+'/saved-login/'
 proposal=call('POST',auth+'reconnect-plan',{});result=call('POST',auth+'reconnect',{'plan_id':proposal['id'],'review_token':proposal['review_token'],'confirm_reconnect':True});require(result['record']['state']=='succeeded','Saved reconnect did not succeed')
 record['phase']='local_recovery'
 proposal=call('POST',base+'/publication-recovery/prepare',{'revision':task['revision'],'evidence_id':plan['evidence_id']});require(proposal['state']=='prepared' and proposal['current_source'] is True,'Only a new local recovery declaration is accepted')
 resolved=call('POST',base+'/publication-recovery/confirm',{'revision':task['revision'],'recovery_id':proposal['id'],'review_token':proposal['review_token'],'acknowledge_no_dispatch':True,'acknowledge_new_attempt':True,'actor':'agent_delegated','actor_note':'按本新独立批直接批准及既有委托核对已提交零派发证据；本机一致性声明，原unknown保持，不重放旧350。'})
 require(resolved['state']=='ready' and resolved['current_source'] is True,'Local recovery not ready');record['recovery_id']=resolved['id']
 record['phase']='publish'
 proposal=call('POST',base+'/workflow-publication/prepare',{'revision':task['revision'],'recovery_id':resolved['id']});require(proposal['state']=='ready','Publication not ready');record['new_publication_proposal_id']=proposal['id']
 published=call('POST',base+'/workflow-publication/confirm',{'revision':task['revision'],'recovery_id':resolved['id'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'confirm_publish':True});require(published['state']=='succeeded','Publication did not succeed')
 record['phase']='create_key';proposal=call('POST',base+'/runtime-key-creation/plan',{'revision':task['revision']})
 keyed=call('POST',base+'/runtime-key-creation/confirm',{'revision':task['revision'],'proposal_id':proposal['id'],'review_token':proposal['review_token'],'confirm_create_and_bind':True});require(keyed['state']=='succeeded','Runtime Key creation not successful')
 record['phase']='run';task=call('POST',base+'/run',{'revision':task['revision'],'case_id':'public-four-items'});runs=[r for r in task['runs'] if r.get('kind')=='run'];require(len(runs)==1,'Expected one run only');run=runs[0]
 require(run['status']=='success' and run['evaluation']['status']=='passed','Saved execution or exact declared check not passed');data=run['result']['data'];rows=data['outputs']['results'];require(canonical(rows)==canonical(ROWS),'Actual per-item output differs from public declaration')
 require(data['workflow_id']==published['workflow_id'],'Actual run not bound to newly published source');outputs=data['outputs'];require(set(outputs)=={'results','successes','failures','total','succeeded','failed'},'Unexpected output fields');require(all(type(outputs[k]) in (int,float) and outputs[k]==v for k,v in [('total',4),('succeeded',3),('failed',1)]) and canonical(outputs['failures'])==canonical([ROWS[1]]) and canonical(outputs['successes'])==canonical([ROWS[0],ROWS[2],ROWS[3]]),'Actual counts or split not matched')
 record['phase']='saved_output_read';params={'revision':task['revision'],'field':'results','state':'failed'};response=api.get(base+'/runs/'+run['id']+'/iteration-results',params=params);require(response.status_code==200,'Saved per-item view failed');view=response.json();require(view['total']==4 and view['failed']==1 and [r['index'] for r in view['rows']]==[1],'Saved failure view did not preserve index')
 response=api.get(base+'/runs/'+run['id']+'/iteration-results/export',params={**params,'source':view['source_sha256']});require(response.status_code==200,'Saved failure export failed');require(response.headers['x-sierra-content-sha256']==hashlib.sha256(response.content).hexdigest() and canonical(response.json()['items'])==canonical([ROWS[1]]),'Failure export differs from complete source')
 record.update(state='passed',phase='complete',task_id=task['id'],revision=task['revision'],run_id=run['id'],declared_case_passed=True,total=4,succeeded=3,failed=1,failure_indices=[1],business_acceptance_complete=False)
 return task,response.content
