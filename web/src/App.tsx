import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { streamChat } from "./chatStream";
import type { ChatMessage, RunStep, StreamEvent, TurnOutput } from "./types";

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "告诉我你的经营目标或需要核对的问题。我会根据任务自主选择能力，并把实际执行轨迹展示在这里。当前接入的是合成演示数据。",
};

function SendIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4.6 14-2.8-5.4L5 12Z" /><path d="m11.6 13.6 3.5-3.8" /></svg>;
}

function updateTool(steps: RunStep[], event: Extract<StreamEvent, { type: "tool" }>) {
  const next = [...steps];
  const index = next.findIndex((step) => step.id === event.id);
  const previous = index === -1 ? undefined : next[index];
  const step: RunStep = {
    id: event.id,
    name: event.name,
    label: event.label ?? event.name,
    turn: event.turn,
    detail: event.detail,
    arguments: event.arguments !== undefined ? event.arguments : previous?.arguments,
    result: event.result !== undefined ? event.result : previous?.result,
    state: event.state,
  };
  if (index === -1) next.push(step);
  else next[index] = { ...next[index], ...step };
  return next;
}

function updateTurnOutput(outputs: TurnOutput[], event: Extract<StreamEvent, { type: "delta" }>) {
  const next = [...outputs];
  const index = next.findIndex((output) => output.turn === event.turn);
  if (index === -1) next.push({ turn: event.turn, content: event.delta });
  else next[index] = { ...next[index], content: next[index].content + event.delta };
  return next;
}

function latestTurnText(message: ChatMessage) {
  const outputs = message.turnOutputs ?? [];
  return outputs.length ? outputs[outputs.length - 1].content : "";
}

function updateEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  if (event.type === "trace") return { ...message, traceId: event.trace_id };
  if (event.type === "turn") return { ...message, activeTurn: event.turn };
  if (event.type === "tool") return { ...message, steps: updateTool(message.steps ?? [], event) };
  if (event.type === "delta") {
    return {
      ...message,
      turnOutputs: updateTurnOutput(message.turnOutputs ?? [], event),
    };
  }
  if (event.type === "error") {
    const visibleText = message.content || latestTurnText(message);
    return {
      ...message,
      content: visibleText
        ? `${visibleText}\n\n[运行中断] ${event.message}`
        : event.message,
      streaming: false,
      error: true,
      traceId: event.trace_id ?? message.traceId,
    };
  }
  const finalOutput = (message.turnOutputs ?? []).find((output) => output.turn === event.turns);
  return {
    ...message,
    content: finalOutput?.content ?? message.content,
    streaming: false,
    activeTurn: event.turns,
    traceId: event.trace_id,
  };
}

function formatPayload(value: unknown) {
  if (typeof value === "string") return value;
  const serialized = JSON.stringify(value, null, 2);
  return serialized ?? String(value);
}

