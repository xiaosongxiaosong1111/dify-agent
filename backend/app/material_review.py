"""Read-only, bounded material clues; never decide business truth or delete files."""
import hashlib,json,re
from collections import defaultdict
from fastapi import Query,Response
from .conflicts import summary as conflict_summary

LIMIT=100
NOTE='依据上传时保存的摘要及当前已解析正文检查，未重新读取原文件。重复和同名差异只是技术线索，不自动去重、删除、替换或选定正确版本；业务事实冲突仍须在需求分歧工作台明确裁定。没有线索不代表已全面排除重复或冲突。'


def label(value,fallback):
    if not isinstance(value,str) or not value or len(value)>1000:return fallback
    try:value.encode('utf-8')
    except UnicodeError:return fallback
    return value


def inspect_materials(task):
    materials=task.get('materials',[]);rows=[];raw_groups=defaultdict(list);text_groups=defaultdict(list);names=defaultdict(list)
    for position,m in enumerate(materials[:LIMIT],1):
        if not isinstance(m,dict):m={}
        mid=label(m.get('id'),f'unknown-{position}');name=label(m.get('name') or m.get('filename'),'未识别文件名')
        raw=m.get('sha256');raw=raw.lower() if isinstance(raw,str) and re.fullmatch(r'[0-9a-fA-F]{64}',raw) else None
        text=m.get('text');text_hash=None
        if m.get('status')=='parsed' and isinstance(text,str) and text.strip() and len(text)<=100000:
            try:text_hash=hashlib.sha256(text.encode('utf-8')).hexdigest()
            except UnicodeError:pass
        mode=m.get('reference_mode');mode=mode if isinstance(mode,str) and mode in {'borrow','preserve','replicate'} else None
        row={'id':mid,'name':name,'readable_text':bool(text_hash),'reference_mode':mode,'original_digest_recorded':bool(raw),'text_source':'user_supplied_text' if m.get('source_kind')=='user_supplied_text' else 'reviewed_model_image_text' if m.get('source_kind')=='reviewed_model_image_text' else 'file_or_reference'}
        rows.append(row)
        if raw:raw_groups[raw].append(mid)
        if text_hash:text_groups[text_hash].append(mid)
        if name!='未识别文件名' and raw:names[name.casefold()].append((mid,raw))
    groups=lambda values:[{'material_ids':ids} for ids in values.values() if len(ids)>1]
    versions=[{'material_ids':[mid for mid,_ in entries]} for entries in names.values() if len({raw for _,raw in entries})>1]
    try:
        state=conflict_summary(task);record=state.get('record') or {};conflicts=(record.get('review') or {}).get('conflicts',[])
        conflict={'state':'not_enabled' if not state['enabled'] else 'confirmed_record' if state['confirmed'] else 'needs_review','unresolved_count':len(conflicts),'stale':state['stale']}
    except (ValueError,TypeError,KeyError,AttributeError):conflict={'state':'unavailable','unresolved_count':None,'stale':True}
    report={'task_id':task['id'],'revision':task['revision'],'material_total':len(materials),'shown':len(rows),'limit':LIMIT,'truncated':len(materials)>LIMIT,'records':rows,'original_digest_duplicates':groups(raw_groups),'exact_text_duplicates':groups(text_groups),'same_name_different_content':versions,'needs_text_count':sum(not r['readable_text'] for r in rows),'unconfirmed_reference_count':sum(r['reference_mode'] is None for r in rows),'unknown_digest_count':sum(not r['original_digest_recorded'] for r in rows),'conflicts':conflict,'original_files_rechecked':False,'semantic_conflicts_checked':False,'note':NOTE}
    report['snapshot_hash']=hashlib.sha256(json.dumps(report,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return report


def register(h):
    @h.app.get('/api/tasks/{item_id}/material-review')
    def read(item_id:str,response:Response,revision:int=Query(ge=1)):
        response.headers['Cache-Control']='no-store'
        with h.store.lock:
            task=h.get_task(item_id);h.require_revision(task,revision)
            return inspect_materials(task)
