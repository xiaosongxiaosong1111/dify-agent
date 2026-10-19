import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.runtime_assets import SnapshotAssets


def setup(tmp_path):
    current=tmp_path/'current';current.mkdir();snapshots=tmp_path/'snapshots';snapshots.mkdir();old=snapshots/'0.79.0-old';assets=old/'frontend/dist/assets';assets.mkdir(parents=True)
    content=b'old lazy module';name='HttpNodePanel-Old12345.js';(assets/name).write_bytes(content)
    manifest={'schema_version':1,'build_id':old.name,'files':{'frontend/dist/assets/'+name:hashlib.sha256(content).hexdigest()}}
    (old/'runtime-manifest.json').write_text(json.dumps(manifest),encoding='utf-8');app=FastAPI();app.mount('/assets',SnapshotAssets(current,snapshots))
    return TestClient(app),current,old,name,manifest


def test_cached_page_lazy_asset_stays_available_after_switch(tmp_path):
    client,current,old,name,_=setup(tmp_path)
    response=client.get('/assets/'+name);assert response.status_code==200 and response.content==b'old lazy module'
    assert response.headers['x-sierra-asset-source']=='retained-snapshot' and 'immutable' in response.headers['cache-control']
    assert client.head('/assets/'+name).status_code==200
    (current/name).write_bytes(b'current module');response=client.get('/assets/'+name)
    assert response.content==b'current module' and 'x-sierra-asset-source' not in response.headers


@pytest.mark.parametrize('path',['runtime-manifest.json','index.html','.credential-key','data-Old12345.json','../runtime-manifest.json'])
def test_only_named_hashed_js_css_are_eligible(tmp_path,path):
    client,_,_,_,_=setup(tmp_path);assert client.get('/assets/'+path).status_code==404


def test_bad_or_unlisted_file_cannot_be_served(tmp_path):
    client,_,old,name,manifest=setup(tmp_path);target=old/'frontend/dist/assets'/name;target.write_text('changed',encoding='utf-8')
    assert client.get('/assets/'+name).status_code==404
    target.write_bytes(b'old lazy module');manifest['files']={};(old/'runtime-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    assert client.get('/assets/'+name).status_code==404


def test_incomplete_snapshot_does_not_claim_retained_assets(tmp_path):
    client,_,old,name,_=setup(tmp_path);(old/'runtime-manifest.json').unlink()
    assert client.get('/assets/'+name).status_code==404