function ToolPayload({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(true);
  if (step.state === "running" || step.result === undefined) return null;
  return (
    <details className="tool-payload" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{open ? "收起调用数据" : "查看输入与结果"}</summary>
      <div className="payload-grid">
        {step.arguments !== undefined && (
          <section>
            <strong>输入参数</strong>
            <pre>{formatPayload(step.arguments)}</pre>
          </section>
        )}
        <section>
          <strong>返回结果</strong>
          <pre>{formatPayload(step.result)}</pre>
        </section>
      </div>
    </details>
  );
}

function ExecutionTrace({ message }: { message: ChatMessage }) {
  const steps = message.steps ?? [];
  const outputs = message.turnOutputs ?? [];
  if (!steps.length && !message.streaming) return null;
  const turnNumbers = Array.from(new Set([
    ...steps.map((step) => step.turn),
    ...outputs.map((output) => output.turn),
    ...(message.activeTurn ? [message.activeTurn] : []),
  ])).sort((left, right) => left - right);
  const visibleTurnNumbers = turnNumbers.filter((turn) => (
    message.streaming
    || turn !== message.activeTurn
    || steps.some((step) => step.turn === turn)
  ));
  return (
    <div className="execution-trace" aria-label="智能体执行轨迹">
      <div className="trace-heading">
        <strong>执行轨迹</strong>
        <span>{message.streaming ? `第 ${message.activeTurn ?? 1} 个 Turn · 运行中` : `共 ${message.activeTurn ?? 0} 个 Turn`}</span>
      </div>
      {visibleTurnNumbers.map((turn) => {
        const output = outputs.find((item) => item.turn === turn);
        const turnSteps = steps.filter((step) => step.turn === turn);
        const isFinalAnswer = !message.streaming && turn === message.activeTurn;
        return (
          <section className="trace-turn" key={turn}>
            <div className="turn-label">Turn {turn}</div>
            {output?.content && !isFinalAnswer && (
              <div className="turn-narrative">
                {output.content}
                {message.streaming && turn === message.activeTurn && <span className="stream-cursor" aria-hidden="true" />}
              </div>
            )}
            {turnSteps.map((step) => (
              <div className={`trace-row trace-${step.state}`} key={step.id}>
                <span className="trace-marker" aria-hidden="true">{step.state === "complete" ? "✓" : step.state === "error" ? "!" : "·"}</span>
                <div className="trace-body">
                  <span className="trace-copy">
                    <strong>{step.label}</strong>
                    <small>{step.detail ?? (step.state === "running" ? "正在调用工具" : step.name)}</small>
                  </span>
                  <ToolPayload step={step} />
                </div>
              </div>
            ))}
          </section>
        );
      })}
      {!visibleTurnNumbers.length && message.streaming && <div className="trace-pending">正在理解请求并判断下一步</div>}
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  return (
    <article className={`message message-${message.role}${message.error ? " message-error" : ""}`}>
      <div className="message-meta">{message.role === "assistant" ? "经营 Agent" : "你"}</div>
      <ExecutionTrace message={message} />
      {(message.content || (message.streaming && !(message.turnOutputs?.length))) && (
        <div className="message-content">
          {message.content || <span className="thinking">正在分析</span>}
        </div>
      )}
    </article>
  );
}

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [draft, setDraft] = useState("");
  const [running, setRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const viewport = scrollRef.current;
    if (viewport) viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const patchAssistant = (id: string, event: StreamEvent) => {
    setMessages((current) => current.map((item) => item.id === id ? updateEvent(item, event) : item));
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || running) return;
    const stamp = Date.now().toString();
    const assistantId = `assistant-${stamp}`;
    setMessages((current) => [...current,
      { id: `user-${stamp}`, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", steps: [], turnOutputs: [], streaming: true },
    ]);
    setDraft("");
    setRunning(true);
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      for await (const streamEvent of streamChat(text, controller.signal)) patchAssistant(assistantId, streamEvent);
    } catch (error) {
      if ((error as DOMException).name === "AbortError") {
        patchAssistant(assistantId, { type: "error", message: "本次运行已停止。" });
      } else {
        patchAssistant(assistantId, { type: "error", message: error instanceof Error ? error.message : "连接中断，请稍后重试。" });
      }
    } finally {
      setRunning(false);
      controllerRef.current = null;
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">经</span>
          <div><h1>经营 Agent</h1><p>自主分析 · 可观察工具调用</p></div>
        </div>
        <div className="connection-state" title="页面请求真实 Agent 流式接口">
          <span aria-hidden="true" />后端接口
        </div>
      </header>

      <div className="conversation" ref={scrollRef} aria-live="polite">
        <div className="conversation-inner">{messages.map((message) => <Message message={message} key={message.id} />)}</div>
      </div>

      <footer className="composer-wrap">
        <form className="composer" onSubmit={submit}>
          <textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKeyDown}
            placeholder="输入经营目标，或询问某个机会、客户与规则" rows={1} disabled={running} aria-label="经营请求" />
          <button className={running ? "stop-button" : "send-button"} type={running ? "button" : "submit"}
            onClick={running ? () => controllerRef.current?.abort() : undefined} disabled={!running && !draft.trim()}
            aria-label={running ? "停止生成" : "发送"}>
            {running ? <span className="stop-icon" aria-hidden="true" /> : <SendIcon />}
          </button>
        </form>
        <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · 当前数据源为合成演示数据</p>
      </footer>
    </main>
  );
}
