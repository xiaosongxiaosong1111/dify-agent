"""Disposable public-case state copy with fake encrypted credentials. Never called live."""
import copy,shutil
from pathlib import Path
from support import ReadOnly
from guard import require

PROJECT=Path(__file__).resolve().parents[2]
TID='aa827c91-b683-4a34-9e7f-fa0789f5c252'
EID='202bfb35-2f92-47c1-bc1b-eac32082181d'
PID='9513f594-c256-46b7-882a-35d9871bf9d0'


def prepare(host,TestClient,fixture):
    source=ReadOnly(PROJECT/'data');task=source.get('task',TID)
    require(task['revision']==13 and not task.get('materials'),'Only the existing public saved-case fixture is supported')
    environment=copy.deepcopy(source.get('environment',EID));environment['base_url']='https://public-dify.invalid'
    environment['console_login_binding']={'base_url':environment['base_url'],'version':environment['version'],'workspace_id':environment['console_workspace_id']}
    provider=copy.deepcopy(source.get('provider',PID))
    host.store.put_with_secrets('environment',EID,environment,{'console_token':'PUBLIC_OLD_CONSOLE_TOKEN','csrf_token':'PUBLIC_OLD_CSRF_TOKEN','service_api_key':'app-PUBLIC_OLD_RUNTIME_KEY','console_login_email':'public@example.invalid','console_login_password':'PUBLIC_SYNTHETIC_ONLY'})
    host.store.put_with_secrets('provider',PID,provider,{'api_key':'PUBLIC_SYNTHETIC_ONLY'})
    with TestClient(host.app) as api:
        for i in range(17):require(api.post('/api/tasks',json={'name':'公开保护Task'+str(i),'app_type':'workflow','environment_id':EID}).status_code==201,'Public fixture Task failed')
    for kind in ('task','task_budget','execution_limits'):
        host.store.put(kind,TID,copy.deepcopy(source.get(kind,TID)))
    # Only this public Task's static artifacts; never copy the data-root key or credential DB.
    origin=PROJECT/'data'/TID;destination=host.store.root/TID
    if origin.exists():
        require(origin.resolve()==origin and destination.resolve().is_relative_to(host.store.root.resolve()),'Fixture artifact location invalid')
        for file in origin.rglob('*'):require(file.resolve().is_relative_to(origin.resolve()),'Fixture artifact link outside Task')
        shutil.copytree(origin,destination)
    return environment,provider,TID
