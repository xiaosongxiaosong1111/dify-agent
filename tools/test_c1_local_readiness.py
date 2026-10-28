"""Only disposable fixtures and mocked SDK transports; no Dify or supplier calls."""
import copy,json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import httpx,pytest

ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'c1-existing357'
sys.path[:0]=[str(SOURCE),str(ROOT.parent/'backend')]
from local_readiness import SERVICES,HEALTHY,NotReady,check,validate_rows
from guard import Boundary
from transport import dispatch
from app.dify import DifyClient,DifyError

def rows():
 return [{'name':'dify-local-'+s+'-1','state':'exited' if s=='init_permissions' else 'running','status':'Exited (0) 2 weeks ago' if s=='init_permissions' else 'Up 1 minute'+(' (healthy)' if s in HEALTHY else ''),'image':'langgenius/dify-api:1.17.1' if s in {'api','worker','worker_beat','api_websocket'} else 'langgenius/dify-web:1.17.1' if s=='web' else 'public-image','ports':'127.0.0.1:8080->80/tcp' if s=='nginx' else ''} for s in SERVICES]

@pytest.mark.parametrize('failure',['missing','duplicate','stopped','unhealthy','starting','bad_init','wrong_api','wrong_web','wrong_port','unknown_field'])
def test_stack_states_reject_before_login(failure):
 value=rows();by={r['name'].split('dify-local-',1)[1].removesuffix('-1'):r for r in value}
 if failure=='missing':value.pop()
 elif failure=='duplicate':value.append(copy.deepcopy(value[0]))
 elif failure=='stopped':by['worker']['state']='exited'
 elif failure in {'unhealthy','starting'}:by['api']['status']='Up (unhealthy)' if failure=='unhealthy' else 'Up (health: starting)'
 elif failure=='bad_init':by['init_permissions']['status']='Exited (1) 1 minute ago'
 elif failure=='wrong_api':by['api']['image']='langgenius/dify-api:latest'
 elif failure=='wrong_web':by['web']['image']='langgenius/dify-web:latest'
 elif failure=='wrong_port':by['nginx']['ports']='127.0.0.1:8888->80/tcp'
 else:by['api']['environment']='secret-not-to-be-reflected'
 with pytest.raises(NotReady) as exc:validate_rows(value)
 assert 'secret-not-to-be-reflected' not in str(exc.value)

def test_readiness_is_limited_local_metadata_and_does_not_accept_login():
 calls=[]
 def cli(args,**kwargs):
  calls.append(args);assert kwargs['timeout']==10 and kwargs['capture_output']
  body='29.8.2' if args[1]=='version' else '\n'.join(json.dumps(r) for r in rows())
  return SimpleNamespace(returncode=0,stdout=body.encode())
 result=check('http://127.0.0.1:8080',runner=cli,docker_executable='public-docker.exe')
 assert result['ready'] and not result['login_verified'] and result['dify_http_requests']==0
 assert [c[1] for c in calls]==['version','ps']
 assert calls[1][2:5]==['-a','--filter','label=com.docker.compose.project=dify-local']

@pytest.mark.parametrize('failure',['engine_error','timeout','malformed_version','malformed_json','oversized'])
def test_cli_failure_is_fixed_safe_diagnostic(failure):
 count=[]
 def cli(args,**kwargs):
  count.append(1)
  if failure=='timeout':raise subprocess.TimeoutExpired(args,10,output=b'sk-private')
  if failure=='engine_error':return SimpleNamespace(returncode=1,stdout=b'sk-private',stderr=b'password=private')
  if args[1]=='version':body='malformed' if failure=='malformed_version' else '29.8.2'
  else:body='x'*65537 if failure=='oversized' else '{sk-private'
  return SimpleNamespace(returncode=0,stdout=body.encode())
 with pytest.raises(NotReady) as exc:check('http://localhost:8080',runner=cli,docker_executable='public-docker.exe')
 assert 'sk-private' not in str(exc.value) and 'password' not in str(exc.value)
 assert len(count)<=2

def test_remote_target_does_not_inspect_host_docker():
 def forbidden(*a,**kw):raise AssertionError('Remote target must not use host Docker')
 assert check('https://public-dify.invalid',runner=forbidden)['applicable'] is False

def test_failed_local_preflight_precedes_attempt_claim(tmp_path,monkeypatch):
 import execute
 project=tmp_path;canonical=project/'work/c1-existing357';canonical.mkdir(parents=True)
 monkeypatch.setattr(execute,'ROOT',canonical);monkeypatch.setattr(execute,'PROJECT',project)
 monkeypatch.setattr(sys,'argv',['execute.py','live','--playwright',str(tmp_path)])
 monkeypatch.setattr(execute,'validated',lambda _: {'playwright_path':str(tmp_path)})
 monkeypatch.setattr(execute,'approved',lambda *a:None);monkeypatch.setattr(execute,'current',lambda *a:None)
 def failed(*a):raise NotReady('local_docker_engine_unavailable')
 monkeypatch.setattr(execute,'runtime_check',failed)
 def forbidden(*a):raise AssertionError('Not-ready stack consumed the attempt')
 monkeypatch.setattr(execute,'claim',forbidden)
 with pytest.raises(NotReady):execute.main()
 assert not (canonical/'attempt.json').exists()

@pytest.mark.parametrize('status',[401,403,500,502,503])
def test_sdk_receives_original_failed_http_but_next_dispatch_is_forbidden(status,monkeypatch):
 import asyncio
 env={'id':'public-env','base_url':'https://public-dify.invalid'}
 boundary=Boundary(env,{'base_url':'https://public-model.invalid'}, {},{'phase':'reconnect'},[]);calls=[]
 class Body(httpx.AsyncByteStream):
  async def __aiter__(self):yield b'<html>sk-private-response</html>'
 async def forward(request):calls.append(1);return httpx.Response(status,stream=Body())
 async def transport(self,request):return await dispatch(boundary,forward,request)
 monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',transport)
 async def run():
  client=DifyClient(env,None)
  with pytest.raises(DifyError) as exc:await client.login('public@example.invalid','PUBLIC_SYNTHETIC_ONLY')
  assert exc.value.code==('login_service_error' if status>=500 else 'login_rejected') and exc.value.http_status==status
  assert 'sk-private' not in str(exc.value) and boundary.halted
  with pytest.raises(RuntimeError):await client.login('public@example.invalid','PUBLIC_SYNTHETIC_ONLY')
 asyncio.run(run());assert calls==[1] and boundary.counts['login']==1
