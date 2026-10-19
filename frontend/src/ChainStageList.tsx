type StageType = "string" | "number";

type ChainStage = {
  position: number;
  input_type: StageType;
  value_type: StageType;
  original_code_sha256: string;
  code_sha256: string;
};

const STAGE_FIELDS = [
  "position",
  "input_type",
  "value_type",
  "original_code_sha256",
  "code_sha256",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStageType(value: unknown): value is StageType {
  return value === "string" || value === "number";
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function hasExactKeys(
  record: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const keys = Reflect.ownKeys(record);
  if (keys.length !== expected.length) return false;
  for (const key of keys) {
    if (typeof key !== "string" || !expected.includes(key)) return false;
  }
  for (const key of expected) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) return false;
  }
  return true;
}

function validateStages(value: unknown): value is ChainStage[] {
  try {
    if (!Array.isArray(value)) return false;
    const length = value.length;
    if (!Number.isSafeInteger(length) || length < 2 || length > 8) return false;

    const arrayKeys = Reflect.ownKeys(value);
    if (arrayKeys.length !== length + 1) return false;
    if (!arrayKeys.includes("length")) return false;
    for (let index = 0; index < length; index += 1) {
      if (!arrayKeys.includes(String(index))) return false;
    }

    let previousValueType: StageType | undefined;
    for (let index = 0; index < length; index += 1) {
      const item = value[index];
      if (!isRecord(item) || !hasExactKeys(item, STAGE_FIELDS)) return false;

      const position = item.position;
      const inputType = item.input_type;
      const valueType = item.value_type;
      const originalHash = item.original_code_sha256;
      const codeHash = item.code_sha256;

      if (
        typeof position !== "number" ||
        !Number.isSafeInteger(position) ||
        position !== index + 1
      ) {
        return false;
      }
      if (!isStageType(inputType) || !isStageType(valueType)) return false;
      if (index === 0) {
        if (inputType !== "string") return false;
      } else if (inputType !== previousValueType) {
        return false;
      }
      if (!isSha256(originalHash) || !isSha256(codeHash)) return false;

      previousValueType = valueType;
    }

    return true;
  } catch {
    return false;
  }
}

export function isChainStages(value: unknown): boolean {
  return validateStages(value);
}

function typeLabel(value: StageType): string {
  return value === "string" ? "文字" : "数值";
}

export default function ChainStageList({ stages }: { stages: unknown }) {
  if (!validateStages(stages)) {
    return <p className="hint">计算步骤明细暂不可用，请重新准备完整方案。</p>;
  }

  return (
    <details className="chain-stage-list">
      <summary>查看各步计算与代码摘要</summary>
      {stages.map((stage) => (
        <div key={stage.position}>
          <p>{`第${stage.position}步：${typeLabel(stage.input_type)} → ${typeLabel(stage.value_type)}`}</p>
          <p>{`原代码摘要：${stage.original_code_sha256.slice(0, 12)}`}</p>
          <p>{`封装代码摘要：${stage.code_sha256.slice(0, 12)}`}</p>
        </div>
      ))}
      <p className="hint">
        失败记录中的 failed_stage 为1基计算步骤；该项后续步骤只传递失败记录，不再执行原计算。成功项 failed_stage 为 null。仍须复核完整计划，摘要不证明代码运行、平台或业务通过。
      </p>
    </details>
  );
}
