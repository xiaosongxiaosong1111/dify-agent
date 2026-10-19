type Props = { value: string; disabled: boolean; onChange: (value: string) => void };

const EXAMPLE = `{
  "type": "object",
  "properties": {
    "label": { "type": "string" },
    "score": { "type": "number", "minimum": 0, "maximum": 100 }
  },
  "required": ["label", "score"],
  "additionalProperties": false
}`;

export default function ObjectOutcomeSchemaInput(props: Props) {
  const empty = props.value.trim() === '';
  return (
    <section className="object-outcome-schema-input">
      <label>
        对象成功结果 value 本身的完整根 object JSON Schema（不是 outcome 外壳，也不是字段示例）
        <textarea
          aria-label="对象成功结果 Schema"
          value={props.value}
          disabled={props.disabled}
          rows={12}
          spellCheck={false}
          onChange={(e) => props.onChange(e.target.value)}
        />
      </label>
      <p className="hint">
        支持 object、array、string、number、integer、boolean 子集；每个 object 必须 additionalProperties=false。不支持 null、引用、组合、默认值或猜测字段。非法 JSON、重复键、超安全范围整数及未知规则由后端拒绝，不会自动修复、补默认或改类型。结果必须严格符合 Schema；输出格式错误会终止整次运行，不会转为可继续的失败项。每项对象 64000 UTF-8 字节以内、最多 20000 值、16 层嵌套、数值有限，整数须在 ±9007199254740991 内。此处仅填写草稿，未保存、不调用模型、不执行代码或 Dify。
      </p>
      <div className="secondary">
        <button
          type="button"
          disabled={props.disabled || !empty}
          onClick={() => props.onChange(EXAMPLE)}
        >
          填入对象 Schema 示例
        </button>
        <span className="hint">仅示例，需按实际需求修改，不代表已确认业务字段。</span>
      </div>
    </section>
  );
}
