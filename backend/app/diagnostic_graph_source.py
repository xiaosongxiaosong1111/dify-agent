"""Bounded fingerprints, not raw runtime/published graphs or customer content."""
import hashlib,json,math,uuid

NOTE='只核对核心节点ID／父作用域／data及连接／句柄／data；不判断完整应用特性、资源或业务正确性。节点顶层位置／尺寸／视图字段不参与，data内其他字段仍保守核对；平台规范化差异也可能被判不同，须人工核对，不自动覆盖。三个内容一致不证明同一发布版本ID，只以此次采集时为准。'


def fingerprint(graph):
    try:
        if not isinstance(graph,dict) or not isinstance(graph.get('nodes'),list) or not isinstance(graph.get('edges'),list) or not 1<=len(graph['nodes'])<=1500 or len(graph['edges'])>1500:raise ValueError()
        budget=[40000];seen=set()
        def bounded(value,depth=0):
            budget[0]-=1
            if budget[0]<0 or depth>60:raise ValueError()
            if isinstance(value,(dict,list)):
                if id(value) in seen:raise ValueError()
                seen.add(id(value))
                if isinstance(value,dict) and any(not isinstance(k,str) for k in value):raise ValueError()
                for child in value.values() if isinstance(value,dict) else value:bounded(child,depth+1)
            elif value is not None and type(value) not in (str,int,float,bool):raise ValueError()
            elif type(value) is float and not math.isfinite(value):raise ValueError()
        bounded(graph)
        nodes=[];ids=set()
        for raw in graph['nodes']:
            if not isinstance(raw,dict) or not isinstance(raw.get('id'),str) or not 0<len(raw['id'])<=256 or raw['id'] in ids or not isinstance(raw.get('data'),dict) or not isinstance(raw['data'].get('type'),str) or not 0<len(raw['data']['type'])<=128:raise ValueError()
            if raw.get('parentId') is not None and not isinstance(raw['parentId'],str):raise ValueError()
            ids.add(raw['id']);data={k:v for k,v in raw['data'].items() if k!='selected'}
            nodes.append({'id':raw['id'],'parent_id':raw.get('parentId'),'data':data})
        if any(n['parent_id'] is not None and n['parent_id'] not in ids for n in nodes):raise ValueError()
        edges=[];edge_keys=set()
        for raw in graph['edges']:
            if not isinstance(raw,dict) or raw.get('source') not in ids or raw.get('target') not in ids:raise ValueError()
            a,b=raw.get('sourceHandle','source'),raw.get('targetHandle','target')
            if not isinstance(a,str) or not a or not isinstance(b,str) or not b or not isinstance(raw.get('data',{}),dict):raise ValueError()
            key=(raw['source'],raw['target'],a,b)
            if key in edge_keys:raise ValueError()
            edge_keys.add(key);edges.append({'source':key[0],'target':key[1],'source_handle':a,'target_handle':b,'data':raw.get('data',{})})
        value={'nodes':sorted(nodes,key=lambda n:n['id']),'edges':sorted(edges,key=lambda e:(e['source'],e['target'],e['source_handle'],e['target_handle']))}
        text=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(text)>2_000_000:raise ValueError()
        return {'digest':hashlib.sha256(text).hexdigest(),'node_count':len(nodes),'edge_count':len(edges)}
    except (ValueError,TypeError,KeyError,RecursionError):return None


def artifact(host,task):
    from .dsl_roundtrip import parse
    from fastapi import HTTPException
    try:
        uuid.UUID(task['id'])
        path=host.artifact_path(task).resolve();folder=(host.DATA_ROOT/task['id']).resolve()
        if path.parent!=folder or path.stat().st_size>2_000_000:raise ValueError()
        document=parse(path.read_text(encoding='utf-8'),task['app_type'])
        return fingerprint(document['workflow']['graph'])
    except (ValueError,OSError,KeyError,TypeError,AttributeError,HTTPException):return None


def initial(local):
    return {'state':'not_checked','artifact':local,'execution':None,'published':None,'published_workflow_id':None,'matched':False,'note':NOTE}


def compare(local,execution_graph,published):
    result=initial(local);result['execution']=fingerprint(execution_graph)
    if not result['execution']:result.update(state='execution_graph_unavailable',message='远端运行详情缺少可核对的完整核心图，不能根据节点ID列表猜执行版本。');return result
    try:pid=str(uuid.UUID(published.get('id'))) if isinstance(published,dict) else None
    except (ValueError,TypeError,AttributeError):pid=None
    result['published_workflow_id']=pid
    result['published']=fingerprint(published.get('graph')) if isinstance(published,dict) and pid else None
    if not result['published']:result.update(state='published_unavailable',message='当前已发布工作流没有可信ID／核心图，不能用草稿或旧缓存替代。')
    elif result['execution']['digest']!=result['published']['digest']:result.update(state='different_published_graph',message='实际执行核心图与该应用当前已发布核心图不同；这是历史版本或发生了结构变化，请复核再修复。')
    elif not local:result.update(state='artifact_unavailable',message='当前Sierra成果核心图无法可信读取，虽可保留远端证据，不能当作当前方案。')
    elif local['digest']!=result['execution']['digest']:result.update(state='different_artifact_graph',message='执行／已发布核心图与当前Sierra成果不同，可能有Dify手改或平台规范化差异；先读取实际DSL并复核保留。')
    else:result.update(state='matched',matched=True,message='实际执行、当前已发布和当前Sierra成果的核心节点／连接内容一致；仍需核对完整特性、资源与业务。')
    return result
