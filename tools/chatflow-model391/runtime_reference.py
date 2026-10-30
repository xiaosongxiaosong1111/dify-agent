import base64,json,subprocess,urllib.request
from pathlib import Path
from common import PROJECT,sha,require
def load(path):return json.loads(Path(path).read_text(encoding="utf-8"))

def runtime_check(plan):
    require(sha(PROJECT/'runtime-process.ps1')==plan['runtime_process_sha256'],'Runtime helper changed')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**kw):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    with opener.open('http://127.0.0.1:8765/api/runtime',timeout=10) as r:runtime=json.load(r)
    require(runtime.get('build_id')==plan['runtime_build'] and runtime.get('version')=='0.363.0','Managed runtime changed')
    folder=PROJECT/'.runtime/snapshots'/plan['runtime_build'];require(sha(folder/'runtime-manifest.json')==plan['runtime_manifest_sha256'],'Runtime manifest changed')
    for name,value in load(folder/'runtime-manifest.json')['files'].items():
        source=(PROJECT/name).resolve();saved=(folder/name).resolve();require(source.is_relative_to(PROJECT) and saved.is_relative_to(folder) and sha(source)==value and sha(saved)==value,'Source/snapshot mismatch')
    pid=int((PROJECT/'data/server.pid').read_text('ascii').strip());require(pid>0,'PID unavailable')
    script="$ErrorActionPreference='Stop'; Set-Location -LiteralPath 'E:\\workSpace\\dify-agent'; . .\\runtime-process.ps1; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = "+str(pid)+"'; if(-not $p -or -not (Test-SierraCommandLine ([string]$p.CommandLine) 'E:\\workSpace\\dify-agent')){throw 'Not owned'}; @{executable=$p.ExecutablePath;command=$p.CommandLine} | ConvertTo-Json -Compress"
    encoded=base64.b64encode(script.encode('utf-16-le')).decode()
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));require(result.returncode==0,'PID ownership unavailable')
    process=json.loads(result.stdout.decode('utf-8-sig'));require(Path(process['executable']).resolve()==PROJECT/'.venv/Scripts/python.exe' and str(folder/'backend').lower() in process['command'].lower(),'Wrong executable/snapshot')
    return {'verified_pid':pid,'runtime_build':runtime['build_id'],'source_files_matched':runtime['file_count']}

