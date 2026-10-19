"""Delivery provenance for adopted image text; excludes drafts and original candidate prose."""
import hashlib


def summary(host,task):
    result=[]
    for material in task.get('materials',[]):
        if material.get('source_kind')!='reviewed_model_image_text':continue
        plan_id=material.get('image_candidate_id');record=host.store.get('image_preview',plan_id) if plan_id else None
        bound=bool(record and record.get('task_id')==task['id'] and record.get('material_id')==material['id'] and record.get('status')=='adopted' and record.get('source',{}).get('sha256')==material.get('sha256'))
        item={'material_id':material['id'],'source_sha256':material.get('sha256'),'candidate_id':plan_id,'human_reviewed_text_sha256':hashlib.sha256(material.get('text','').encode('utf-8')).hexdigest(),'reviewed_at':material.get('text_reviewed_at'),'source_record_matched':bound,'coverage_note':material.get('source_coverage_note'),'uncertainties':material.get('image_uncertainties',[]),'note':'人工核对的图像模型文字；不是专业OCR、全图理解或实际Dify业务验证。'}
        if bound:
            provider=record.get('provider',{})
            item.update(provider={k:provider.get(k) for k in ('id','name','model','protocol')},preview_revision=record.get('revision'),applied_revision=record.get('applied_revision'),completed_at=record.get('completed_at'),adopted_at=record.get('adopted_at'),estimated_reserve_usd=record.get('image_reserve_usd'),usage=record.get('usage'),human_review_acknowledged=record.get('adoption',{}).get('human_reviewed',False))
        else:item['note']+=' 原候选记录缺失或归属／摘要不匹配，不能声称来源链完整。'
        result.append(item)
    return {'materials':result,'note':'只列当前已采用图像文字的来源链，不导出未采用候选、人工草稿、原图字节、凭据或内部指纹。用量按供应商返回记录；金额是登记计价估算，不是实际账单证明。'}
