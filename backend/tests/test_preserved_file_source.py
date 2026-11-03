"""Preserved DSL build reads its own bounded file, not a matching foreign YAML."""
import copy
import pytest
from fastapi.testclient import TestClient
from test_api import client, forbid_api_external_calls
from test_dsl_roundtrip import prepared, capture, apply, changed
from app import main


def merged(client):
    task, root = prepared(client)
    task = capture(client, task, changed(root))
    response, _ = apply(client, task)
    assert response.status_code == 200, response.text
    task = response.json()
    for kind in ('requirements', 'configuration'):
        response = client.post(f"/api/tasks/{task['id']}/confirm", json={'revision':task['revision'],'kind':kind})
        assert response.status_code == 200, response.text
        task = response.json()
    path = main.DATA_ROOT / task['id'] / task['dsl_overlay']['filename']
    return task, path


@pytest.mark.parametrize('location', ['absolute','parent','foreign_task','file_link'])
def test_equal_semantics_cannot_authorize_a_foreign_preserved_source(client, tmp_path, location):
    task, original = merged(client)
    target = tmp_path / 'PRIVATE_SOURCE.yaml'
    if location == 'parent':target = main.DATA_ROOT / 'PRIVATE_SOURCE.yaml'
    if location == 'foreign_task':
        target = main.DATA_ROOT / 'other-task' / 'PRIVATE_SOURCE.yaml'
        target.parent.mkdir()
    target.write_bytes(original.read_bytes() + b'\n# PRIVATE_SOURCE_SENTINEL\n')
    if location == 'file_link':
        original.unlink()
        original.symlink_to(target)
    else:
        task['dsl_overlay']['filename'] = str(target) if location=='absolute' else ('../' + target.relative_to(main.DATA_ROOT).as_posix())
        main.store.put('task',task['id'],task)
    before = copy.deepcopy(main.get_task(task['id']))
    response = client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code == 422, response.text
    assert 'PRIVATE_SOURCE' not in response.text
    assert main.get_task(task['id']) == before
    assert target.read_bytes().endswith(b'# PRIVATE_SOURCE_SENTINEL\n')
    assert not (main.DATA_ROOT/task['id']/f"artifact-r{task['revision']}.yaml").exists()


@pytest.mark.parametrize('filename', [None, [], {}, '', 'PRIVATE_MISSING.yaml'])
def test_unreadable_identity_has_safe_error_and_no_new_artifact(client, filename):
    task, _ = merged(client)
    task['dsl_overlay']['filename'] = filename
    main.store.put('task',task['id'],task)
    before=copy.deepcopy(task)
    with TestClient(main.app,raise_server_exceptions=False) as safe:
        response=safe.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code == 422, response.text
    assert 'PRIVATE_MISSING' not in response.text
    assert main.get_task(task['id']) == before


@pytest.mark.parametrize('fault', ['empty','oversize','encoding','semantic_change'])
def test_invalid_preserved_bytes_do_not_replace_the_last_artifact_or_confirmation(client, fault):
    task, path = merged(client)
    raw=path.read_bytes()
    if fault=='empty':raw=b''
    elif fault=='oversize':raw+=b'\n#'+b'x'*2_000_001
    elif fault=='encoding':raw+=b'\n# PRIVATE_ENCODING_\xff'
    else:raw=raw.replace(b'strip().upper()',b'strip().lower()')
    path.write_bytes(raw)
    before=copy.deepcopy(main.get_task(task['id']))
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code==422, response.text
    assert 'PRIVATE_ENCODING' not in response.text
    assert main.get_task(task['id'])==before and path.read_bytes()==raw


@pytest.mark.parametrize('newline', [b'\n',b'\r\n'])
def test_same_task_semantics_and_public_comments_keep_existing_preservation_contract(client, newline):
    task,path=merged(client)
    path.write_bytes((path.read_bytes()+b'\n# PUBLIC_LEGITIMATE_COMMENT\n').replace(b'\n',newline))
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code==200,response.text
    assert 'PUBLIC_LEGITIMATE_COMMENT' in main.artifact_text(response.json())
    assert response.json()['requirements_confirmed'] and response.json()['configuration_confirmed']


def test_coverage_does_not_read_foreign_equal_graph_to_offer_source_evidence(client, tmp_path):
    from app.coverage import final_root, evidence
    task,path=merged(client)
    target=tmp_path/'PRIVATE_COVERAGE.yaml'
    target.write_bytes(path.read_bytes())
    task['dsl_overlay']['filename']=str(target)
    root,error=final_root(task)
    assert root is None and error and 'PRIVATE' not in error
    assert not any(key.startswith('node:') for key in evidence(task))


def test_preserved_reader_does_not_read_past_the_public_dsl_limit(client, monkeypatch):
    from pathlib import Path
    from app.dsl_roundtrip import MAX_BYTES
    task,path=merged(client)
    path.write_bytes(path.read_bytes()+b'\n#'+b'x'*(MAX_BYTES+100))
    real_open=Path.open;requested=[]
    class Bounded:
        def __enter__(self):return self
        def __exit__(self,*args):self.source.close()
        def __init__(self,source):self.source=source
        def read(self,size=-1):
            requested.append(size)
            assert 0 < size <= MAX_BYTES+1, 'oversize DSL was read without a bound'
            return self.source.read(size)
    def opened(candidate,*args,**kwargs):
        source=real_open(candidate,*args,**kwargs)
        return Bounded(source) if candidate==path else source
    monkeypatch.setattr(Path,'open',opened)
    response=client.post(f"/api/tasks/{task['id']}/build",json={'revision':task['revision']})
    assert response.status_code==422 and requested
