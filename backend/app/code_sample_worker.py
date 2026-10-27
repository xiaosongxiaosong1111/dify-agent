"""Trusted container-only suffix; appended to policy source, never imported by the host."""
import builtins,contextlib,signal,sys,types,os
class _TimedOut(BaseException):pass
class _OutputLimit(BaseException):pass
class _Sink:
 def __init__(self):self.size=0
 def write(self,text):
  self.size+=len(text.encode('utf-8'))
  if self.size>4096:raise _OutputLimit()
  return len(text)
 def flush(self):pass

def _import(name,globals=None,locals=None,fromlist=(),level=0):
 if level or name not in MODULES:raise ImportError('unsupported')
 source=json if name=='json' else math
 return types.SimpleNamespace(**{key:getattr(source,key) for key in MODULES[name]})

def _run():
 if sys.platform!='linux' or os.getuid()!=65534 or os.environ.get('SIERRA_CODE_WORKER')!='pure-python-v1':return {'status':'protocol_error','error_category':'isolation_marker_missing'}
 import resource
 try:
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(4,4))
  raw=sys.stdin.buffer.read(INPUT_BYTES+2*CODE_BYTES+8193)
  if len(raw)>INPUT_BYTES+2*CODE_BYTES+8192:raise ValueError('payload_limit')
  payload=json.loads(raw);code=payload['code'];inputs=payload['inputs'];validate_code(code);json_value(inputs)
  def timeout(*_):raise _TimedOut()
  signal.signal(signal.SIGALRM,timeout);signal.alarm(3)
  safe={key:getattr(builtins,key) for key in BUILTINS};safe['__import__']=_import
  namespace={'__builtins__':safe,'__name__':'sierra_local_sample'}
  try:
   with contextlib.redirect_stdout(_Sink()),contextlib.redirect_stderr(_Sink()):
    exec(compile(code,'<local-sample>','exec'),namespace,namespace);value=namespace['main'](**inputs)
   try:json_value(value);text=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
   except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):return {'status':'invalid_output','error_category':'non_json_output'}
   if len(text.encode('utf-8'))>OUTPUT_BYTES:return {'status':'output_limit','error_category':'output_limit'}
   return {'status':'returned','output_json':text}
  except _TimedOut:return {'status':'timeout','error_category':'timeout'}
  except _OutputLimit:return {'status':'output_limit','error_category':'output_limit'}
  except Exception as exc:return {'status':'code_error','error_category':type(exc).__name__[:64]}
  finally:signal.alarm(0)
 except Exception:return {'status':'protocol_error','error_category':'protocol_error'}

if __name__=='__main__':
 _result=_run();sys.stdout.write(json.dumps(_result,ensure_ascii=False,allow_nan=False));sys.stdout.flush()
