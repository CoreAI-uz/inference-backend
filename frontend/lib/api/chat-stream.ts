// SSE chat stream consumer: POST + fetch + ReadableStream (not EventSource — we need
// POST, cookies, and AbortController for stop). Yields the named events distinctly so
// the UI can render queued / rate-limit / error as three separate, honest states.

import type { ChatEvent, ChatRequestMessage, ReasoningEffort } from "./types";

export interface StreamChatBody {
  model: string;
  conversation_id?: string;
  // New turn / edit: the user text. Omit for regenerate.
  user_content?: string;
  // Attach point. Include (even as null, to edit the first message) to branch
  // explicitly; omit for a plain new turn (server uses the active leaf).
  parent_id?: string | null;
  reasoning_effort?: ReasoningEffort;
  thinking?: boolean;
  // Legacy new-turn shape; server only reads the last user message from it.
  messages?: ChatRequestMessage[];
}

export async function* streamChat(
  body: StreamChatBody,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const resp = await fetch("/api/chat/completions", {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  // Pre-flight errors (429 rate limit, 404 model, 413 input) arrive as JSON, not SSE.
  if (!resp.ok) {
    let b: Record<string, unknown> = {};
    try {
      b = await resp.json();
    } catch {
      /* ignore */
    }
    yield {
      type: "error",
      code: (b.error as string) ?? "error",
      message: (b.message as string) ?? resp.statusText,
      retry_after: b.retry_after as number | undefined,
    };
    return;
  }
  if (!resp.body) return;

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        if (!block.trim()) continue;
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        try {
          yield { type: event, ...JSON.parse(data) } as ChatEvent;
        } catch {
          /* skip malformed frame */
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
