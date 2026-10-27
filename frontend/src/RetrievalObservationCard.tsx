export type RetrievalObservation={basis:string;note:string;retrieval_status?:string;result_count?:number|null;sources?:{position:number;dataset_id:string|null;document_id:string|null;segment_id:string|null;score:number|null}[];sources_truncated?:boolean};
export default function RetrievalObservationCard({value}:{value:RetrievalObservation}){
 if(value.basis!=='native_retrieval_result')return null;
 const label=({empty:'本次无命中片段',returned:'已返回片段，相关性待业务核对',technical_failure:'技术失败，不是无命中',unknown:'证据不足，不能当作无命中'} as Record<string,string>)[value.retrieval_status||'']||'证据不足，不能当作无命中';
 return <section className="retrieval-observation" aria-label="检索结果证据"><b>检索：{label}</b><p>返回片段数：{value.result_count??'未知'}{value.sources_truncated?'；来源预览仅前20项，不能当作全部来源':''}</p>
 {!!value.sources?.length&&<details><summary>核对白名单来源与平台分数</summary>{value.sources.map(source=><div key={source.position} style={{overflowWrap:'anywhere'}}><b>第{source.position}项</b><p>知识库ID：{source.dataset_id??'未知'} · 文档ID：{source.document_id??'未知'} · 片段ID：{source.segment_id??'未知'}</p><p>平台分数：{source.score??'未知'}（不等于业务相关性结论）</p></div>)}</details>}
 <p className="hint">{value.note}</p></section>;
}
