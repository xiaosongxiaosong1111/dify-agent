export type DatasetCheck = {
  status_label: string;
  observed_at: string;
  source: 'console' | 'service';
  pages_read: number;
  catalog_complete: boolean;
  search_complete_for_selected: boolean;
  rows: {
    id: string;
    status_label: string;
    metadata: {
      name?: string;
      document_count?: number;
      available_document_count?: number;
      indexing_technique?: string;
      embedding_model?: string;
      embedding_model_provider?: string;
    };
    issues: string[];
    unavailable_fields: string[];
    guidance?:{option:string;experience:string;cost:string;manual_work:string}[];
  }[];
  note: string;
  warnings: string[];
};

const sourceLabel: Record<DatasetCheck['source'], string> = {
  console: '管理连接',
  service: '知识库 Key',
};

const knownFields: Record<string, string> = {
  indexing_technique:'索引方式',embedding_model:'Embedding型号',embedding_model_provider:'Embedding供应商',
  document_count: '文档数',
  available_document_count: '可用文档数',
  status_label: '状态',
  pages_read: '已读取页数',
  catalog_complete: '目录完整性',
  search_complete_for_selected: '指定ID核对完整性',
  'metadata.name': '名称',
  'metadata.document_count': '文档数',
  'metadata.available_document_count': '可用文档数',
  'metadata.indexing_technique': '索引方式',
  'metadata.embedding_model': 'Embedding模型',
  'metadata.embedding_model_provider': 'Embedding提供方',
};

const showCount = (value?: number) =>
  value === undefined || value === null ? '未知' : String(value);

const showField = (field: string) => knownFields[field] ?? field;

// Advice is optional for older responses; malformed advice must never reach React.
export function validDatasetGuidance(value: unknown): boolean {
  if (value === undefined) return true;
  return Array.isArray(value) && (value.length === 0 || value.length === 3) && value.every(item =>
    item !== null && typeof item === 'object' && !Array.isArray(item) &&
    Object.keys(item).length === 4 && ['option','experience','cost','manual_work'].every(key =>
      typeof item[key] === 'string' && item[key].trim().length > 0 && item[key].length <= 2000));
}

export default function DatasetConfigurationResult({ result }: { result: DatasetCheck }) {
  return (
    <section className="dataset-configuration-result">
      <h2>目标知识库目录与索引计数</h2>
      <div className="callout amber">
        <p>本结果仅用于目录与索引计数的元数据核对：未执行检索，不读取全文，不证明资料等价，也不代表业务通过。</p>
      </div>
      <dl>
        <dt>状态</dt><dd>{result.status_label}</dd>
        <dt>核对时间</dt><dd>{result.observed_at}</dd>
        <dt>认证来源</dt><dd>{sourceLabel[result.source]}</dd>
        <dt>已读取页数</dt><dd>{result.pages_read}</dd>
        <dt>目录是否完整</dt><dd>{result.catalog_complete ? '是' : '否'}</dd>
        <dt>指定ID是否核对完整</dt><dd>{result.search_complete_for_selected ? '是' : '否'}</dd>
      </dl>
      <div className="hint"><p>说明：{result.note}</p></div>
      {result.warnings.length > 0 && (
        <div className="callout amber">
          <p>警告：</p>
          <ul>{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </div>
      )}
      <h3>逐项结果</h3>
      {result.rows.map((row, index) => (
        <article key={row.id || index} className="merge-conflict">
          <p><strong>完整ID：</strong>{row.id}</p>
          <p><strong>名称：</strong>{row.metadata.name?.trim() ? row.metadata.name : '未提供名称'}</p>
          <p><strong>文档数：</strong>{showCount(row.metadata.document_count)}</p>
          <p><strong>可用文档数：</strong>{showCount(row.metadata.available_document_count)}</p>
          <p><strong>索引方式：</strong>{row.metadata.indexing_technique==='economy'?'经济关键词索引':row.metadata.indexing_technique==='high_quality'?'高质量索引':row.metadata.indexing_technique||'未知'}</p>
          <p><strong>Embedding：</strong>{row.metadata.indexing_technique==='economy'?'不适用（经济索引）':`${row.metadata.embedding_model||'未知'}${row.metadata.embedding_model_provider?`（${row.metadata.embedding_model_provider}）`:''}`}</p>
          <p><strong>状态：</strong>{row.status_label}</p>
          <div><strong>本次目录核对问题：</strong>{row.issues.length > 0 ? <ul>{row.issues.map((issue, issueIndex) => <li key={issueIndex}>{issue}</li>)}</ul> : <span>无</span>}</div>
          {!!row.guidance?.length&&<details className="dataset-remediation"><summary>可选处理方案（尚未执行）</summary><p className="hint">请根据影响决定补齐条件、明确更换或保留待验证；没有自动修改资源或缩小范围。</p>{row.guidance.map((g,i)=><div key={i}><b>{g.option}</b><p>体验影响：{g.experience}</p><p>费用：{g.cost}</p><p>人工工作：{g.manual_work}</p></div>)}</details>}
          <p><strong>无法完整核对的字段：</strong>{row.unavailable_fields.length > 0 ? row.unavailable_fields.map(showField).join('、') : '无'}</p>
        </article>
      ))}
    </section>
  );
}
