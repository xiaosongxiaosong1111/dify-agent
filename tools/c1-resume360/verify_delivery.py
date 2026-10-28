"""Validate both same-Task downloads and the single core graph edit; no external action."""
import copy,hashlib,json,zipfile
from guard import require,canonical,digest,resource_graph

def verify(output,fixture,task_id,environment_id,apps):
 from app.dsl_roundtrip import parse
 values=[]
 for name in ('original','modified'):
  with zipfile.ZipFile(output/(name+'.zip')) as archive:
   manifest=json.loads(archive.read('manifest.json'));require(manifest['task_id']==task_id and manifest['environment_id']==environment_id and manifest['app_id'] in apps,'Wrong delivery source')
   require(all(manifest[k] is False for k in ('business_verified','platform_checked','network_requested')),'Local bundle verification markers changed')
   require(set(archive.namelist())==set(manifest['files'])|{'manifest.json'} and len(archive.namelist())==4,'Incomplete/duplicate archive')
   for path,meta in manifest['files'].items():
    raw=archive.read(path);require(len(raw)==meta['bytes'] and hashlib.sha256(raw).hexdigest()==meta['sha256'],'Archive file hash mismatch')
   paths=[p for p in manifest['files'] if p.endswith('.yaml')];require(len(paths)==1,'DSL entry missing');graph=resource_graph(parse(archive.read(paths[0]).decode('utf-8'),'workflow'),fixture,name)
   require(digest(graph)==apps[manifest['app_id']]['graph_digest'],'Delivered graph differs from approved imported graph');values.append((manifest,graph))
 first,last=values;require(first[0]['revision']<last[0]['revision'] and first[0]['app_id']!=last[0]['app_id'],'Missing independent second revision/App')
 expected=copy.deepcopy(first[1]);nodes=[n for n in expected['nodes'] if n['data']['type']=='template-transform'];require(len(nodes)==1,'Expected one no-hit template');nodes[0]['data']['template']=fixture['changed_fallback'];require(canonical(expected)==canonical(last[1]),'Other core graph content changed')
 proof={'state':'passed','same_task':True,'original_revision':first[0]['revision'],'modified_revision':last[0]['revision'],'file_hashes_verified':True,'only_core_graph_change':'no_hit_template.data.template','platform_checked':False,'business_verified':False}
 (output/'delivery-proof.json').write_text(json.dumps(proof,indent=2),'utf-8');return proof
