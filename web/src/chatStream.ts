import type { StreamEvent } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";
const STREAM_PATH = import.meta.env.VITE_CHAT_STREAM_PATH ?? "/api/chat/stream";
const DATA_SOURCE_ID = import.meta.env.VITE_DATA_SOURCE_ID ?? "demo-acts-1-3";

async function* readEventStream(response: Response): AsyncGenerator<StreamEvent> {
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  if (!response.body) throw new Error("浏览器未收到流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const records = buffer.split(/\r?\n\r?\n/);
    buffer = done ? "" : records.pop() ?? "";
    for (const record of records) {
      const data = record
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue;
      try {
        yield JSON.parse(data) as StreamEvent;
      } catch {
        throw new Error("流式响应格式无效");
      }
    }
    if (done) break;
  }
}

export async function* streamChat(
  message: string,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}${STREAM_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, data_source_id: DATA_SOURCE_ID }),
    signal,
  });
  yield* readEventStream(response);
}
