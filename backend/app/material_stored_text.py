"""Read stored material text, never reparse/recheck a source file or adopt text."""
import hashlib,hmac,json,re
from fastapi import APIRouter,HTTPException
from .message_original_pages import ReadRoute
from .material_text import source_metadata

FIELDS=('text','partial_text')
MAX_BYTES=2_000_000
PAGE=4000
NOTE='仅核对本次保存的文字记录/当前页，不重新解析或核对原文件，不代表全部页/布局/OCR/语义已读、材料正式采用或本次批准。原解析片段不当作当前已采用正文，原来源、覆盖说明和未知项保持。'


def digest(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
def file_hash(material):return material.get('sha256') if digest(material.get('sha256')) else None


def entry(value):
    result={'state':'unavailable','source_length':None,'source_bytes':None,'content_sha256':None,'note':'该字段未保存为可完整核对的文字，未转换或猜测。'}
    if value is None:return {**result,'state':'missing','source_length':0,'source_bytes':0,'note':'该字段没有保存文字。'}
    if not isinstance(value,str):return result
    result['source_length']=len(value)
    if len(value)>MAX_BYTES:return {**result,'state':'oversized','note':'此字段超过2MB UTF8完整核对范围，未截断冒充完整。'}
    try:raw=value.encode('utf-8')
    except UnicodeError:return {**result,'note':'保存文字编码无法完整核对，未替换坏字符。'}
    result['source_bytes']=len(raw)
    if len(raw)>MAX_BYTES:return {**result,'state':'oversized','note':'此字段超过2MB UTF8完整核对范围，未截断冒充完整。'}
    return {**result,'state':'available' if value else 'empty','content_sha256':hashlib.sha256(raw).hexdigest(),'note':'保存文字可按页读取；不是原文件或全部业务含义已核实的证明。' if value else '此字段保存的文字为空。'}


def describe(task,material):
    public={'schema_version':1,'task_id':task['id'],'revision':task['revision'],'material_id':material['id'],'source_sha256':file_hash(material),
            'status':material.get('status'),'source_metadata':source_metadata(material),'entries':{field:entry(material.get(field)) for field in FIELDS},
            'verification':'saved_material_text_index_only','task_modified':False,'model_called':False,'external_network_requested':False,
            'original_file_rechecked':False,'material_reparsed':False,'business_verified':False,'note':NOTE}
    context={'task_id':task['id'],'revision':task['revision'],'material_id':material['id'],
             'identity':{k:material.get(k) for k in ('name','filename','sha256','status','source_kind','reference_mode','preserve_items','source_coverage_note','extraction_coverage','original_parse_error','image_uncertainties','image_model_response_received')},
             'source_metadata':public['source_metadata'],'entries':public['entries']}
    try:public['source_token']=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii')).hexdigest()
    except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError):raise HTTPException(422,'材料文字来源元数据无法完整核对，未输出部分索引。') from None
    return public


def project_materials(task):
    materials=task.get('materials')
    if not isinstance(materials,list):raise HTTPException(409,'材料列表结构无法核对，未当作没有材料。')
    result=[];seen=set()
    for material in materials:
        if not isinstance(material,dict) or not isinstance(material.get('id'),str) or not material['id'] or material['id'] in seen:raise HTTPException(409,'材料ID缺失/重复或结构不明，未猜测文字归属。')
        seen.add(material['id']);result.append({**{k:v for k,v in material.items() if k not in FIELDS},'text_view':describe(task,material)})
    return result


def register(h):
    router=APIRouter(route_class=ReadRoute)
    def scope(item_id,material_id,payload,keys):
        if set(payload)!=keys or type(payload.get('revision'))is not int or payload['revision']<1:raise HTTPException(422,'材料文字请求须明确当前修订、保存摘要和来源范围，不接受额外字段。')
        sha=payload['source_sha256'];token=payload['source_token']
        if sha is not None and not digest(sha) or token is not None and not digest(token):raise HTTPException(422,'材料文字定位摘要无法核对。')
        task=h.get_task(item_id);h.require_revision(task,payload['revision']);materials=task.get('materials')
        if not isinstance(materials,list):raise HTTPException(409,'材料列表结构无法核对。')
        matches=[m for m in materials if isinstance(m,dict) and m.get('id')==material_id]
        if not matches:raise HTTPException(404,'本任务没有该材料记录。')
        if len(matches)!=1:raise HTTPException(409,'材料ID重复，不能可靠定位原文字。')
        material=matches[0];meta=describe(task,material)
        if sha!=meta['source_sha256'] or token is not None and not hmac.compare_digest(token,meta['source_token']):raise HTTPException(409,'材料原保存摘要、文字或来源标签已变化，请刷新任务，未沿用旧页。')
        return material,meta

    @router.post('/api/tasks/{item_id}/materials/{material_id}/stored-text/index')
    def index(item_id:str,material_id:str,payload:dict):
        with h.store.lock:return scope(item_id,material_id,payload,{'revision','source_sha256','source_token'})[1]

    @router.post('/api/tasks/{item_id}/materials/{material_id}/stored-text/page')
    def page(item_id:str,material_id:str,payload:dict):
        with h.store.lock:
            material,meta=scope(item_id,material_id,payload,{'revision','source_sha256','source_token','field','offset'})
            field=payload['field'];offset=payload['offset']
            if not isinstance(field,str) or field not in FIELDS or type(offset)is not int or offset<0 or payload['source_token'] is None:raise HTTPException(422,'材料页必须明确已核对来源指纹、注册文字字段和非负码点位置。')
            source=meta['entries'][field]
            if source['state']!='available':raise HTTPException(413 if source['state']=='oversized' else 409,source['note'])
            text=material[field]
            if offset>=len(text):raise HTTPException(422,'页位置超出保存文字，未改到其它字段或位置。')
            end=min(len(text),offset+PAGE);chunk=text[offset:end]
            return {**meta,'verification':'saved_material_text_page_only','field':field,'content_chunk':chunk,
                    'page_start':offset,'page_end':end,'page_size_limit':PAGE,'page_sha256':hashlib.sha256(chunk.encode('utf-8')).hexdigest(),
                    'complete_field':offset==0 and end==len(text),'has_previous':offset>0,'has_next':end<len(text),
                    'partial_extraction':field=='partial_text'}
    h.app.include_router(router)
