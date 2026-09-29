/**
 * sanchopanza compaction for Claude Code, as a function-hook module (early access).
 *
 * On `session.compact` it hands the conversation to `sanchopanza compact` and, when that
 * frees enough, returns the same messages with old tool results replaced by one-line stubs
 * (the full text is archived on disk and the stub names the file). On anything else - the
 * command missing, a non-zero exit (3: below the minimum reduction), a timeout, output it
 * cannot read, a broken tool_use/tool_result pair - it logs why and calls `next(event)`, so
 * Claude Code writes its normal summary. It never fails silently and never leaves the
 * conversation half-edited.
 *
 * Enable with CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 and a plugin whose hooks/hooks.json is
 * {"modules": ["./compact_hook.ts"]} (`sanchopanza install --compact` writes one).
 *
 * Environment:
 *   SANCHOPANZA_COMPACT_COMMAND  the command, split on whitespace (no shell); default
 *                                "sanchopanza compact --stdin"
 *   SANCHOPANZA_COMPACT_MARKER   a file to append one line per event to, for checking that
 *                                the module loaded and what it did (off when unset)
 *   SANCHOPANZA_COMPACT_AT_PERCENT  compact by itself when a main-thread turn ends with the
 *                                context at or above this percentage (off when unset or 0).
 *                                The autopilot sets 60, with the command's arm set to `mask`.
 *
 * The automatic trigger follows fast-jev-compaction's `turn.complete` hook (MIT): read
 * `$.session.usage().context.percent` after each turn and call `$.session.compact()`, which
 * raises `session.compact` with trigger `plugin` through every hook but the calling one (so
 * this module's own `session.compact` handler runs), with an in-flight guard. Subagent turns
 * (`agentId` set) and interrupted turns never trigger it. Compacting between turns is the one
 * moment a rewrite is cheap: the next request pays the new prefix once, as it would after the
 * built-in compaction.
 *
 * The event and message shapes follow the declarations Claude Code 2.1.274 generated, as
 * shipped by fast-jev-compaction (MIT, github.com/tamaratran/fast-jev-compaction). The
 * transcript is converted to Messages-API messages for the command and back; a message the
 * command did not change is returned as the engine's own object without its `handle` (see
 * `detached()`), every other field kept.
 *
 * Checked against Claude Code 2.1.282 on 2026-09-28, once: the module loads through
 * `--plugin-dir` and through the settings `sanchopanza install --compact` writes, and a
 * `/compact` on a resumed `-p` session ran the command (rules arm) and left the transcript with
 * the stub in place of the result, with no model call. Not checked: `auto` compaction, a
 * subagent's transcript (`agentId`), or a long session.
 */

type ToolUse = {
  tool_use_id: string;
  tool: string;
  input: Record<string, unknown>;
  text?: string;
  isError?: true;
  result?: unknown;
};

type ToolResult = { tool_use_id: string; text: string; isError: boolean; result?: unknown };

type SessionMessage = {
  role: 'user' | 'assistant';
  text: string;
  toolUses: ToolUse[];
  toolResults?: ToolResult[];
  handle?: string;
};

type Block = Record<string, unknown>;
type ApiMessage = { role: string; content: Block[]; sanchopanza_index?: number };

type Host = {
  env: { get: (name: string) => Promise<string | undefined> };
  fs: { read: (path: string) => Promise<string>; write: (path: string, text: string) => Promise<void> };
  process: {
    run: (
      argv: readonly string[],
      init?: { stdin?: string; timeoutMs?: number },
    ) => Promise<{ exitCode: number; stdout: string; stderr: string }>;
  };
  session: {
    id: () => Promise<string>;
    usage?: () => Promise<{ context: { percent?: number } }>;
    compact?: (args?: unknown) => Promise<unknown>;
  };
  ui: { log: (text: string) => void };
};

type CompactEvent = { trigger: string; messages: readonly SessionMessage[] };
type TurnEvent = { agentId?: string; reason?: string; aborted?: boolean };
type Next<E, R> = (event: E) => Promise<R>;

const DEFAULT_COMMAND = 'sanchopanza compact --stdin';
const TIMEOUT_MS = 180_000;
const PREFIX = 'sanchopanza compact';

