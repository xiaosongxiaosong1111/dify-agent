import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

import pytest
from test_api import client,create,forbid_api_external_calls
from test_material_parsing import upload
from app import main


def endpoint(task, material, download=False, revision=None):
    return f"/api/tasks/{task['id']}/materials/{material['id']}/original"+('/download' if download else '')+f"?revision={task['revision'] if revision is None else revision}"


def source(task,material):
    return main.DATA_ROOT/task['id']/'materials'/(material['id']+Path(material['name']).suffix.lower())


@pytest.mark.parametrize('name,raw', [('same.txt',b'first\r\nsecond\r\n'),('原图.PNG',b'not-a-decoded-image\x00\xff'),('bad.json',b'{ invalid }'),('noextension',b'original'),('bom.md',b'\xef\xbb\xbforiginal')])
def test_exact_original_bytes_download_even_when_not_parsed(client,name,raw):
    task,material=upload(client,create(client),name,raw);before=copy.deepcopy(task)
    check=client.get(endpoint(task,material));assert check.status_code==200,check.text
    value=check.json();assert value['state']=='verified' and value['downloadable'] is True
    assert value['sha256_matches'] is True and value['size_matches'] is True
    assert value['observed_sha256']==hashlib.sha256(raw).hexdigest() and value['observed_size']==len(raw)
    assert value['material_id']==material['id'] and value['revision']==task['revision']
    response=client.get(endpoint(task,material,True));assert response.status_code==200,response.text
    assert response.content==raw and response.headers['content-type']=='application/octet-stream'
    assert response.headers['x-content-type-options']=='nosniff' and response.headers['cache-control']=='no-store'
    assert response.headers['x-sierra-source-sha256']==hashlib.sha256(raw).hexdigest()
    assert 'attachment;' in response.headers['content-disposition']
    assert main.get_task(task['id'])==before


def test_same_name_and_other_task_never_share_or_overwrite_source(client):
    task= create(client);task,a=upload(client,task,'rules.txt',b'first');task,b=upload(client,task,'rules.txt',b'second')
    other,c=upload(client,create(client),'rules.txt',b'other')
    assert client.get(endpoint(task,a,True)).content==b'first'
    assert client.get(endpoint(task,b,True)).content==b'second'
    assert client.get(endpoint(other,c,True)).content==b'other'
    assert client.get(endpoint(other,a,True)).status_code==404
    assert client.get(endpoint(other,a)).status_code==404


@pytest.mark.parametrize('change',['missing','modified','oversized','old_digest','wrong_size'])
def test_unknown_or_changed_source_cannot_be_downloaded_or_reconstructed(client,change):
    task,material=upload(client,create(client),'original.txt',b'original')
    path=source(task,material)
    if change=='missing':path.unlink()
    elif change=='modified':path.write_bytes(b'local modified')
    elif change=='oversized':
        with path.open('wb') as handle:handle.truncate(20*1024*1024+1)
    elif change=='old_digest':material.pop('sha256');task['materials'][-1]=material;main.save_task(task)
    else:material['size']=999;task['materials'][-1]=material;main.save_task(task)
    before=copy.deepcopy(main.get_task(task['id']))
    response=client.get(endpoint(task,material));assert response.status_code==200,response.text
    value=response.json();assert value['downloadable'] is False and value['state']!='verified'
    assert client.get(endpoint(task,material,True)).status_code in (409,422)
    assert main.get_task(task['id'])==before
    if change=='modified':
        assert value['state']=='changed' and value['sha256_matches'] is False
        assert value['observed_sha256']==hashlib.sha256(b'local modified').hexdigest()
        assert 'local modified' not in response.text
    if change=='missing':assert not path.exists()


def test_download_rechecks_after_successful_probe_and_binds_revision(client):
    task,material=upload(client,create(client),'original.txt',b'original')
    assert client.get(endpoint(task,material)).json()['downloadable']
    source(task,material).write_bytes(b'changed after preview')
    assert client.get(endpoint(task,material,True)).status_code==409
    assert client.get(endpoint(task,material,revision=task['revision']-1)).status_code==409


