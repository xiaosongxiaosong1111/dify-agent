"""Real multipart upload and downstream gates; no supplier or production calls."""
import hashlib
import json
import pytest
from test_api import client,create,approved,forbid_api_external_calls
from app import main
from app.conflicts import sources


def upload(client,task,name,raw):
    response=client.post(f"/api/tasks/{task['id']}/materials",files={'file':(name,raw,'application/octet-stream')})
    assert response.status_code==200,response.text
    return response.json(),response.json()['materials'][-1]


@pytest.mark.parametrize('name,raw,line,column',[
    ('broken.json',b'{\n "x": }\n',2,7),
    ('trailing.JSON',b'{} {}',1,4),
    ('constant.json',b'{"x": NaN}',1,7),
    ('infinity.json',b'{"x": -Infinity}',1,7),
    ('broken.yaml',b'a: [1,\n',2,1),
    ('anchor.yml',b'a: *missing\n',1,4),
    ('indent.yaml',b'a:\n\tb: 1\n',2,1),
    ('encoding.txt','公开\nabc'.encode()+b'\xff',2,4),
    ('bom.md',b'\xef\xbb\xbf'+'公开\nabc'.encode()+b'\xff',2,4),
])
def test_invalid_syntax_or_encoding_is_unread_with_location(client,name,raw,line,column):
    task=create(client);saved,material=upload(client,task,name,raw)
    assert material['status']=='needs_input' and material['text']==''
    assert f'第{line}行' in material['error'] and f'第{column}列' in material['error']
    path=main.DATA_ROOT/task['id']/'materials'/(material['id']+'.'+name.split('.')[-1].lower())
    assert path.read_bytes()==raw and material['sha256']==hashlib.sha256(raw).hexdigest()
    assert not saved['requirements_confirmed'] and not saved['configuration_confirmed']
    assert ('material',material['id']) not in sources(saved)


@pytest.mark.parametrize('name,text',[
    ('data.json','{ "精确":900719925474099312345, "decimal":0.12345678901234567890 }\r\n'),
    ('array.json','["中文",null,true,1]'),
    ('scalar.json','"原始文字"\n'),
    ('quoted.json','{"example":"NaN -Infinity", "escaped":"\\\"NaN"}'),
    ('bom.json','\ufeff{"a":1}'),
    ('data.yaml','a: &value [1, 2]\nb: *value\n'),
    ('data.yml','---\nfirst: 一\n---\nsecond: 二\n'),
    ('tags.yaml','a: !custom-reference {x: 1}\n'),
    ('notes.txt','{不是JSON}\n'),
    ('notes.md','```yaml\n不是: [完整\n```\n'),
    ('rows.csv','id,note\n1,"{不解析为JSON}"\n'),
])
def test_valid_sources_keep_original_text_and_never_reserialize(client,name,text):
    task=create(client);raw=text.encode();saved,m=upload(client,task,name,raw)
    assert m['status']=='parsed' and m['error']==''
    assert m['text']==text.removeprefix('\ufeff')
    assert m['reference_mode'] is None and ('material',m['id']) in sources(saved)


def test_bad_structured_material_blocks_confirmation_and_can_be_replaced_explicitly(client):
    task=approved(client);task,m=upload(client,task,'rules.json',b'{"private-marker": [}')
    assert m['status']=='needs_input' and 'private-marker' not in m['error']
    task=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'revision':task['revision'],'reference_mode':'borrow'}).json()
    assert client.post(f"/api/tasks/{task['id']}/confirm",json={'kind':'requirements','revision':task['revision']}).status_code==422
    reply=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json={'revision':task['revision'],'source_sha256':m['sha256'],'text':'用户提供的修正说明','coverage_note':'只解释业务要求，不是原JSON已修好','acknowledge_manual_source':True})
    assert reply.status_code==200,reply.text
    current=reply.json();amended=current['materials'][-1]
    assert amended['source_kind']=='user_supplied_text' and amended['source_file_parsed'] is False
    assert amended['original_parse_error']==m['error'] and amended['reference_mode']=='borrow'
    assert not current['requirements_confirmed'] and current['versions'][-1]['materials'][0]['status']=='needs_input'


def test_yaml_failure_exposes_position_not_error_context_or_file_text(client):
    task=create(client);_,m=upload(client,task,'private.yaml',b'private-marker: [\n')
    assert m['status']=='needs_input' and 'private-marker' not in m['error']
    assert '第2行' in m['error'] and '第1列' in m['error']


def test_size_limit_precedes_syntax_parse_and_deep_document_is_unread(client):
    task=create(client);_,m=upload(client,task,'large.json',b' '*100001+b'{')
    assert m['status']=='needs_input' and '10' in m['error'] and m['text']==''
    _,m=upload(client,task,'deep.json',b'['*2000+b'0'+b']'*1999)
    assert m['status']=='needs_input' and m['text']==''