function apiBlocks(message: SessionMessage): Block[] {
  const blocks: Block[] = [];
  for (const result of message.toolResults ?? []) {
    blocks.push({
      type: 'tool_result',
      tool_use_id: result.tool_use_id,
      content: result.text,
      is_error: result.isError === true,
    });
  }
  if (message.text) blocks.push({ type: 'text', text: message.text });
  for (const tool of message.toolUses ?? []) {
    blocks.push({ type: 'tool_use', id: tool.tool_use_id, name: tool.tool, input: tool.input });
  }
  return blocks;
}

export function toApi(messages: readonly SessionMessage[]): ApiMessage[] {
  return messages.map((message, index) => ({
    role: message.role,
    content: apiBlocks(message),
    sanchopanza_index: index,
  }));
}

function rebuilt(output: ApiMessage, original: SessionMessage | undefined): SessionMessage {
  const uses = new Map((original?.toolUses ?? []).map((t) => [t.tool_use_id, t]));
  const text = output.content
    .filter((b) => b.type === 'text')
    .map((b) => String(b.text ?? ''))
    .join('\n');
  const toolUses: ToolUse[] = output.content
    .filter((b) => b.type === 'tool_use')
    .map((b) => {
      const id = String(b.id);
      return uses.get(id) ?? { tool_use_id: id, tool: String(b.name), input: (b.input ?? {}) as Record<string, unknown> };
    });
  const results = output.content
    .filter((b) => b.type === 'tool_result')
    .map((b) => ({
      tool_use_id: String(b.tool_use_id),
      text: typeof b.content === 'string' ? b.content : JSON.stringify(b.content ?? ''),
      isError: b.is_error === true,
    }));
  const message: SessionMessage = { role: output.role === 'assistant' ? 'assistant' : 'user', text, toolUses };
  if (results.length > 0) message.toolResults = results;
  return message;
}

/** A copy of the engine's message without its `handle`, every other field kept. */
export function detached(message: SessionMessage): SessionMessage {
  const { handle: _handle, ...rest } = message;
  return rest;
}

/**
 * Output messages back onto the engine's. An unchanged message keeps every field of the
 * engine's own object except `handle`: a returned handle makes Claude Code chain the entries it
 * writes after the compaction to the old transcript entry, so a `--resume` rebuilds the history
 * from before the compaction, unmasked (found 2026-09-28: docs/results/2026-09-28-context-lean).
 */
export function fromApi(output: readonly ApiMessage[], input: readonly SessionMessage[]): SessionMessage[] {
  return output.map((message) => {
    const index = message.sanchopanza_index;
    const original = typeof index === 'number' ? input[index] : undefined;
    if (original && JSON.stringify(message.content) === JSON.stringify(apiBlocks(original))) {
      return detached(original);
    }
    return rebuilt(message, original);
  });
}

function orphans(messages: readonly SessionMessage[]): Set<string> {
  const uses = new Set<string>();
  const results = new Set<string>();
  for (const message of messages) {
    for (const tool of message.toolUses ?? []) uses.add(tool.tool_use_id);
    for (const result of message.toolResults ?? []) results.add(result.tool_use_id);
  }
  const alone = [...uses].filter((id) => !results.has(id));
  return new Set([...alone, ...[...results].filter((id) => !uses.has(id))]);
}

/**
 * No tool_use without its tool_result, nor the reverse, beyond what the input already had
 * (a call still in flight when compaction starts is the engine's own state).
 */
export function paired(output: readonly SessionMessage[], input: readonly SessionMessage[]): boolean {
  const before = orphans(input);
  return [...orphans(output)].every((id) => before.has(id));
}

async function mark($: Host, line: string): Promise<void> {
  try {
    const path = await $.env.get('SANCHOPANZA_COMPACT_MARKER');
    if (!path) return;
    const before = (await $.fs.read(path).catch(() => '')) ?? '';
    await $.fs.write(path, `${before}${new Date().toISOString()} ${line}\n`);
  } catch {
    // a debugging aid must never change what the hook does
  }
}

function say($: Host, text: string): void {
  const line = `${PREFIX}: ${text}`;
  try {
    $.ui.log(line);
  } catch {
    // no transcript to draw on
  }
  try {
    console.error(line);
  } catch {
    // no console in this runtime
  }
}

