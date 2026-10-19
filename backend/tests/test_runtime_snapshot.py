import importlib.util,json
from pathlib import Path
import pytest
from test_api import client,approved
from app import main

spec=importlib.util.spec_from_file_location('prepare_runtime',Path(__file__).resolve().parents[2]/'tools'/'prepare_runtime.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(project):
    for folder in ('backend/app','frontend/dist/assets','docs','data','work','backend/tests'):(project/folder).mkdir(parents=True,exist_ok=True)
    (project/'backend/app/main.py').write_text('app = FastAPI(version="1.2.3")\n',encoding='utf-8')
    (project/'frontend/dist/index.html').write_text('assets/old.js',encoding='utf-8');(project/'frontend/dist/assets/old.js').write_text('old code',encoding='utf-8')
    for name in module.CONTRACTS:(project/'docs'/name).write_text('frozen contract',encoding='utf-8')
    (project/'data/.credential-key').write_text('test-only-do-not-copy',encoding='utf-8');(project/'data/tasks.db').write_text('saved user task fixture',encoding='utf-8')
    (project/'frontend/dist/.env').write_text('test-only-private',encoding='utf-8');(project/'work/example.py').write_text('not runtime',encoding='utf-8')


def test_snapshot_allowlist_keeps_tasks_credentials_and_work_outside(tmp_path):
    fixture(tmp_path);value=module.prepare(tmp_path);root=Path(value['runtime_root']);manifest=json.loads((root/'runtime-manifest.json').read_text(encoding='utf-8'))
    assert not (root/'data').exists() and not (root/'work').exists() and not (root/'frontend/dist/.env').exists()
    assert value['data_path']==str(tmp_path/'data') and manifest['shared_data_copied'] is False
    assert (tmp_path/'data/.credential-key').read_text()=='test-only-do-not-copy'
    assert value['file_count']==len(module.CONTRACTS)+3


def test_code_contract_and_old_lazy_assets_are_frozen_across_new_build(tmp_path):
    fixture(tmp_path);first=module.prepare(tmp_path);old=Path(first['runtime_root'])
    (tmp_path/'backend/app/main.py').write_text('app = FastAPI(version="1.2.3")\nupdated=True\n',encoding='utf-8')
    (tmp_path/'docs/case-model-contract.md').write_text('new scope',encoding='utf-8')
    (tmp_path/'frontend/dist/assets/old.js').unlink();(tmp_path/'frontend/dist/assets/new.js').write_text('new code',encoding='utf-8')
    second=module.prepare(tmp_path);assert second['build_id']!=first['build_id']
    assert (old/'frontend/dist/assets/old.js').read_text()=='old code' and (old/'docs/case-model-contract.md').read_text()=='frozen contract'
    assert 'updated' not in (old/'backend/app/main.py').read_text()
    assert (tmp_path/'data/tasks.db').read_text()=='saved user task fixture'


def test_reuse_verifies_files_and_refuses_modified_or_incomplete_snapshot(tmp_path):
    fixture(tmp_path);first=module.prepare(tmp_path);assert module.prepare(tmp_path)==first
    root=Path(first['runtime_root']);(root/'backend/app/main.py').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='快照文件变化'):module.prepare(tmp_path)
    assert (root/'backend/app/main.py').read_text()=='changed'
    (root/'runtime-manifest.json').unlink()
    with pytest.raises(ValueError,match='不完整'):module.prepare(tmp_path)


def test_missing_contract_or_bundle_blocks_snapshot_instead_of_partial_start(tmp_path):
    fixture(tmp_path);(tmp_path/'docs/intake-model-contract.md').unlink()
    with pytest.raises(ValueError,match='模型契约缺失'):module.prepare(tmp_path)
    assert not (tmp_path/'.runtime/snapshots').exists()


def test_runtime_identity_read_does_not_expose_paths_or_touch_tasks(client,tmp_path,monkeypatch):
    saved=approved(client);before=main.get_task(saved['id']);root=tmp_path/'runtime';root.mkdir()
    monkeypatch.setattr(main,'PROJECT_ROOT',root)
    response=client.get('/api/runtime');assert response.status_code==200 and response.json()['mode']=='source_tree'
    (root/'runtime-manifest.json').write_text(json.dumps({'schema_version':1,'version':main.app.version,'build_id':'test-build','content_sha256':'a'*64,'files':{'backend/app/main.py':'b'*64}}),encoding='utf-8')
    value=client.get('/api/runtime').json();assert value['mode']=='snapshot' and value['build_id']=='test-build' and value['task_data_inside_snapshot'] is False
    assert not any(key in value for key in ('data_path','runtime_root','files','credentials'))
    assert main.get_task(saved['id'])==before


def test_runtime_identity_does_not_invent_build_for_bad_manifest(client,tmp_path,monkeypatch):
    (tmp_path/'runtime-manifest.json').write_text('{unfinished',encoding='utf-8');monkeypatch.setattr(main,'PROJECT_ROOT',tmp_path)
    assert client.get('/api/runtime').status_code==422
