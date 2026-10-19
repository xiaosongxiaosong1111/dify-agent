export type VersionNodeChange = {
  change: 'added' | 'removed' | 'changed' | 'moved';
  current_path: number[] | null;
  historical_path: number[] | null;
  before_type: string | null;
  after_type: string | null;
  fields: string[];
};

export type VersionNodeDetails = {
  scope: 'node_identity_and_fields_only';
  items: VersionNodeChange[];
  total: number;
  omitted: number;
  limit: 30;
};

const CHANGE_LABELS: Record<VersionNodeChange['change'], string> = {
  added: '新增',
  removed: '移除',
  changed: '更改',
  moved: '位置变化',
};

const ERROR_MESSAGE = '节点明细暂不可用，请重新比较；未恢复。';

function isSafeIntegerInRange(value: unknown, min: number, max: number): value is number {
  return (
    typeof value === 'number' &&
    Number.isSafeInteger(value) &&
    value >= min &&
    value <= max
  );
}

function isNodePath(value: unknown): value is number[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 21) {
    return false;
  }
  const segments: unknown[] = value;
  for (const segment of segments) {
    if (!isSafeIntegerInRange(segment, 1, 2000)) {
      return false;
    }
  }
  return true;
}

function isNullableNodePath(value: unknown): value is number[] | null {
  return value === null || isNodePath(value);
}

function isChangeKind(value: unknown): value is VersionNodeChange['change'] {
  return (
    value === 'added' ||
    value === 'removed' ||
    value === 'changed' ||
    value === 'moved'
  );
}

function isCorrespondingType(value: unknown, path: number[] | null): boolean {
  if (path === null) {
    return value === null;
  }
  return typeof value === 'string' && value.length > 0 && value.length <= 60;
}

function isFieldLabels(value: unknown): value is string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 20) {
    return false;
  }
  const labels: unknown[] = value;
  const seen = new Set<string>();
  for (const label of labels) {
    if (
      typeof label !== 'string' ||
      label.length === 0 ||
      label.length > 60 ||
      seen.has(label)
    ) {
      return false;
    }
    seen.add(label);
  }
  return true;
}

function isVersionNodeChange(value: unknown): value is VersionNodeChange {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }

  const record = value as Record<string, unknown>;
  const change = record.change;
  if (!isChangeKind(change)) {
    return false;
  }

  const currentPath = record.current_path;
  const historicalPath = record.historical_path;
  if (!isNullableNodePath(currentPath) || !isNullableNodePath(historicalPath)) {
    return false;
  }

  if (currentPath === null && historicalPath === null) {
    return false;
  }
  if (change === 'added' && (currentPath !== null || historicalPath === null)) {
    return false;
  }
  if (change === 'removed' && (currentPath === null || historicalPath !== null)) {
    return false;
  }
  if (
    (change === 'changed' || change === 'moved') &&
    (currentPath === null || historicalPath === null)
  ) {
    return false;
  }

  if (!isCorrespondingType(record.before_type, currentPath)) {
    return false;
  }
  if (!isCorrespondingType(record.after_type, historicalPath)) {
    return false;
  }
  if (!isFieldLabels(record.fields)) {
    return false;
  }

  return true;
}

export function isVersionNodeDetails(value: unknown): value is VersionNodeDetails {
  try {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      return false;
    }

    const record = value as Record<string, unknown>;
    if (record.scope !== 'node_identity_and_fields_only') {
      return false;
    }
    if (record.limit !== 30) {
      return false;
    }

    const total = record.total;
    if (!isSafeIntegerInRange(total, 0, 4000)) {
      return false;
    }

    if (!Array.isArray(record.items)) {
      return false;
    }
    const items: unknown[] = record.items;
    if (items.length > 30 || items.length > total) {
      return false;
    }

    if (!isSafeIntegerInRange(record.omitted, 0, 4000)) {
      return false;
    }
    if (record.omitted !== total - items.length) {
      return false;
    }

    for (const item of items) {
      if (!isVersionNodeChange(item)) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  }
}

function formatPath(path: number[]): string {
  return path
    .map((position, index) =>
      index === 0
        ? `第${position}个节点`
        : `容器内第${position}个节点`,
    )
    .join(' → ');
}

function describeTypes(item: VersionNodeChange): string | null {
  if (item.before_type !== null && item.after_type !== null) {
    if (item.before_type === item.after_type) {
      return null;
    }
    return `类型：${item.before_type} → ${item.after_type}`;
  }
  if (item.before_type !== null) {
    return `当前类型：${item.before_type}`;
  }
  if (item.after_type !== null) {
    return `恢复后类型：${item.after_type}`;
  }
  return null;
}

export default function VersionNodeChanges({ details }: { details: unknown }) {
  if (!isVersionNodeDetails(details)) {
    return (
      <div className='version-node-changes version-node-changes-error'>
        {ERROR_MESSAGE}
      </div>
    );
  }

  try {
    const total = details.total;
    const omitted = details.omitted;
    const items = details.items;

    return (
      <details
        className='version-node-changes'
        style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
      >
        <summary>查看节点变更明细（{total}项）</summary>
        <div>
          {total === 0 ? (
            <p>无可逐项列出的节点变化；连线/其它流程变化另看摘要。</p>
          ) : null}
          {omitted > 0 ? (
            <p>
              只展示前{items.length}项，另有{omitted}项未列出；未列出不代表未变化。
            </p>
          ) : null}
          {items.length > 0 ? (
            <ol>
              {items.map((item, index) => {
                const typeText = describeTypes(item);
                return (
                  <li key={index} className='version-node-change'>
                    <div>
                      <strong>{CHANGE_LABELS[item.change]}</strong>
                    </div>
                    <div>
                      {`当前位置：${
                        item.current_path === null
                          ? '无'
                          : formatPath(item.current_path)
                      }`}
                    </div>
                    <div>
                      {`恢复后位置：${
                        item.historical_path === null
                          ? '无'
                          : formatPath(item.historical_path)
                      }`}
                    </div>
                    {typeText === null ? null : <div>{typeText}</div>}
                    <div>字段：{item.fields.join('、')}</div>
                  </li>
                );
              })}
            </ol>
          ) : null}
          <p>位置和字段变化不证明业务影响、静态有效或运行通过。</p>
        </div>
      </details>
    );
  } catch {
    return (
      <div className='version-node-changes version-node-changes-error'>
        {ERROR_MESSAGE}
      </div>
    );
  }
}
