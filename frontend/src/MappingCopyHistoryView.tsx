export type History = {
  total: number;
  shown: number;
  invalid_in_window: number;
  truncated: boolean;
  rows: {
    operation_id: string;
    target_task_id: string;
    target_name: string;
    target_revision: number;
    source_revision: number;
    created_at: string;
  }[];
};

export default function MappingCopyHistoryView({
  history,
  disabled,
  onSelect,
}: {
  history: History;
  disabled: boolean;
  onSelect: (operationId: string) => void;
}) {
  const { total, shown, invalid_in_window, truncated, rows } = history;
  return (
    <section className="merge-draft-record" aria-label="创建回执历史">
      <p className="hint">
        这是独立本机任务的创建回执，不代表 Dify 导入、运行或业务验收。
      </p>
      <p className="hint">
        总数 {total} 条，实际展示 {shown} 条，损坏 {invalid_in_window} 条。
      </p>
      {truncated && (
        <p className="callout amber">仅读取最新20条窗口；更早记录未展示，不能当作完整历史。</p>
      )}
      {rows.length === 0 ? (
        <p className="hint">{total===0?"暂无已保存的创建回执。":"本窗口没有可打开的回执；已有记录仍需核对。"}</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.operation_id} className="merge-conflict">
              <div>目标任务：{row.target_name}（ID：{row.target_task_id}）</div>
              <div>
                目标当前修订：{row.target_revision}；源修订：{row.source_revision}
              </div>
              <div>创建时间：{row.created_at}</div>
              <button
                className="secondary"
                type="button"
                disabled={disabled}
                onClick={() => onSelect(row.operation_id)}
              >
                打开本机目标任务
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
