import hashlib,json,copy
from pathlib import Path
import pytest
from test_reference_dsl import client,approved,preview,adopt,content,forbid_reference_external_calls
from app import main
from app.material_sources import read_source


@pytest.mark.parametrize('filename',['reference.yaml','reference.yml','reference.json','reference.YML','reference','参考流程.yaml'])
@pytest.mark.parametrize('newlines',['lf','crlf'])
def test_adopted_source_matches_original_bytes_name_and_digest(client,filename,newlines):
    task=approved(client);original=content(task)
    if filename.endswith('.json'):
        import yaml
        original=json.dumps(yaml.safe_load(original),ensure_ascii=False,indent=2)+'\n'
    if newlines=='crlf':original=original.replace('\n','\r\n')
    assert preview(client,task,original,filename=filename).status_code==200
    response=adopt(client,task);assert response.status_code==200,response.text
    saved=response.json();m=saved['materials'][-1];path=main.DATA_ROOT/task['id']/'materials'/(m['id']+Path(filename).suffix.lower())
    assert path.exists() and path.read_bytes()==original.encode('utf-8')
    assert m['sha256']==hashlib.sha256(original.encode('utf-8')).hexdigest()
    assert read_source(main,task['id'],m)==original.encode('utf-8')
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']


def test_source_change_is_rejected_and_old_source_is_not_silently_rewritten(client):
    task=approved(client);original=content(task);preview(client,task,original,filename='reference.yml');saved=adopt(client,task).json();m=saved['materials'][-1]
    source=main.DATA_ROOT/task['id']/'materials'/(m['id']+'.yml')
    assert source.exists()
    source.write_bytes(original.encode()+b'\n# local change')
    with pytest.raises(main.HTTPException) as exc:read_source(main,task['id'],m)
    assert exc.value.status_code==409 and source.read_bytes().endswith(b'# local change')
    # Old wrong-extension files must not be guessed or migrated on a read.
    source.unlink();legacy=source.with_suffix('.yaml');legacy.write_bytes(original.encode());before=copy.deepcopy(main.get_task(task['id']))
    with pytest.raises(main.HTTPException) as exc:read_source(main,task['id'],m)
    assert exc.value.status_code==422 and legacy.read_bytes()==original.encode() and main.get_task(task['id'])==before


@pytest.mark.parametrize('filename',['reference.yaml:alternate','reference.yaml;$bad'])
def test_unsafe_suffix_cannot_be_used_as_a_filesystem_destination(client,filename):
    task=approved(client);assert preview(client,task,filename=filename).status_code==200
    before=copy.deepcopy(main.get_task(task['id']));response=adopt(client,task)
    assert response.status_code==422 and main.get_task(task['id'])==before
    assert not list((main.DATA_ROOT/task['id']).glob('materials/*'))
