"""Compressed Word package limits before library loading; public local fixtures."""
import hashlib
import io
import zipfile

import pytest
from docx import Document
from docx.opc.packuri import PackURI
from docx.opc.part import Part

from test_api import client,create,approved,forbid_api_external_calls
from test_material_parsing import upload
from app import main,material_documents
from app.conflicts import sources


def linked_word(size):
    doc=Document();doc.add_paragraph('PUBLIC-BODY')
    part=Part(PackURI('/word/media/public.bin'),'application/octet-stream',b'A'*size)
    doc.part.relate_to(part,'urn:public:synthetic-part')
    out=io.BytesIO();doc.save(out);return out.getvalue()


def test_compressed_large_related_part_is_not_treated_as_read_material(client):
    raw=linked_word(33*1024*1024)
    assert len(raw)<20*1024*1024
    task=create(client);_,m=upload(client,task,'large-linked.docx',raw)
    assert m['status']=='needs_input' and m['text']==''
    assert '32MiB' in m['error']
    assert ('material',m['id']) not in sources(main.get_task(task['id']))
    path=main.DATA_ROOT/task['id']/'materials'/(m['id']+'.docx')
    assert path.read_bytes()==raw and m['sha256']==hashlib.sha256(raw).hexdigest()


def synthetic_package(parts):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as package:
        for name,content in parts:package.writestr(name,content)
    return out.getvalue()


@pytest.mark.parametrize('kind,parts,expected',[
    ('part',[('private-file.xml',b'a'*33)],'32MiB'),
    ('total',[('a.xml',b'a'*24),('b.xml',b'b'*24),('c.xml',b'c'*24)],'64MiB'),
    ('count',[(str(i),b'') for i in range(4)],'2048'),
])
def test_rejected_package_never_reaches_word_loader(client,monkeypatch,kind,parts,expected):
    monkeypatch.setattr(material_documents,'MAX_DOCX_PART_BYTES',32)
    monkeypatch.setattr(material_documents,'MAX_DOCX_EXPANDED_BYTES',64)
    monkeypatch.setattr(material_documents,'MAX_DOCX_ENTRIES',3)
    calls=[]
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('Word loader must not run')
    monkeypatch.setattr('docx.Document',forbidden)
    task=create(client);_,m=upload(client,task,'bounds.docx',synthetic_package(parts))
    assert not calls
    assert m['status']=='needs_input' and expected in m['error'] and m['text']==''
    assert 'private-file' not in m['error']


def test_valid_package_at_limits_still_uses_original_extraction(client,monkeypatch):
    raw=linked_word(100)
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        entries=package.infolist()
        monkeypatch.setattr(material_documents,'MAX_DOCX_ENTRIES',len(entries))
        monkeypatch.setattr(material_documents,'MAX_DOCX_PART_BYTES',max(x.file_size for x in entries))
        monkeypatch.setattr(material_documents,'MAX_DOCX_EXPANDED_BYTES',sum(x.file_size for x in entries))
    _,m=upload(client,create(client),'at-limit.docx',raw)
    assert m['status']=='parsed' and m['text']=='PUBLIC-BODY'
    assert m['extraction_coverage']['verification']=='body_text_extraction_only'


def test_over_limit_requires_explicit_source_correction_and_keeps_old_error(client,monkeypatch):
    monkeypatch.setattr(material_documents,'MAX_DOCX_PART_BYTES',32)
    task=approved(client);saved,m=upload(client,task,'rules.docx',synthetic_package([('private-part',b'x'*33)]))
    saved=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'reference_mode':'borrow'}).json()
    assert client.post(f"/api/tasks/{task['id']}/confirm",json={'kind':'requirements','revision':saved['revision']}).status_code==422
    corrected=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json={'revision':saved['revision'],'source_sha256':m['sha256'],'text':'公开人工提供的规则','coverage_note':'只提供规则，不是原文件已经解析','acknowledge_manual_source':True})
    assert corrected.status_code==200,corrected.text
    manual=corrected.json()['materials'][-1]
    assert manual['source_kind']=='user_supplied_text' and manual['source_file_parsed'] is False
    assert manual['original_parse_error']==m['error']