async function prune($: Host, event: CompactEvent): Promise<SessionMessage[]> {
  const command = ((await $.env.get('SANCHOPANZA_COMPACT_COMMAND')) || DEFAULT_COMMAND).trim();
  const session = await $.session.id().catch(() => 'session');
  const safe = session.replace(/[^A-Za-z0-9_.-]/g, '_') || 'session';
  const out = `.sanchopanza/compact-${safe}.json`;
  const argv = [...command.split(/\s+/), '--session', safe, '--out', out];
  const payload = JSON.stringify({ session: safe, messages: toApi(event.messages) });
  const run = await $.process.run(argv, { stdin: payload, timeoutMs: TIMEOUT_MS });
  if (run.exitCode !== 0) {
    const why = run.stderr.trim().slice(0, 600) || 'no message';
    throw new Error(`\`${command}\` exited ${run.exitCode}: ${why}`);
  }
  const raw = await $.fs.read(out);
  // The file is a copy of the conversation: blank it as soon as it is read.
  await $.fs.write(out, '{}').catch(() => undefined);
  const parsed = JSON.parse(raw) as { messages?: ApiMessage[]; report?: Record<string, unknown> };
  if (!Array.isArray(parsed.messages)) throw new Error('the command returned no messages');
  const messages = fromApi(parsed.messages, event.messages);
  if (!paired(messages, event.messages)) throw new Error('the pruned conversation breaks a tool_use/tool_result pair');
  const report = parsed.report ?? {};
  const reduction = Math.round(Number(report.reduction ?? 0) * 100);
  say($, `kept ${messages.length}/${event.messages.length} messages, ${reduction}% freed, no summary (${JSON.stringify(report.reasons ?? {})})`);
  return messages;
}

/** The percentage from the environment, or 0 (off) when unset or not a number in (0, 100]. */
export function threshold(raw: string | undefined): number {
  const value = Number(raw ?? '');
  return Number.isFinite(value) && value > 0 && value <= 100 ? value : 0;
}

/** Whether a finished turn should compact: main thread, not interrupted, at the threshold. */
export function shouldCompact(event: TurnEvent, percent: number | undefined, at: number): boolean {
  if (at <= 0 || event.agentId || event.aborted || event.reason === 'aborted') return false;
  return typeof percent === 'number' && percent >= at;
}

export function register(on: (...args: unknown[]) => unknown, _options?: unknown): void {
  let compacting = false;

  on('turn.complete', async ($: Host, event: TurnEvent, next: Next<TurnEvent, unknown>) => {
    if (compacting) return next(event);
    try {
      const at = threshold(await $.env.get('SANCHOPANZA_COMPACT_AT_PERCENT'));
      // `$.session.usage` and `$.session.compact` are only ever called, never tested as values:
      // Claude Code's hook compiler refuses the whole module otherwise (a debug-log line is the
      // only trace). A runtime without them throws here, and the catch below says so.
      if (at <= 0) return next(event);
      const { context } = await $.session.usage!();
      if (!shouldCompact(event, context.percent, at)) return next(event);
      compacting = true;
      await mark($, `auto compact at ${context.percent}% (threshold ${at}%)`);
      await $.session.compact!();
    } catch (error) {
      say($, `auto compact skipped (${error instanceof Error ? error.message : String(error)})`);
    } finally {
      compacting = false;
    }
    return next(event);
  });

  on('session.start', async ($: Host, event: unknown, next: Next<unknown, unknown>) => {
    await mark($, 'loaded');
    return next(event);
  });

  on('session.compact', async ($: Host, event: CompactEvent, next: Next<CompactEvent, unknown>) => {
    await mark($, `session.compact trigger=${event.trigger} messages=${event.messages.length}`);
    if (event.trigger === 'precompute') return next(event); // decide once, when it is real
    try {
      const messages = await prune($, event);
      await mark($, `pruned ${event.messages.length} -> ${messages.length}`);
      return { messages };
    } catch (error) {
      const why = error instanceof Error ? error.message : String(error);
      say($, `fallback to the built-in summary (${why})`);
      await mark($, `fallback: ${why}`);
      return next(event);
    }
  });
}
