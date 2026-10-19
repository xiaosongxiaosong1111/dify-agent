export type MappingResult = {
  preview_token: string;
  content: string;
  note: string;
  warnings: string[];
  changes: Record<string, unknown>;
  target_environment: { id: string; name: string; base_url: string; version: string };
  verification: string;
  platform_verified: boolean;
  business_verified: boolean;
  target_resources_verified: boolean;
  can_apply: boolean;
};

const yes = (value: boolean) => (value ? "是" : "否");

export default function EnvironmentMappingResult({ result }: { result: MappingResult }) {
  return (
    <section className="environment-mapping-result">
      <div className="callout amber" role="status">
        <strong>目标映射草稿：资源待验证</strong>
        <p className="hint">此草稿尚未导入，也未运行；ID 对应并不证明源与目标知识库的资料等价。</p>
      </div>

      <h2>目标环境</h2>
      <dl>
        <dt>名称</dt>
        <dd>{result.target_environment.name}</dd>
        <dt>地址</dt>
        <dd>{result.target_environment.base_url}</dd>
        <dt>版本</dt>
        <dd>{result.target_environment.version}</dd>
        <dt>环境 ID</dt>
        <dd>{result.target_environment.id}</dd>
      </dl>

      <h2>备注</h2>
      <p>{result.note}</p>

      <h2>警告</h2>
      <div className="merge-conflict">
        {result.warnings.length === 0 ? (
          <p className="hint">无警告。</p>
        ) : (
          <ul>
            {result.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        )}
      </div>

      <h2>验证信息</h2>
      <ul>
        <li>平台已验证：{yes(result.platform_verified)}</li>
        <li>业务已验证：{yes(result.business_verified)}</li>
        <li>目标资源已验证：{yes(result.target_resources_verified)}</li>
        <li>可应用：{yes(result.can_apply)}</li>
      </ul>

      <details>
        <summary>查看完整变更 JSON</summary>
        <pre>{JSON.stringify(result.changes, null, 2)}</pre>
      </details>

      <details>
        <summary>查看完整内容 YAML</summary>
        <pre>{result.content}</pre>
      </details>
    </section>
  );
}
