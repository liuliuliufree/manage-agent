import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { isDemoMode, streamChat } from "./chatStream";
import type { ActProgress, ChatMessage, StreamEvent } from "./types";

const INITIAL_ACTS: ActProgress[] = [
  { id: 1, label: "理解目标与边界", detail: "等待开始", state: "waiting" },
  { id: 2, label: "发现并比较机会", detail: "等待开始", state: "waiting" },
  { id: 3, label: "筛选目标客户", detail: "等待开始", state: "waiting" },
];

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "告诉我这次经营目标。我会先核对边界，再比较近期机会并完成客户筛选。所有结果都来自当前合成场景。",
};

function SendIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4.6 14-2.8-5.4L5 12Z" /><path d="m11.6 13.6 3.5-3.8" /></svg>;
}

function updateEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  if (event.type === "delta") return { ...message, content: message.content + event.delta };
  if (event.type === "act") {
    return {
      ...message,
      acts: (message.acts ?? INITIAL_ACTS).map((act) => act.id === event.act ? {
        ...act,
        label: event.label ?? act.label,
        detail: event.detail ?? act.detail,
        state: event.state ?? "complete",
      } : act),
    };
  }
  if (event.type === "error") return { ...message, content: event.message, streaming: false, error: true };
  return { ...message, streaming: false };
}

function ActTimeline({ acts }: { acts: ActProgress[] }) {
  const numbers = ["一", "二", "三"];
  return (
    <div className="act-timeline" aria-label="前三幕执行进度">
      {acts.map((act) => (
        <div className={`act-row act-${act.state}`} key={act.id}>
          <span className="act-marker" aria-hidden="true">{act.state === "complete" ? "✓" : act.id}</span>
          <span className="act-copy">
            <strong>第{numbers[act.id - 1]}幕 · {act.label}</strong>
            <small>{act.detail}</small>
          </span>
        </div>
      ))}
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  return (
    <article className={`message message-${message.role}${message.error ? " message-error" : ""}`}>
      <div className="message-meta">{message.role === "assistant" ? "经营 Agent" : "你"}</div>
      {message.acts && <ActTimeline acts={message.acts} />}
      <div className="message-content">
        {message.content || (message.streaming ? <span className="thinking">正在分析</span> : null)}
        {message.streaming && message.content && <span className="stream-cursor" aria-hidden="true" />}
      </div>
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
      { id: assistantId, role: "assistant", content: "", acts: INITIAL_ACTS.map((act) => ({ ...act })), streaming: true },
    ]);
    setDraft("");
    setRunning(true);
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      for await (const streamEvent of streamChat(text, controller.signal)) patchAssistant(assistantId, streamEvent);
    } catch (error) {
      if ((error as DOMException).name === "AbortError") patchAssistant(assistantId, { type: "done" });
      else patchAssistant(assistantId, { type: "error", message: error instanceof Error ? error.message : "连接中断，请稍后重试。" });
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
          <div><h1>经营 Agent</h1><p>前三幕 · 机会洞察与自动圈客</p></div>
        </div>
        <div className="connection-state" title={isDemoMode ? "当前使用内置合成演示流" : "已连接流式接口"}>
          <span aria-hidden="true" />{isDemoMode ? "演示数据" : "已连接"}
        </div>
      </header>

      <div className="conversation" ref={scrollRef} aria-live="polite">
        <div className="conversation-inner">{messages.map((message) => <Message message={message} key={message.id} />)}</div>
      </div>

      <footer className="composer-wrap">
        <form className="composer" onSubmit={submit}>
          <textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKeyDown}
            placeholder="输入经营目标，例如：分析近期值得重点经营的加保机会" rows={1} disabled={running} aria-label="经营目标" />
          <button className={running ? "stop-button" : "send-button"} type={running ? "button" : "submit"}
            onClick={running ? () => controllerRef.current?.abort() : undefined} disabled={!running && !draft.trim()}
            aria-label={running ? "停止生成" : "发送"}>
            {running ? <span className="stop-icon" aria-hidden="true" /> : <SendIcon />}
          </button>
        </form>
        <p className="composer-hint">Enter 发送 · Shift + Enter 换行 · 合成演示数据</p>
      </footer>
    </main>
  );
}
