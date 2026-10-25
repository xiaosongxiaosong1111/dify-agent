"""Public synthetic PDF/DOCX bytes exercise the actual multipart parser."""
import io
import hashlib
import pytest
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
from docx import Document
from test_api import client,create,approved,forbid_api_external_calls
from test_material_parsing import upload
from app import main
from app.conflicts import sources
from app.material_text import source_metadata


def pdf(pages,encrypted=False):
    writer=PdfWriter()
    for text in pages:
        page=writer.add_blank_page(width=595,height=842)
        if text is not None:
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
            stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 30 700 Td ('+text+') Tj ET').encode())
            page[NameObject('/Contents')]=stream
    if encrypted:writer.encrypt('public-fixture-password')
    output=io.BytesIO();writer.write(output);return output.getvalue()


def word(nested=False,merged=False):
    doc=Document();doc.add_paragraph('RULE-BEFORE')
    table=doc.add_table(rows=1,cols=2);table.cell(0,0).text='TABLE-LEFT';table.cell(0,1).text='TABLE-RIGHT'
    if merged:table.cell(0,0).merge(table.cell(0,1))
    if nested:
        cell=table.cell(0,0);cell.add_paragraph('CELL-BEFORE');cell.add_table(rows=1,cols=1).cell(0,0).text='NESTED-RULE';cell.add_paragraph('CELL-AFTER')
    doc.add_paragraph('RULE-AFTER');doc.add_table(rows=1,cols=1).cell(0,0).text='LAST-TABLE'
    out=io.BytesIO();doc.save(out);return out.getvalue()


def test_mixed_pdf_is_not_complete_keeps_partial_text_and_unread_page_numbers(client):
    task=approved(client);raw=pdf(['FIRST-PAGE',None,'THIRD-PAGE'])
    saved,m=upload(client,task,'mixed.pdf',raw)
    assert m['status']=='needs_input' and m['text']==''
    assert m['extraction_coverage']['unread_pages']==[2] and m['extraction_coverage']['total_pages']==3
    assert '[第 1 页]' in m['partial_text'] and 'FIRST-PAGE' in m['partial_text'] and 'THIRD-PAGE' in m['partial_text']
    assert '第2页' in m['error'] and ('material',m['id']) not in sources(saved)
    assert not source_metadata(m)['source_file_parsed']
    saved=client.patch(f"/api/tasks/{task['id']}/materials/{m['id']}",json={'reference_mode':'borrow'}).json()
    assert client.post(f"/api/tasks/{task['id']}/confirm",json={'kind':'requirements','revision':saved['revision']}).status_code==422
    path=main.DATA_ROOT/task['id']/'materials'/(m['id']+'.pdf')
    assert path.read_bytes()==raw and m['sha256']==hashlib.sha256(raw).hexdigest()


def test_pdf_text_pages_have_source_scope_and_page_order(client):
    task=create(client);_,m=upload(client,task,'readable.pdf',pdf(['FIRST-PAGE','SECOND-PAGE']))
    assert m['status']=='parsed' and m['text'].index('FIRST-PAGE')<m['text'].index('SECOND-PAGE')
    assert m['extraction_coverage']['unread_pages']==[]
    assert source_metadata(m)['source_coverage_note']==m['extraction_coverage']['scope_note']
    assert 'OCR' in source_metadata(m)['source_coverage_note']


@pytest.mark.parametrize('raw,expected',[
    (pdf([None,None]),'未提取'),
    (pdf(['PUBLIC'],encrypted=True),'加密'),
    (pdf([None]*101),'100'),
    (b'%PDF-broken-private-marker','PDF'),
],ids=['no_text','encrypted','too_many_pages','corrupt'])
def test_unreadable_pdf_does_not_expose_file_contents(client,raw,expected):
    task=create(client);_,m=upload(client,task,'unreadable.pdf',raw)
    assert m['status']=='needs_input' and m['text']=='' and expected in m['error']
    assert 'private-marker' not in m['error']


