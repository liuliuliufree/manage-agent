import type { ActId, StreamEvent } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";
const STREAM_PATH = import.meta.env.VITE_CHAT_STREAM_PATH ?? "/api/chat/stream";

function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

async function* readEventStream(response: Response): AsyncGenerator<StreamEvent> {
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  if (!response.body) throw new Error("浏览器未收到流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const records = buffer.split(/\r?\n\r?\n|\r?\n/);
    buffer = done ? "" : records.pop() ?? "";
    for (const record of records) {
      const line = record.trim();
      if (!line || line.startsWith(":")) continue;
      const raw = line.startsWith("data:") ? line.slice(5).trim() : line;
      if (raw === "[DONE]") { yield { type: "done" }; return; }
      try { yield JSON.parse(raw) as StreamEvent; }
      catch { throw new Error("流式响应格式无效"); }
    }
    if (done) break;
  }
}

async function* requestStream(message: string, signal: AbortSignal) {
  const response = await fetch(`${API_BASE}${STREAM_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, scenario_id: "demo-acts-1-3" }),
    signal,
  });
  yield* readEventStream(response);
}

const DEMO_ANSWER = `我已按照当前场景核对经营目标与边界：只使用已授权数据，并强制执行营销许可、触达频次、敏感状态与初步适当性校验。高分不能覆盖任何硬规则。\n\n机会比较中，“家庭责任变化与重疾保障缺口”综合表现最优。它覆盖 86 名机会客户，近期主动保障行为更集中，适合先从保障检视切入；另外两个方向分别覆盖 50 名和 25 名客户。\n\n围绕推荐机会完成圈客后，漏斗为：86 名机会客户 → 41 名可经营客户 → 12 名高优先级客户。其余客户因未授权、近期频繁触达、明确拒绝、敏感状态或初步适当性未通过而被排除。\n\n建议先向高优先级客户提供保障现状检视，不直接推荐具体产品。具体产品适当性和销售沟通仍需由具备资格的专业人员确认。\n\n以上结果来自 2026-09-15 基准时点的合成演示数据；预计响应、成本和综合分不代表生产预测。`;

async function* mockStream(signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const acts: Array<{ act: ActId; detail: string }> = [
    { act: 1, detail: "已核对经营目标、授权范围与合规边界" },
    { act: 2, detail: "已比较 3 个候选机会并形成推荐" },
    { act: 3, detail: "已完成硬规则筛选与客户优先级排序" },
  ];
  for (const item of acts) {
    yield { type: "act", ...item, state: "running" };
    await delay(360, signal);
    yield { type: "act", ...item, state: "complete" };
  }
  for (const token of DEMO_ANSWER.match(/.{1,4}/gs) ?? []) {
    await delay(20, signal);
    yield { type: "delta", delta: token };
  }
  yield { type: "done", degraded: true };
}

export function streamChat(message: string, signal: AbortSignal) {
  return API_BASE ? requestStream(message, signal) : mockStream(signal);
}

export const isDemoMode = !API_BASE;
