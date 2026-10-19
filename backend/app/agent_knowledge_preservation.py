"""Project the explicitly supported native knowledge policy without rewriting it."""
from .agent_preservation import fields,text
from .agent_plan import validate_agent_plan


def project(knowledge,selected,prompt):
    fields(knowledge,{'sets'},'Agent 知识集',('sets',))
    rows=knowledge['sets'];expected=selected.get('sets')
    if not isinstance(rows,list) or not isinstance(expected,list):raise ValueError('Agent 知识集须为明确数组。')
    selected_ids={d['id'] for s in expected for d in s['datasets']}
    if not rows:
        if selected_ids:raise ValueError('本次已选知识集不能在保留合并中清空。')
        return []
    if not selected_ids:raise ValueError('文本 Agent 没有已确认知识库，不能从保留文件擅自加入知识集。')
    if not 1<=len(rows)<=5:raise ValueError('Agent 保留知识集须为1—5个。')
    ids=set();plan_rows=[]
    for row in rows:
        fields(row,{'id','name','description','datasets','query','retrieval','metadata_filtering'},'Agent 知识集条目',('id','name','description','datasets','query','retrieval'))
        ident=row['id'];text(ident,'Agent 知识集ID',255,True)
        if ident!=ident.strip() or ident in ids:raise ValueError('Agent 知识集ID须明确、唯一，不自动修剪后合并。')
        ids.add(ident)
        datasets=row['datasets']
        if not isinstance(datasets,list) or not 1<=len(datasets)<=20:raise ValueError('每个Agent知识集须明确1—20个知识库。')
        dataset_ids=[]
        for dataset in datasets:
            fields(dataset,{'id','name','description'},'Agent 知识库引用',('id',))
            for key in ('name','description'):
                if dataset.get(key) is not None:text(dataset[key],'Agent 知识库显示信息',10000)
            dataset_ids.append(dataset['id'])
        query=fields(row['query'],{'mode','value'},'Agent 知识集查询',('mode',))
        if query['mode']!='generated_query' or query.get('value') is not None:raise ValueError('Agent 保留只支持generated_query且无固定查询；不删除固定查询后通过。')
        retrieval=fields(row['retrieval'],{'mode','top_k','score_threshold','reranking_mode','reranking_enable','reranking_model','weights','model'},'Agent 知识集检索',('mode','top_k','reranking_enable'))
        if retrieval['mode']!='multiple' or retrieval['reranking_enable'] is not False or retrieval.get('reranking_mode','reranking_model')!='reranking_model':raise ValueError('Agent 保留只适配明确多库检索且关闭重排，不推测默认重排或模型路由。')
        if any(retrieval.get(key) is not None for key in ('score_threshold','reranking_model','weights','model')):raise ValueError('Agent 知识集的分数阈值、重排、权重或路由模型尚未适配，不移除后通过。')
        filtering=fields(row.get('metadata_filtering',{}),{'mode','model_config','metadata_model_config','conditions'},'Agent 知识集元数据过滤')
        if filtering.get('mode','disabled')!='disabled' or any(filtering.get(key) is not None for key in ('model_config','metadata_model_config','conditions')):raise ValueError('Agent 知识集元数据过滤尚未适配，只保留明确默认关闭配置。')
        plan_rows.append({'name':row['name'],'description':row['description'],'dataset_ids':dataset_ids,'query_mode':'generated_query','top_k':retrieval['top_k']})
    checked=validate_agent_plan({'app_type':'agent','configuration':{'dataset_ids':sorted(selected_ids)}}, {'schema_version':1,'scope':'knowledge','system_prompt':prompt,'knowledge_sets':plan_rows})
    if not checked['valid']:raise ValueError('；'.join(checked['errors']))
    return plan_rows
