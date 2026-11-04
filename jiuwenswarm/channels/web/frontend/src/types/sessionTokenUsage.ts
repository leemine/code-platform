export interface SessionTokenUsageCategory {
  input_tokens: number | null;
  output_tokens: number | null;
  input_calls: number | null;
  output_calls: number | null;
  calls_total: number | null;
  total_tokens?: number;
  cached_input_tokens?: number;
  reasoning_output_tokens?: number;
  cache_write_input_tokens?: number;
}

export interface SessionTokenUsageSnapshot {
  schema_version: 1;
  revision: number;
  session_id: string;
  scope?: 'native';
  main: SessionTokenUsageCategory;
  others: SessionTokenUsageCategory;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function isNullableCount(value: unknown): value is number | null {
  return value === null || isCount(value);
}

function isCategory(value: unknown): value is SessionTokenUsageCategory {
  if (!isRecord(value)) return false;
  return (
    isNullableCount(value.input_tokens)
    && isNullableCount(value.output_tokens)
    && isNullableCount(value.input_calls)
    && isNullableCount(value.output_calls)
    && isNullableCount(value.calls_total)
    && (value.input_calls === null || value.calls_total === null || value.input_calls <= value.calls_total)
    && (value.output_calls === null || value.calls_total === null || value.output_calls <= value.calls_total)
    && ['total_tokens', 'cached_input_tokens', 'reasoning_output_tokens', 'cache_write_input_tokens']
      .every((key) => value[key] === undefined || isCount(value[key]))
  );
}

export function parseSessionTokenUsageSnapshot(value: unknown): SessionTokenUsageSnapshot | null {
  if (
    !isRecord(value)
    || value.schema_version !== 1
    || !isCount(value.revision)
    || typeof value.session_id !== 'string'
    || !value.session_id
    || (value.scope !== undefined && value.scope !== 'native')
    || !isCategory(value.main)
    || !isCategory(value.others)
  ) {
    return null;
  }
  return value as unknown as SessionTokenUsageSnapshot;
}
