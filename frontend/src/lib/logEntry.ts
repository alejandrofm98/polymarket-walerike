const LOG_ENTRY_SEPARATOR = "\t";
const LEGACY_LOG_ENTRY_PATTERN = /^(?<time>(?:\d{1,2}:){1,2}\d{2}(?:\s?[AP]M)?)\s+(?<message>.+)$/i;

export function formatLogEntry(message: string, timestamp = new Date()): string {
  return `${timestamp.toLocaleTimeString()}${LOG_ENTRY_SEPARATOR}${message}`;
}

export function parseLogEntry(entry: string): { time: string; message: string } {
  const separatorIndex = entry.indexOf(LOG_ENTRY_SEPARATOR);
  if (separatorIndex >= 0) {
    return {
      time: entry.slice(0, separatorIndex),
      message: entry.slice(separatorIndex + LOG_ENTRY_SEPARATOR.length),
    };
  }

  const match = LEGACY_LOG_ENTRY_PATTERN.exec(entry);
  if (match?.groups) {
    return {
      time: match.groups.time,
      message: match.groups.message,
    };
  }

  return { time: "", message: entry };
}
