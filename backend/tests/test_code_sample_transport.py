import copy,sys,uuid
import pytest
from app.code_sample_docker import LocalDocker,DockerProblem,command,IMAGE,LABEL,PROFILE

def profile(operation):
 return {'id':'a'*64,'image':IMAGE,'config_image':IMAGE,'name':'/sierra-code-'+operation,'user':'65534:65534','labels':{LABEL:operation,LABEL+'.profile':PROFILE},'mounts':[],'host':{'ReadonlyRootfs':True,'NetworkMode':'none','Memory':134217728,'MemorySwap':134217728,'NanoCpus':1000000000,'PidsLimit':32,'AutoRemove':True,'CapDrop':['ALL'],'CapAdd':None,'Privileged':False,'SecurityOpt':['no-new-privileges'],'Binds':None,'Mounts':None,'PortBindings':None,'Devices':[],'PidMode':'','IpcMode':'private','Ulimits':[{'Name':'cpu','Soft':4,'Hard':4},{'Name':'nofile','Soft':64,'Hard':64}]}}

@pytest.mark.parametrize('field,value', [('ReadonlyRootfs',False),('NetworkMode','bridge'),('Memory',0),('MemorySwap',-1),('NanoCpus',0),('PidsLimit',0),('AutoRemove',False),('CapDrop',None),('CapAdd',['SYS_ADMIN']),('Privileged',True),('SecurityOpt',[]),('Binds',['/host:/data']),('Mounts',[{}]),('PortBindings',{'80/tcp':[{}]}),('Devices',[{}]),('PidMode','host'),('IpcMode','host'),('Ulimits',[])])
def test_inspection_refuses_relaxed_isolation(field,value):
 operation=str(uuid.uuid4());docker=LocalDocker();original=profile(operation);assert docker.profile(original,operation)
 original['host'][field]=value;assert not docker.profile(original,operation)

@pytest.mark.parametrize('field,value',[('user','0'),('image','other'),('config_image','other'),('mounts',[{}]),('labels',{})])
def test_ownership_and_filesystem_boundary(field,value):
 operation=str(uuid.uuid4());value0=profile(operation);value0[field]=value;assert not LocalDocker().profile(value0,operation)

def test_cleanup_never_deletes_unowned_container(monkeypatch):
 operation=str(uuid.uuid4());docker=LocalDocker();calls=[]
 def fake(*args,**kw):calls.append(args);return 0,b'aaaaaaaaaaaa\n',b''
 monkeypatch.setattr(docker,'call',fake);bad=profile(operation);bad['labels']={};monkeypatch.setattr(docker,'inspect',lambda _:bad)
 assert not docker.cleanup(operation) and not any(call[0]=='rm' for call in calls)

def test_transport_output_and_timeout_are_bounded():
 with pytest.raises(DockerProblem) as e:command([sys.executable,'-c','print("PUBLIC_X"*100000)'],limit=1024)
 assert e.value.code=='transport_output_limit'
 with pytest.raises(DockerProblem) as e:command([sys.executable,'-c','import time; time.sleep(10)'],timeout=.1)
 assert e.value.code=='docker_timeout'

def test_worker_module_cannot_execute_from_host():
 import app.code_sample_worker as worker
 if sys.platform!='linux':assert worker._run()=={'status':'protocol_error','error_category':'isolation_marker_missing'}

@pytest.mark.parametrize('operation',['-'*36,'OTHER','11111111-1111-1111-1111-11111111111x'])
def test_invalid_owner_id_cannot_dispatch_cleanup(monkeypatch,operation):
 docker=LocalDocker()
 def forbid(*a,**kw):raise AssertionError('Invalid owner cannot dispatch')
 monkeypatch.setattr(docker,'call',forbid);assert docker.cleanup(operation) is False
