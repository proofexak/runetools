/**
 * Session-log parsing, same rules as lib/logreport.parse_lines: blank lines are ignored;
 * a line that isn't a JSON object with an "event" counts as bad and is skipped.
 *
 * Tailing adds one rule: only whole lines (ending in "\n") are consumed. A line still
 * being written stays for the next read; a line cut short by a hard kill is never
 * finished and so is never read — the same outcome as logreport skipping it.
 */

export interface LogEvent {
  ts: string;
  event: string;
  session?: string;
  bot?: string;
  [key: string]: unknown;
}

const NL = 0x0a;

/** The complete-lines prefix of a chunk read from a log file, and its length in bytes. */
export function completeLines(chunk: Buffer): { text: string; bytes: number } {
  const last = chunk.lastIndexOf(NL);
  if (last < 0) return { text: "", bytes: 0 };
  return { text: chunk.subarray(0, last + 1).toString("utf8"), bytes: last + 1 };
}

// Python's json.dumps writes NaN / Infinity, which JSON.parse refuses.
const PY_NON_FINITE = /(?<=[:[,]\s*)(?:NaN|-?Infinity)(?=\s*[,\]}])/g;

function parseRecord(line: string): unknown {
  try {
    return JSON.parse(line);
  } catch {
    return JSON.parse(line.replace(PY_NON_FINITE, "null"));
  }
}

export function parseLines(text: string): { events: LogEvent[]; bad: number } {
  const events: LogEvent[] = [];
  let bad = 0;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    let record: unknown;
    try {
      record = parseRecord(line);
    } catch {
      bad++;
      continue;
    }
    if (record && typeof record === "object" && !Array.isArray(record) && "event" in record &&
        typeof (record as LogEvent).ts === "string") {
      events.push(record as LogEvent);
    } else {
      bad++;
    }
  }
  return { events, bad };
}

/** "2026-10-05T15:17:12.569" → milliseconds, reading the naive time as UTC (only differences matter). */
export function tsMillis(ts: string): number {
  return Date.parse(ts.replace(" ", "T") + (/[zZ]|[+-]\d\d:\d\d$/.test(ts) ? "" : "Z"));
}
