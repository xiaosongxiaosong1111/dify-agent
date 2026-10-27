"""Local Docker transport. Own labelled temporary containers only; no host user-code exec."""
import hashlib,json,os,re,shutil,subprocess,sys,tempfile,threading,time,uuid
from pathlib import Path
IMAGE='sha256:ceede5b903afaa20348f7ad80ebf847379dc56d886a99b9ec6a08913dacd7732'
REPOSITORY='langgenius/dify-api@'+IMAGE
LABEL='io.sierra.code-sample'
PROFILE='pure-python-v1'
HOST='npipe:////./pipe/dockerDesktopLinuxEngine' if sys.platform=='win32' else 'unix:///var/run/docker.sock'
LIMITS={'wall_seconds':3,'cpu_seconds':4,'host_wait_seconds':8,'memory_bytes':134217728,'cpus':1,'pids':32,'code_bytes':32768,'input_bytes':65536,'output_bytes':32768,'printed_bytes':4096,'network':'none','host_mounts':False,'read_only_root':True,'user':'65534:65534','capabilities':'drop_all','no_new_privileges':True,'image_pulled':False}
class DockerProblem(RuntimeError):
 def __init__(self,code):super().__init__(code);self.code=code

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

def command(args,*,payload=None,timeout=6,limit=131072):
 try:proc=subprocess.Popen(args,stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={k:v for k,v in os.environ.items() if k.upper() not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_CONFIG','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 except OSError:raise DockerProblem('docker_unavailable') from None
 output=[bytearray(),bytearray()];overflow=threading.Event()
 def reader(stream,target):
  try:
   while True:
    chunk=stream.read(4096)
    if not chunk:break
    if len(target)+len(chunk)>limit:overflow.set();break
    target.extend(chunk)
  finally:stream.close()
 def writer():
  try:proc.stdin.write(payload);proc.stdin.flush()
  except (OSError,ValueError):pass
  finally:proc.stdin.close()
 threads=[threading.Thread(target=reader,args=(stream,target),daemon=True) for stream,target in zip((proc.stdout,proc.stderr),output)]
 if payload is not None:threads.append(threading.Thread(target=writer,daemon=True))
 for thread in threads:thread.start()
 deadline=time.monotonic()+timeout;problem=None
 try:
  while proc.poll() is None:
   if overflow.is_set():problem='transport_output_limit';break
   if time.monotonic()>=deadline:problem='docker_timeout';break
   time.sleep(.025)
  if problem:proc.kill()
  proc.wait(timeout=2)
 finally:
  if proc.poll() is None:proc.kill();proc.wait(timeout=2)
  for thread in threads:thread.join(timeout=2)
 if any(t.is_alive() for t in threads):raise DockerProblem('transport_cleanup_unknown')
 if problem or overflow.is_set():raise DockerProblem(problem or 'transport_output_limit')
 return proc.returncode,bytes(output[0]),bytes(output[1])

class LocalDocker:
 def __enter__(self):
  self.cli=shutil.which('docker')
  if not self.cli:raise DockerProblem('docker_unavailable')
  self.temp=tempfile.TemporaryDirectory(prefix='sierra-code-cli-');self.config=Path(self.temp.name)
  (self.config/'config.json').write_text('{"auths":{},"proxies":{}}','utf-8')
  return self
 def __exit__(self,*args):
  # Only our newly allocated config directory is recursively cleaned.
  if self.config.resolve().parent!=Path(tempfile.gettempdir()).resolve() or not self.config.name.startswith('sierra-code-cli-'):raise DockerProblem('config_cleanup_unknown')
  self.temp.cleanup()
 def call(self,*args,**kwargs):return command([self.cli,'--host',HOST,'--config',str(self.config),*args],**kwargs)
 def json(self,*args):
  rc,out,_=self.call(*args)
  if rc:raise DockerProblem('docker_unavailable')
  try:return json.loads(out)
  except (ValueError,UnicodeError):raise DockerProblem('docker_protocol_error') from None
 def ready(self):
  security=self.json('info','--format','{{json .SecurityOptions}}')
  if not isinstance(security,list) or not any(v.startswith('name=seccomp,profile=builtin') for v in security if isinstance(v,str)):raise DockerProblem('seccomp_not_verified')
  value=self.json('image','inspect',IMAGE,'--format','{"id":{{json .Id}},"digests":{{json .RepoDigests}},"os":{{json .Os}},"volumes":{{json (index .Config "Volumes")}}}')
  if value.get('id')!=IMAGE or REPOSITORY not in (value.get('digests') or []) or value.get('os')!='linux' or value.get('volumes'):raise DockerProblem('supported_image_missing')
  return {'image_id':IMAGE,'repository_digest':REPOSITORY,'profile':PROFILE,'limits':LIMITS,'local_engine':True,'default_seccomp_verified':True,'image_pulled':False}
 def inspect(self,ident):
  return self.json('inspect',ident,'--format','{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Image}},"config_image":{{json .Config.Image}},"user":{{json .Config.User}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}},"host":{{json .HostConfig}}}')
 def owned(self,value,operation):
  return bool(value.get('image')==IMAGE and value.get('config_image')==IMAGE and value.get('name')=='/sierra-code-'+operation and (value.get('labels') or {}).get(LABEL)==operation and (value.get('labels') or {}).get(LABEL+'.profile')==PROFILE)
 def profile(self,value,operation):
  h=value.get('host') or {};opts=h.get('SecurityOpt') or []
  return bool(self.owned(value,operation) and value.get('user')=='65534:65534' and not value.get('mounts') and h.get('ReadonlyRootfs') is True and h.get('NetworkMode')=='none' and h.get('Memory')==134217728 and h.get('MemorySwap')==134217728 and h.get('NanoCpus')==1000000000 and h.get('PidsLimit')==32 and h.get('AutoRemove') is True and h.get('CapDrop')==['ALL'] and not h.get('CapAdd') and not h.get('Privileged') and any(x.split(':')[0]=='no-new-privileges' for x in opts) and not h.get('Binds') and not h.get('Mounts') and not h.get('PortBindings') and not h.get('Devices') and h.get('PidMode') in ('',None) and h.get('IpcMode')=='private' and all(any(v.get('Name')==name and v.get('Soft')==limit and v.get('Hard')==limit for v in h.get('Ulimits',[])) for name,limit in [('cpu',4),('nofile',64)]))
 def cleanup(self,operation):
  # The operation UUID is server generated. Do not delete by port, prefix, or unverified name.
  try:
   if str(uuid.UUID(operation))!=operation:return False
  except (ValueError,TypeError,AttributeError):return False
  try:
   rc,out,_=self.call('ps','-aq','--filter','name=^/sierra-code-'+operation+'$','--filter','label='+LABEL+'='+operation)
   if rc:return False
   ids=out.decode().split()
   if not ids:return True
   if len(ids)!=1 or not re.fullmatch(r'[0-9a-f]{12,64}',ids[0]):return False
   value=self.inspect(ids[0])
   if not self.owned(value,operation):return False
   rc,_,_=self.call('rm','--force',value['id']);return rc==0
  except (DockerProblem,ValueError,UnicodeError):return False

def worker_source():
 root=Path(__file__).resolve().parent
 return (root/'code_sample_policy.py').read_text('utf-8')+'\n'+(root/'code_sample_worker.py').read_text('utf-8')

def execute(code,inputs,operation,progress=lambda **kw:None):
 from .code_sample_policy import validate_code,json_value
 validate_code(code);json_value(inputs)
 if not isinstance(inputs,dict) or len(canonical(inputs).encode())>65536:raise ValueError('样例参数超过JSON对象边界。')
 if str(uuid.UUID(operation))!=operation:raise DockerProblem('invalid_operation')
 result={'status':'technical_error','error_category':'docker_unavailable','cleanup_verified':False}
 with LocalDocker() as docker:
  try:
   docker.ready();progress(phase='creating',create_dispatches=1)
   args=['create','--pull=never','--rm','-i','--name','sierra-code-'+operation,'--label',LABEL+'='+operation,'--label',LABEL+'.profile='+PROFILE,'--network','none','--read-only','--user','65534:65534','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','128m','--memory-swap','128m','--cpus','1','--pids-limit','32','--ulimit','cpu=4:4','--ulimit','nofile=64:64','--no-healthcheck','--workdir','/tmp','--env','SIERRA_CODE_WORKER=pure-python-v1','--entrypoint','/usr/local/bin/python',IMAGE,'-I','-S','-B','-u','-c',worker_source()]
   rc,out,_=docker.call(*args)
   ident=out.decode().strip()
   if rc or not re.fullmatch(r'[0-9a-f]{64}',ident):raise DockerProblem('container_creation_unknown')
   value=docker.inspect(ident)
   if not docker.profile(value,operation):raise DockerProblem('container_isolation_not_verified')
   progress(phase='executing',container_id=ident,profile_verified=True,start_dispatches=1)
   payload=json.dumps({'code':code,'inputs':inputs},ensure_ascii=False,allow_nan=False).encode()
   rc,out,_=docker.call('start','-ai',ident,payload=payload,timeout=8)
   if rc:raise DockerProblem('container_exit_error')
   try:result=json.loads(out)
   except (ValueError,UnicodeError):raise DockerProblem('worker_protocol_error') from None
   if not isinstance(result,dict) or result.get('status') not in ('returned','timeout','output_limit','code_error','protocol_error','invalid_output') or set(result)-{'status','error_category','output_json'}:raise DockerProblem('worker_protocol_error')
   if result['status']=='returned' and (not isinstance(result.get('output_json'),str) or len(result['output_json'].encode())>32768):raise DockerProblem('worker_protocol_error')
   if result.get('error_category') is not None and (not isinstance(result['error_category'],str) or not re.fullmatch('[A-Za-z_]{1,64}',result['error_category'])):raise DockerProblem('worker_protocol_error')
  except (DockerProblem,ValueError,UnicodeError) as exc:result={'status':'technical_error','error_category':exc.code if isinstance(exc,DockerProblem) else 'worker_protocol_error'}
  finally:result['cleanup_verified']=docker.cleanup(operation)
 if not result['cleanup_verified']:result={'status':'unknown','error_category':'cleanup_unknown','cleanup_verified':False}
 return result
