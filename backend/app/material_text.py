"""User-supplied text for an unread source; never imply image/OCR parsing."""
import hashlib
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool,StrictStr,Field


class TextRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    source_sha256:StrictStr=Field(pattern=r'^[0-9a-f]{64}$')
    text:StrictStr=Field(min_length=1,max_length=100000)
    coverage_note:StrictStr=Field(min_length=1,max_length=2000)
    acknowledge_manual_source:StrictBool


def source_metadata(material):
    kind=material.get('source_kind')
    if kind not in {'user_supplied_text','reviewed_model_image_text'}:kind='file_text_parser'
    return {'source_kind':kind,'source_file_parsed':kind=='file_text_parser' and material.get('status')=='parsed',
            'source_coverage_note':material.get('source_coverage_note') if kind!='file_text_parser' else '仅文件文字提取，不据此声称图像、布局、OCR或全部业务含义已读取。',
            'image_model_response_received':material.get('image_model_response_received',False),'image_uncertainties':material.get('image_uncertainties',[])}



def register(h):
    @h.app.post('/api/tasks/{item_id}/materials/{material_id}/text')
    def supply_text(item_id:str,material_id:str,payload:TextRequest):
        if not payload.acknowledge_manual_source or not payload.text.strip() or not payload.coverage_note.strip():
            raise HTTPException(422,'请明确确认这是用户提供的文字，并填写正文及覆盖／缺失范围；不是原文件已解析或OCR成功。')
        with h.store.lock:
            task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
            material=next((m for m in task['materials'] if m['id']==material_id),None)
            if not material:raise HTTPException(404,'材料不存在，未保存文字。')
            if material.get('status')!='needs_input':raise HTTPException(422,'此材料已有可用正文或不处于待补充状态，请另行上传说明，不能覆盖当前来源。')
            if material.get('sha256')!=payload.source_sha256:raise HTTPException(409,'原材料身份已变化，未采用旧页面的文字说明。')
            from .material_sources import read_source
            read_source(h,item_id,material)
            h.invalidate(task,'为未解析材料提供文字前保存')
            material.update(status='parsed',text=payload.text,error='',source_kind='user_supplied_text',
                            source_file_parsed=False,source_coverage_note=payload.coverage_note,
                            original_parse_status='needs_input',original_parse_error=material.get('error',''),
                            text_source_acknowledged=True,text_supplied_at=h.now(),
                            text_sha256=hashlib.sha256(payload.text.encode('utf-8')).hexdigest())
            # Existing reference degree remains a separate explicit decision.
            return h.save_task(task)
