"""Check two downloaded static revisions, exact bytes and the single intended graph edit."""
import copy,hashlib,json,zipfile
import yaml


def verify(output,fixture):
 values=[]
 for name in ('original','modified'):
  with zipfile.ZipFile(output/(name+'.zip')) as archive:
   manifest=json.loads(archive.read('manifest.json'))
   assert manifest['business_verified'] is False and manifest['platform_checked'] is False and manifest['network_requested'] is False
   assert manifest['app_id'] is None and manifest['environment_id'] is None
   assert set(manifest['files'])=={f'dify-workflow-r{manifest["revision"]}.yaml',f'report-r{manifest["revision"]}.md','README.md'}
   assert len(archive.namelist())==4 and set(archive.namelist())==set(manifest['files'])|{'manifest.json'}
   for path,record in manifest['files'].items():
    raw=archive.read(path);assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256']
    assert b'NOT_A_REAL_KEY' not in raw
   paths=[p for p in manifest['files'] if p.endswith('.yaml')];assert len(paths)==1
   document=yaml.safe_load(archive.read(paths[0]));values.append((manifest,document['workflow']['graph']))
 old,new=values;assert old[0]['task_id']==new[0]['task_id'] and old[0]['revision']<new[0]['revision']
 expected=copy.deepcopy(old[1]);node=next(n for n in expected['nodes'] if n['id']=='answer_nohit')
 assert node['data']['template']==fixture['plan']['nodes'][4]['config']['template']
 node['data']['template']=fixture['changed_fallback'];assert expected==new[1],'Unrelated nodes, connections or model fields changed'
 proof={'state':'passed','same_task':True,'original_revision':old[0]['revision'],'modified_revision':new[0]['revision'],'hashes_verified':True,'only_graph_change':'answer_nohit.data.template','platform_checked':False,'business_verified':False}
 (output/'delivery-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),'utf-8');return proof
