export type ModelSummary = {
  provider: string;
  name: string;
  temperature: number;
  maxTokens: number;
};

type Props = {
  current: ModelSummary;
  selected: ModelSummary;
};

const AgentModelComparison = ({ current, selected }: Props) => (
  <div className="agent-model-comparison">
    <b>合并预览与已选模型不同</b>
    <table>
      <thead>
        <tr>
          <th>配置项</th>
          <th>合并预览</th>
          <th>本次已选</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>供应商</td><td>{current.provider}</td><td>{selected.provider}</td></tr>
        <tr><td>型号</td><td>{current.name}</td><td>{selected.name}</td></tr>
        <tr><td>Temperature</td><td>{current.temperature}</td><td>{selected.temperature}</td></tr>
        <tr><td>Max tokens</td><td>{current.maxTokens}</td><td>{selected.maxTokens}</td></tr>
      </tbody>
    </table>
    <p className="hint">你可以在本页明确采用完整模型参数，或前往配置页调整；采用或保存后重新分析保留方案，旧确认不会沿用。</p>
  </div>
);

export default AgentModelComparison;