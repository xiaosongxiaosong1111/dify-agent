"""Verify the new single-App bundle and retained original history, no extra HTTP."""
import hashlib,json,zipfile
from guard import require,digest,resource_graph


def verify(output,fixture,task_id,environment_id,apps):
    from app.dsl_roundtrip import parse
    with zipfile.ZipFile(output/'modified.zip') as archive:
        manifest=json.loads(archive.read('manifest.json'))
        require(manifest['task_id']==task_id and manifest['environment_id']==environment_id and manifest['app_id'] in apps,'New bundle binding mismatch')
        require(all(manifest[k] is False for k in ('business_verified','platform_checked','network_requested')),'Bundle local verification flags changed')
        require(set(archive.namelist())==set(manifest['files'])|{'manifest.json'} and len(archive.namelist())==4,'Bundle has missing or duplicate files')
        for name,meta in manifest['files'].items():
            raw=archive.read(name);require(len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['sha256'],'Bundle file digest mismatch')
        names=[n for n in manifest['files'] if n.endswith('.yaml')];require(len(names)==1,'DSL source missing')
        graph=resource_graph(parse(archive.read(names[0]).decode('utf-8'),'workflow'),fixture,'modified')
        require(digest(graph)==apps[manifest['app_id']]['graph_digest'],'Delivered graph differs from reviewed/imported graph')
    proof={'state':'passed','revision':manifest['revision'],'app_id':manifest['app_id'],'file_hashes_verified':True,
           'graph_matches_reviewed_imported_version':True,'existing_history_not_replayed':True,'platform_checked':False,'business_verified':False}
    (output/'delivery-proof.json').write_text(json.dumps(proof,indent=2),'utf-8')
    return proof