def test_deleted_material_does_not_expose_retained_audit_file(client):
    task,material=upload(client,create(client),'original.txt',b'original')
    response=client.delete(f"/api/tasks/{task['id']}/materials/{material['id']}", params={'revision':task['revision']})
    task=response.json();assert source(task,material).exists()
    assert client.get(endpoint(task,material)).status_code==404
    assert client.get(endpoint(task,material,True)).status_code==404


@pytest.mark.parametrize('field,value',[('id','../other'),('name','bad.txt:stream'),('id','00000000-0000-0000-0000-000000000000/else')])
def test_unverifiable_metadata_paths_are_refused_before_source_read(client,monkeypatch,field,value):
    task,material=upload(client,create(client),'original.txt',b'original')
    material[field]=value;task['materials'][-1]=material;main.save_task(task)
    # Slash IDs do not route; other unsafe metadata is refused by source inspection.
    if '/' in material['id']:
        from app.material_original import inspect_original
        assert inspect_original(main,task['id'],material)['state']=='unavailable'
    else:
        assert client.get(endpoint(task,material)).json()['downloadable'] is False


def test_download_filename_is_encoded_attachment_and_body_is_not_reopened(client):
    raw=b'<html><script>untrusted()</script></html>'
    task,material=upload(client,create(client),'带空格 原文.html',raw)
    response=client.get(endpoint(task,material,True))
    assert response.status_code==200 and response.content==raw
    assert unquote(response.headers['content-disposition']).endswith('带空格 原文.html')
    assert response.headers['content-security-policy']=='sandbox'


def test_internal_source_symlink_cannot_borrow_other_material_identity(client,monkeypatch):
    task,material=upload(client,create(client),'original.txt',b'original')
    path=source(task,material);original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda self: self==path or original(self))
    value=client.get(endpoint(task,material)).json()
    assert value['state']=='unavailable' and value['downloadable'] is False


def test_adopted_reference_keeps_original_yaml_bytes_in_download(client):
    from test_reference_dsl import approved,preview,adopt,content
    task=approved(client);raw=content(task).replace('\n','\r\n')
    assert preview(client,task,raw,filename='reference.YML').status_code==200
    task=adopt(client,task).json();material=task['materials'][-1]
    response=client.get(endpoint(task,material,True))
    assert response.status_code==200 and response.content==raw.encode()


def test_missing_size_is_explicit_unknown_but_digest_can_verify_original(client):
    task,material=upload(client,create(client),'original.txt',b'original');material.pop('size');task['materials'][-1]=material;main.save_task(task)
    value=client.get(endpoint(task,material)).json()
    assert value['state']=='verified' and value['size_matches'] is None
    assert value['recorded_size'] is None and value['observed_size']==8


def test_source_permission_error_is_bounded_and_does_not_leak_host_path(client,monkeypatch):
    task,material=upload(client,create(client),'original.txt',b'original');path=source(task,material)
    original=Path.open
    def denied(self,*args,**kwargs):
        if self==path:raise PermissionError('private-host-path-and-data')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',denied)
    response=client.get(endpoint(task,material));assert response.status_code==200
    assert response.json()['state']=='unavailable' and 'private-host' not in response.text
    assert client.get(endpoint(task,material,True)).status_code==422


def test_metadata_and_revision_change_while_source_is_read_discards_result(client,monkeypatch):
    from app import material_original
    task,material=upload(client,create(client),'original.txt',b'original')
    original=material_original.inspect_original
    def changed(host,item_id,value):
        result=original(host,item_id,value)
        current=main.get_task(item_id);current['revision']+=1;main.save_task(current)
        return result
    monkeypatch.setattr(material_original,'inspect_original',changed)
    response=client.get(endpoint(task,material,True));assert response.status_code==409
    assert response.content!=b'original'
