"""A compact read model, never persisted or used as a restore snapshot."""
import json
from .task_message_window import task_view

MAX_VERSIONS=5000
MAX_INDEX_BYTES=2_000_000
FIELDS={'id':200,'label':2000,'kind':100,'created_at':100}
REASONS={
    'invalid_history':'保存的版本列表结构无法核对',
    'version_count_limit':'版本数超过本批5000条索引上限',
    'version_id_invalid':'历史版本ID缺失或无法可靠定位',
    'version_id_ambiguous':'历史版本ID重复，不能可靠区分',
    'metadata_invalid':'有版本索引字段不是明确文字对象',
    'metadata_limit':'有版本索引字段超过明确长度上限',
    'metadata_encoding':'有版本索引文字编码无法完整核对',
    'index_bytes_limit':'完整版本索引超过本批2MB上限',
}


def text(value,limit,*,required=False):
    if value is None or value=='':
        if required:raise ValueError('version_id_invalid')
        return None
    if not isinstance(value,str):raise ValueError('metadata_invalid')
    if len(value)>limit:raise ValueError('metadata_limit')
    value.encode('utf-8')
    if required and (not value.strip() or not value.isprintable()):raise ValueError('version_id_invalid')
    return value


def version_index(task):
    rows=task.get('versions');count=len(rows) if isinstance(rows,list) else None
    meta={'schema_version':1,'task_id':task['id'],'revision':task['revision'],'state_sequence':task.get('state_sequence',0),
          'state':'unavailable','total_versions':count,'returned_versions':0,'body_omitted':True,'unknown_revision_count':0,
          'task_modified':False,'model_called':False,'external_network_requested':False,'reason':None,
          'note':'版本索引无法完整核对或超过5000条/2MB索引范围；未返回部分列表或删除存档。完整Task及快照仍保留，请核对原记录；不能当作没有历史。'}
    def unavailable(reason):return [],{**meta,'reason':reason,'note':REASONS[reason]+'；未返回部分列表或删除存档，完整Task及快照仍保留。请核对原记录，不能当作没有历史。'}
    if not isinstance(rows,list):return unavailable('invalid_history')
    if count>MAX_VERSIONS:return unavailable('version_count_limit')
    projected=[];seen=set();size=2;unknown=0
    try:
        for row in rows:
            if not isinstance(row,dict):raise ValueError('metadata_invalid')
            item={}
            for key,limit in FIELDS.items():
                value=text(row.get(key),limit,required=key=='id')
                if value is not None:item[key]=value
            if item['id'] in seen:raise ValueError('version_id_ambiguous')
            seen.add(item['id']);revision=row.get('revision')
            if type(revision)is int and 1<=revision<=9007199254740991:item['revision']=revision
            else:unknown+=1
            size+=len(json.dumps(item,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'))+(1 if projected else 0)
            if size>MAX_INDEX_BYTES:raise ValueError('index_bytes_limit')
            projected.append(item)
        return projected,{**meta,'state':'ready','returned_versions':count,'unknown_revision_count':unknown,
                          'note':'仅完整版本索引，不含快照正文；未记录或超出精确范围的旧修订不补猜。比较和恢复仍由原接口读取实际完整存档并核对当前修订/预览指纹，不是业务或平台已验收。'}
    except UnicodeError:return unavailable('metadata_encoding')
    except (ValueError,TypeError,OverflowError,RecursionError) as exc:return unavailable(str(exc) if str(exc) in REASONS else 'metadata_invalid')


def workspace_view(task):
    view=task_view(task);rows,summary=version_index(task)
    return {**view,'versions':rows,'version_summary':summary,'workspace_view':{
        'schema_version':1,'mode':'compact','task_id':task['id'],'revision':task['revision'],'state_sequence':task.get('state_sequence',0),
        'messages_view':'recent','versions_view':'index','task_modified':False,'model_called':False,'external_network_requested':False,'business_verified':False}}
