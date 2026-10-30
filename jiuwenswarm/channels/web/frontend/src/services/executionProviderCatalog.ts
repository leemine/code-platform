/** Public metadata only. Runtime admission and credentials stay on the server. */
export interface ExecutionProviderOption {
  id: string;
  label: string;
  available: boolean;
  modes: string[];
  reason: string | null;
}

export function parseExecutionProviderCatalog(value: unknown): ExecutionProviderOption[] {
  const rows: unknown = typeof value === 'string' ? JSON.parse(value) : value;
  if (!Array.isArray(rows) || !rows.length) throw new Error('Invalid execution provider catalog');
  const seen = new Set<string>();
  return rows.map((row) => {
    if (!row || typeof row.id !== 'string' || !row.id || seen.has(row.id)
      || typeof row.label !== 'string' || !row.label || typeof row.available !== 'boolean'
      || !Array.isArray(row.modes) || !row.modes.every((mode: unknown) => typeof mode === 'string')) {
      throw new Error('Invalid execution provider option');
    }
    seen.add(row.id);
    return { id: row.id, label: row.label, available: row.available, modes: row.modes,
      reason: ['unavailable', 'ambiguous', 'unsupported_mode'].includes(row.reason) ? row.reason : null };
  });
}
