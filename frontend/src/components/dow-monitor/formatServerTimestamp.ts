export function formatServerTimestamp(value: number | string | null | undefined) {
  if (value == null || value === '') return null
  const parsed = new Date(value)
  if (!Number.isFinite(parsed.getTime())) return String(value)
  return `${parsed.toISOString().slice(0, 16).replace('T', ' ')}Z`
}
