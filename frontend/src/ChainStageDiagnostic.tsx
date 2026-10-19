export type ChainDiagnostic = {
  code:
    | 'stage_configuration'
    | 'calculation_scope'
    | 'wrapper_contract'
    | 'stage_order';
  stage_position: number;
  stage_count: number;
};

export function isChainDiagnostic(value: unknown): value is ChainDiagnostic {
  try {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      return false;
    }

    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      return false;
    }

    const requiredKeys = ['code', 'stage_position', 'stage_count'];
    const ownKeys = Reflect.ownKeys(value);

    if (ownKeys.length !== requiredKeys.length) {
      return false;
    }

    for (const key of ownKeys) {
      if (typeof key !== 'string' || !requiredKeys.includes(key)) {
        return false;
      }
    }

    for (const key of requiredKeys) {
      if (!ownKeys.includes(key)) {
        return false;
      }
    }

    const codeDescriptor = Object.getOwnPropertyDescriptor(value, 'code');
    const positionDescriptor = Object.getOwnPropertyDescriptor(value, 'stage_position');
    const countDescriptor = Object.getOwnPropertyDescriptor(value, 'stage_count');

    if (
      !codeDescriptor ||
      !positionDescriptor ||
      !countDescriptor ||
      !Object.prototype.hasOwnProperty.call(codeDescriptor, 'value') ||
      !Object.prototype.hasOwnProperty.call(positionDescriptor, 'value') ||
      !Object.prototype.hasOwnProperty.call(countDescriptor, 'value')
    ) {
      return false;
    }

    const code = codeDescriptor.value;
    const stagePosition = positionDescriptor.value;
    const stageCount = countDescriptor.value;

    if (
      code !== 'stage_configuration' &&
      code !== 'calculation_scope' &&
      code !== 'wrapper_contract' &&
      code !== 'stage_order'
    ) {
      return false;
    }

    if (
      typeof stageCount !== 'number' ||
      !Number.isSafeInteger(stageCount) ||
      stageCount < 2 ||
      stageCount > 8
    ) {
      return false;
    }

    if (
      typeof stagePosition !== 'number' ||
      !Number.isSafeInteger(stagePosition) ||
      stagePosition < 1 ||
      stagePosition > stageCount
    ) {
      return false;
    }

    return true;
  } catch {
    return false;
  }
}

const STAGE_EXPLANATIONS: Record<ChainDiagnostic['code'], string> = {
  stage_configuration:
    '该步须有唯一前步result输入和唯一文字或数值result输出，额外输入和执行设置需要另行确认',
  calculation_scope: '该步原计算超出当前纯Python计算范围，需复核函数、调用和返回约定',
  wrapper_contract: '该步原封装无法完整重建，需复核手改封装，不会覆盖',
  stage_order: '该步原声明次序或总数与当前计算链不符，需核对次序',
};

type ChainStageDiagnosticProps = {
  diagnostic: unknown;
};

export default function ChainStageDiagnostic({ diagnostic }: ChainStageDiagnosticProps) {
  if (!isChainDiagnostic(diagnostic)) {
    return null;
  }

  return (
    <div className='chain-stage-diagnostic'>
      <p role='alert'>
        第{diagnostic.stage_position}步（共{diagnostic.stage_count}步）的方案准备未通过
      </p>
      <p>{STAGE_EXPLANATIONS[diagnostic.code]}</p>
      <p>这是本机准备阶段的定位，不是 Dify 运行中的 failed_stage；没有改稿、执行代码或自动重试。</p>
    </div>
  );
}
