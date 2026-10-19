import { useState } from 'react';
import { Database, LoaderCircle } from 'lucide-react';

type Dataset = { id: string; name?: string; description?: string; document_count?: number };
type DatasetPage = { data: Dataset[]; has_more: boolean };

export default function DatasetSelector({ environmentId, selected, disabled, onChange, scope }: {
  environmentId: string | null; selected: string[]; disabled: boolean; onChange: (ids: string[]) => void; scope?:string;
}) {
  const [source,setSource]=useState<'console'|'service'>('console');
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async (nextPage: number) => {
    if (!environmentId) return;
    setLoading(true); setError('');
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE || '/api'}/environments/${environmentId}/datasets?page=${nextPage}&limit=100&source=${source}`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw Error(typeof body.detail === 'string' ? body.detail : `知识库读取失败（HTTP ${response.status}）。`);
      }
      const body: DatasetPage = await response.json();
      if (!Array.isArray(body.data) || typeof body.has_more !== 'boolean' || body.data.some(d => !d || typeof d.id !== 'string')) throw Error('目录返回格式不符合预期，不能当作成功加载。');
      if (!body.data.length && body.has_more) throw Error('目录返回空页但声明仍有后续数据，请核对实例接口；暂不继续分页。');
      setDatasets(previous => [...new Map((nextPage === 1 ? body.data : [...previous, ...body.data]).map(d => [d.id, d])).values()]);
      setPage(nextPage); setHasMore(body.has_more);
    } catch (e) { setError(e instanceof Error ? e.message : '无法读取知识库目录。'); }
    finally { setLoading(false); }
  };
  return <section className="dataset-selector">
    <label className="field"><span>知识库目录认证方式</span><select aria-label="知识库目录认证方式" value={source} disabled={disabled||loading} onChange={e=>{setSource(e.target.value as 'console'|'service');setDatasets([]);setPage(0);setHasMore(false);setError('')}}><option value="console">使用 Dify 管理连接</option><option value="service">使用知识库 API Key</option></select></label>
    <button className="secondary full" disabled={!environmentId || disabled || loading} onClick={() => void load(1)}>{loading ? <LoaderCircle className="spin" size={14}/> : <Database size={14}/>}读取真实知识库目录</button>
    <p className="hint">管理连接可读取当前账号有权查看的库；知识库 API Key 按它自己的权限读取，限定指定库的 Key 可能无法列举全局目录。此入口仅查询与选择已有库，不创建或上传资料；无法列举时可手填已确认的 ID。</p>
    {error && <div className="alert error" role="alert">{error}</div>}
    {page > 0 && <><div className="listhead"><b>{scope?`${scope} 检索知识库`:'默认检索知识库'}</b><small>已读取 {datasets.length} 个</small></div>
      {!datasets.length && <div className="empty-small bordered">当前目录为空。已填写的 ID 保留，请核对库是否存在及访问权限。</div>}
      <div className="dataset-list">{datasets.map(d => <label key={d.id} className="dataset-option"><input type="checkbox" disabled={disabled || loading} checked={selected.includes(d.id)} onChange={e => onChange(e.target.checked ? [...new Set([...selected, d.id])] : selected.filter(id => id !== d.id))}/><span><b>{d.name || '未命名知识库'}</b><small>{d.id}{typeof d.document_count === 'number' ? ` · ${d.document_count} 份文档` : ''}</small>{d.description && <small>{d.description}</small>}</span></label>)}</div>
      {hasMore && <button className="secondary full" disabled={disabled || loading} onClick={() => void load(page + 1)}>加载下一页知识库</button>}
      <p className="hint">{scope?'选择只填写当前节点的流程草稿，尚未保存、确认或执行。':'选择会修改任务的默认检索配置，需要保存并确认。流程节点若单独指定知识库 ID，还需在流程计划中同步复核。'}</p>
    </>}
  </section>;
}
