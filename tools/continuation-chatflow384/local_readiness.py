"""Read-only check for this workspace's existing localhost Dify Docker stack."""
import json,re,shutil,subprocess
from urllib.parse import urlsplit

PROJECT='dify-local'
SERVICES=('worker','api','agent_backend','plugin_daemon','worker_beat','nginx','sandbox','api_websocket','web','db_postgres','init_permissions','ssrf_proxy','redis','agent_ssrf_proxy','weaviate','local_sandbox')
HEALTHY={'api','sandbox','db_postgres','redis','local_sandbox'}
TEMPLATE='{"name":{{json .Names}},"state":{{json .State}},"status":{{json .Status}},"image":{{json .Image}},"ports":{{json .Ports}}}'

class NotReady(RuntimeError):
 def __init__(self,code):
  self.code=code
  super().__init__('本机Dify未通过消费前只读就绪核对（'+code+'）；未登录、不消费批次、不自动启动或重试。')

def validate_rows(rows):
 if not isinstance(rows,list) or not 1<=len(rows)<=32:raise NotReady('local_container_inventory_invalid')
 by={}
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'name','state','status','image','ports'} or not all(isinstance(v,str) and len(v)<=2048 for v in row.values()):raise NotReady('local_container_inventory_invalid')
  name=row['name']
  if name in by:raise NotReady('local_container_inventory_invalid')
  by[name]=row
 for service in SERVICES:
  row=by.get(PROJECT+'-'+service+'-1')
  if row is None:raise NotReady('local_container_missing')
  if service=='init_permissions':
   if row['state']!='exited' or not row['status'].startswith('Exited (0) '):raise NotReady('local_initialization_not_complete')
  elif row['state']!='running':raise NotReady('local_container_not_running')
  if service in HEALTHY and '(healthy)' not in row['status']:raise NotReady('local_container_not_healthy')
  if service in {'api','worker','worker_beat','api_websocket'} and row['image']!='langgenius/dify-api:1.17.1':raise NotReady('local_dify_version_mismatch')
 if by[PROJECT+'-web-1']['image']!='langgenius/dify-web:1.17.1':raise NotReady('local_dify_version_mismatch')
 if not re.search(r'(?:127\.0\.0\.1|0\.0\.0\.0):8080->80/tcp',by[PROJECT+'-nginx-1']['ports']):raise NotReady('local_proxy_binding_missing')
 return {'applicable':True,'ready':True,'compose_project':PROJECT,'required_containers':len(SERVICES),'healthy_services':sorted(HEALTHY),'dify_http_requests':0,'login_verified':False,'business_verified':False}

def check(base_url,*,runner=subprocess.run,docker_executable=None):
 try:u=urlsplit(base_url);local=u.scheme=='http' and u.hostname in ('127.0.0.1','localhost') and u.port==8080 and u.path in ('','/')
 except (ValueError,TypeError):local=False
 if not local:return {'applicable':False,'ready':None,'dify_http_requests':0,'login_verified':False}
 executable=docker_executable or shutil.which('docker')
 if not executable:raise NotReady('local_docker_cli_missing')
 def read(args):
  try:r=runner([executable,*args],capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  except (OSError,subprocess.TimeoutExpired):raise NotReady('local_docker_engine_unavailable') from None
  if r.returncode!=0 or len(r.stdout)>65536:raise NotReady('local_docker_engine_unavailable')
  try:return r.stdout.decode('utf-8-sig')
  except (UnicodeError,AttributeError):raise NotReady('local_container_inventory_invalid') from None
 version=read(['version','--format','{{.Server.Version}}']).strip()
 if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?',version):raise NotReady('local_docker_engine_unavailable')
 raw=read(['ps','-a','--filter','label=com.docker.compose.project='+PROJECT,'--format',TEMPLATE])
 try:rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
 except (ValueError,TypeError):raise NotReady('local_container_inventory_invalid') from None
 return validate_rows(rows)
