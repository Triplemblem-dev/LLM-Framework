export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${bytes} B`;
}

export function formatContext(length: number | null): string {
  if (!length) return "unknown";
  if (length >= 1000) return `${Math.round(length / 1000)}K`;
  return `${length}`;
}