@pytest.mark.parametrize('nested,merged',[(False,False),(True,False),(False,True)])
def test_docx_preserves_paragraph_table_order_and_nested_text(client,nested,merged):
    task=create(client);_,m=upload(client,task,'rules.docx',word(nested,merged))
    assert m['status']=='parsed' and m['text'].index('RULE-BEFORE')<m['text'].index('TABLE-LEFT')<m['text'].index('RULE-AFTER')<m['text'].index('LAST-TABLE')
    if nested:assert m['text'].index('CELL-BEFORE')<m['text'].index('NESTED-RULE')<m['text'].index('CELL-AFTER')
    if merged:assert m['text'].count('TABLE-LEFT')==m['text'].count('TABLE-RIGHT')==1
    assert '页眉' in source_metadata(m)['source_coverage_note']


def test_corrupt_or_empty_word_is_not_read(client):
    task=create(client);_,m=upload(client,task,'bad.docx',b'private-marker-not-a-docx')
    assert m['status']=='needs_input' and m['text']=='' and 'private-marker' not in m['error']
    doc=Document();out=io.BytesIO();doc.save(out);_,m=upload(client,task,'empty.docx',out.getvalue())
    assert m['status']=='needs_input' and m['text']==''


def test_partial_pdf_manual_text_keeps_original_coverage_and_unconfirmed_state(client):
    task=create(client);task,m=upload(client,task,'mixed.pdf',pdf(['PUBLIC',None]))
    assert m['status']=='needs_input'
    response=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json={'revision':task['revision'],'source_sha256':m['sha256'],'text':'用户核对后的公开说明','coverage_note':'只说明第一页，第二页尚待核对','acknowledge_manual_source':True})
    assert response.status_code==200,response.text
    saved=response.json();new=saved['materials'][-1]
    assert new['source_kind']=='user_supplied_text' and not source_metadata(new)['source_file_parsed']
    assert source_metadata(new)['source_coverage_note']=='只说明第一页，第二页尚待核对'
    assert new['original_parse_error']==m['error'] and saved['versions'][-1]['materials'][-1]['partial_text']==m['partial_text']
    assert not saved['requirements_confirmed']


def test_page_extraction_failure_is_unread_and_each_page_is_read_once(client,monkeypatch):
    from pypdf._page import PageObject
    original=PageObject.extract_text;seen=[]
    def extract(page,*args,**kwargs):
        seen.append(page)
        if len(seen)==2:raise ValueError('private-parser-marker')
        return original(page,*args,**kwargs)
    monkeypatch.setattr(PageObject,'extract_text',extract)
    task=create(client);_,m=upload(client,task,'partly-damaged.pdf',pdf(['FIRST','SECOND','THIRD']))
    assert m['status']=='needs_input' and m['extraction_coverage']['unread_pages']==[2]
    assert len(seen)==3 and 'FIRST' in m['partial_text'] and 'THIRD' in m['partial_text']
    assert 'private-parser-marker' not in m['error']


@pytest.mark.parametrize('suffix',['pdf','docx'])
def test_document_text_limit_never_saves_a_truncated_partial_source(client,suffix):
    if suffix=='pdf':raw=pdf(['X'*100001,None])
    else:
        doc=Document();doc.add_paragraph('X'*100001);out=io.BytesIO();doc.save(out);raw=out.getvalue()
    task=create(client);_,m=upload(client,task,'large.'+suffix,raw)
    assert m['status']=='needs_input' and m['text']=='' and not m.get('partial_text') and '10' in m['error']


def test_historical_material_without_new_coverage_metadata_keeps_its_scope():
    m={'id':'old','name':'old.pdf','status':'parsed','text':'old-extraction'}
    assert source_metadata(m)['source_file_parsed']
    assert source_metadata(m)['source_coverage_note']=='仅文件文字提取，不据此声称图像、布局、OCR或全部业务含义已读取。'
    assert 'extraction_coverage' not in m
