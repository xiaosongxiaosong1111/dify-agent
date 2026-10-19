"""Explicit independence declarations for the exact merged native document."""
def candidates(root):
    from .dsl_roundtrip import digest
    token=digest(root)
    return [{'id':n['id'],'title':n['data'].get('title') or n['id'],'parallel_nums':n['data'].get('parallel_nums'),'root_token':token} for n in root['workflow']['graph']['nodes'] if n['data'].get('type')=='iteration' and n['data'].get('is_parallel') is True]


def validate(root,reviews):
    found={n['id']:n for n in candidates(root)}
    if not isinstance(reviews,dict) or set(reviews)-set(found):raise ValueError('并行保留声明须只引用当前合并文件中的实际并行容器，不能复用未知或已改为顺序的声明。')
    if set(found)-set(reviews):raise ValueError('并行项保留需要明确核对当前最终文件的逐项独立性、顺序依赖及副作用，再填写原因并确认；不会猜测或改为顺序。')
    for nid,value in reviews.items():
        if not isinstance(value,dict) or set(value)!={'acknowledge_independence','reason','root_token'} or value['acknowledge_independence'] is not True or not isinstance(value['reason'],str) or not 0<len(value['reason'].strip())<=2000:raise ValueError('并行保留每项须明确确认独立性、填写1—2000字原因及当前文件摘要；仅为用户声明，不代表已运行验证。')
        if value['root_token']!=found[nid]['root_token']:raise ValueError('并行独立性声明的最终文件已变化，请按新的代码、模型、连接及配置重新核对；旧声明不自动沿用。')
    return reviews
