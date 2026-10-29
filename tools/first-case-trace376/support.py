import base64,subprocess,urllib.request
"""Local immutable-source utilities; never decrypt credentials."""
import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
LIMITS={'reads':10,'login':1,'model':0,'new_tasks':0,'import':0,'publish':0,'key':0,'run':0}

def require(value,message):
    if not value:raise RuntimeError(message)

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):
 def pairs(rows):
  value={}
  for k,v in rows:require(k not in value,'Duplicate JSON key');value[k]=v
  return value
 raw=Path(path).read_bytes();require(len(raw)<=10_000_000,'Oversize JSON')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'Non-finite JSON'))
def uuid(value):
    from uuid import UUID
    try:return isinstance(value,str) and str(UUID(value))==value
    except (ValueError,AttributeError):return False

class ReadOnly:
    def __init__(self,root):self.root=Path(root)
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect((self.root/'flowcraft.sqlite3').as_uri()+'?mode=ro',uri=True)
        try:yield db
        finally:db.close()
    def get(self,kind,item):
        with self.connect() as db:row=db.execute('SELECT value FROM objects WHERE kind=? AND id=?',(kind,item)).fetchone()
        return json.loads(row[0]) if row else None
    def list(self,kind):
        with self.connect() as db:return [json.loads(row[0]) for row in db.execute('SELECT value FROM objects WHERE kind=?',(kind,))]

def capture(store):
    with store.connect() as db:
        objects={k+':'+i:digest(json.loads(v)) for k,i,v in db.execute('SELECT kind,id,value FROM objects')}
        secrets={i:hashlib.sha256(bytes(v)).hexdigest() for i,v in db.execute('SELECT id,value FROM secrets')}
    files={}
    for path in store.root.rglob('*'):
        if not path.is_file() or path.parent==store.root and path.name in {'flowcraft.sqlite3','flowcraft.sqlite3-shm','flowcraft.sqlite3-wal','server.pid','server.out.log','server.err.log'}:continue
        require(path.resolve().is_relative_to(store.root.resolve()),'Asset link outside data root')
        files[str(path.relative_to(store.root))]=sha(path)
    return {'objects':objects,'secrets':secrets,'files':files}

def known_apps(store):
    result=set()
    for kind in ('environment','task','app_runtime_credential','workflow_publication','app_runtime_key_creation','runtime_key_previous_binding'):
        for row in store.list(kind):
            for key in ('app_id','dify_app_id','service_app_id'):
                if uuid(row.get(key)):result.add(row[key])
            for run in row.get('runs',[]):
                if uuid(run.get('app_id')):result.add(run['app_id'])
                value=run.get('result')
                if isinstance(value,dict) and uuid(value.get('app_id')):result.add(value['app_id'])
    return result


def runtime_check(plan):
    require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime helper changed')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime.get('build_id')==plan['runtime_build'] and runtime.get('version')=='0.356.0','Managed runtime changed')
    folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];require(sha(folder/'runtime-manifest.json')==plan['runtime_manifest_sha256'],'Runtime manifest changed')
    for name,value in load(folder/'runtime-manifest.json')['files'].items():
        source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT) and saved.is_relative_to(folder) and sha(source)==value and sha(saved)==value,'Source/snapshot mismatch')
    pid=int((PROJECT/'data/server.pid').read_text('ascii').strip());require(pid>0,'PID unavailable')
    script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'Not owned'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
    encoded=base64.b64encode(script.encode('utf-16-le')).decode()
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'PID ownership unavailable')
    process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==PROJECT/'.venv/Scripts/python.exe' and str(folder/'backend').lower() in process['command'].lower(),'Wrong executable/snapshot')
    return {'verified_pid':pid,'runtime_build':runtime['build_id'],'source_files_matched':runtime['file_count']}
