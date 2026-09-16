import {
  FormEvent,
  KeyboardEvent,
  TextareaHTMLAttributes,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat } from "./chatStream";
import type { ChatMessage, RunStep, StreamEvent, TurnOutput } from "./types";

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 14-7-4.6 14-2.8-5.4L5 12Z" />
      <path d="m11.6 13.6 3.5-3.8" />
    </svg>
  );
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

function interruptRunningTools(steps: RunStep[]) {
  return steps.map((step) => step.state === "running"
    ? { ...step, state: "error" as const, detail: "运行已中断" }
    : step);
}

function updateEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  if (event.type === "trace") return { ...message, traceId: event.trace_id };
  if (event.type === "turn") return { ...message, activeTurn: event.turn };
  if (event.type === "tool") return { ...message, steps: updateTool(message.steps ?? [], event) };
  if (event.type === "delta") {
    return { ...message, turnOutputs: updateTurnOutput(message.turnOutputs ?? [], event) };
  }
  if (event.type === "error") {
    return {
      ...message,
      streaming: false,
      error: true,
      errorMessage: event.message,
      steps: interruptRunningTools(message.steps ?? []),
      traceId: event.trace_id ?? message.traceId,
    };
  }
  return {
    ...message,
    streaming: false,
    activeTurn: event.turns,
    finalTurn: event.turns,
    traceId: event.trace_id,
  };
}

function formatPayload(value: unknown) {
  if (typeof value === "string") return value;
  const serialized = JSON.stringify(value, null, 2);
  return serialized ?? String(value);
}

function Markdown({ children, compact = false }: { children: string; compact?: boolean }) {
  return (
    <div className={compact ? "markdown markdown-compact" : "markdown"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

function ToolCall({ step }: { step: RunStep }) {
  const stateLabel = step.state === "running" ? "执行中" : step.state === "error" ? "调用失败" : "已完成";
  return (
    <details className={`tool-call tool-${step.state}`}>
      <summary>
        <span className="tool-chevron" aria-hidden="true" />
        <span className="tool-title">{step.label}</span>
        <span className="tool-state">{step.detail ?? stateLabel}</span>
      </summary>
      <div className="tool-detail">
        {step.arguments !== undefined && (
          <section>
            <strong>输入参数</strong>
            <pre>{formatPayload(step.arguments)}</pre>
          </section>
        )}
        {step.result !== undefined ? (
          <section>
            <strong>返回结果</strong>
            <pre>{formatPayload(step.result)}</pre>
          </section>
        ) : (
          <p className="tool-waiting">{step.state === "running" ? "等待返回结果" : "没有返回结果"}</p>
        )}
      </div>
    </details>
  );
}

function AgentResponse({ message }: { message: ChatMessage }) {
  const steps = message.steps ?? [];
  const outputs = message.turnOutputs ?? [];
  const turnNumbers = Array.from(new Set([
    ...steps.map((step) => step.turn),
    ...outputs.map((output) => output.turn),
    ...(message.activeTurn ? [message.activeTurn] : []),
  ])).sort((left, right) => left - right);
  const latestOutputTurn = outputs.at(-1)?.turn;
  const hasVisibleWork = steps.length > 0 || outputs.some((output) => output.content);

  return (
    <div className="agent-response">
      {!hasVisibleWork && message.streaming && (
        <div className="processing-status" role="status">正在处理<span aria-hidden="true" /></div>
      )}
      {turnNumbers.map((turn) => {
        const output = outputs.find((item) => item.turn === turn);
        const turnSteps = steps.filter((step) => step.turn === turn);
        const isConfirmedFinal = !message.streaming && !message.error && message.finalTurn === turn;
        const isCurrentDraft = message.streaming && message.activeTurn === turn && turnSteps.length === 0;
        const isInterruptedDraft = message.error && latestOutputTurn === turn && turnSteps.length === 0;
        const isAnswer = Boolean(output?.content && (isConfirmedFinal || isCurrentDraft || isInterruptedDraft));

        if (isAnswer) {
          return (
            <div className={`answer-content${isCurrentDraft ? " answer-streaming" : ""}`} key={turn}>
              <Markdown>{output!.content}</Markdown>
              {isCurrentDraft && <span className="stream-cursor" aria-hidden="true" />}
            </div>
          );
        }

        if (!output?.content && !turnSteps.length) return null;
        return (
          <section className="process-group" key={turn}>
            {output?.content && (
              <div className="process-narrative">
                <Markdown compact>{output.content}</Markdown>
                {message.streaming && turn === message.activeTurn && <span className="stream-cursor" aria-hidden="true" />}
              </div>
            )}
            {turnSteps.map((step) => <ToolCall step={step} key={step.id} />)}
          </section>
        );
      })}
      {message.errorMessage && (
        <div className="run-error" role="alert">{message.errorMessage}</div>
      )}
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <article className="message message-user">
        <div className="user-bubble">{message.content}</div>
      </article>
    );
  }
  return (
    <article className="message message-assistant">
      <div className="assistant-name">智慧经营智能体</div>
      <AgentResponse message={message} />
    </article>
  );
}

interface ComposerProps {
  draft: string;
  running: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onDraftChange: (value: string) => void;
  onSubmit: (event?: FormEvent) => Promise<void>;
  onStop: () => void;
}

function Composer({ draft, running, inputRef, onDraftChange, onSubmit, onStop }: ComposerProps) {
  const resize: TextareaHTMLAttributes<HTMLTextAreaElement>["onInput"] = (event) => {
    event.currentTarget.style.height = "auto";
    const nextHeight = Math.min(event.currentTarget.scrollHeight, 144);
    event.currentTarget.style.height = `${nextHeight}px`;
    event.currentTarget.style.overflowY = event.currentTarget.scrollHeight > 144 ? "auto" : "hidden";
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void onSubmit();
    }
  };
  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        ref={inputRef}
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        onInput={resize}
        onKeyDown={onKeyDown}
        placeholder="输入经营目标或问题"
        rows={1}
        disabled={running}
        aria-label="经营请求"
      />
      <button
        className={running ? "stop-button" : "send-button"}
        type={running ? "button" : "submit"}
        onClick={running ? onStop : undefined}
        disabled={!running && !draft.trim()}
        aria-label={running ? "停止生成" : "发送"}
      >
        {running ? <span className="stop-icon" aria-hidden="true" /> : <SendIcon />}
      </button>
    </form>
  );
}

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [running, setRunning] = useState(false);
  const [showLatest, setShowLatest] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const followOutputRef = useRef(true);
  const hasConversation = messages.length > 0;

  const scrollToLatest = (behavior: ScrollBehavior = "smooth") => {
    const viewport = scrollRef.current;
    if (!viewport) return;
    followOutputRef.current = true;
    setShowLatest(false);
    viewport.scrollTo({ top: viewport.scrollHeight, behavior });
  };

  useEffect(() => {
    if (followOutputRef.current) scrollToLatest("auto");
  }, [messages]);

  const handleScroll = () => {
    const viewport = scrollRef.current;
    if (!viewport) return;
    const atBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 72;
    followOutputRef.current = atBottom;
    setShowLatest(!atBottom);
  };

  const patchAssistant = (id: string, event: StreamEvent) => {
    setMessages((current) => current.map((item) => item.id === id ? updateEvent(item, event) : item));
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || running) return;
    const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const assistantId = `assistant-${stamp}`;
    followOutputRef.current = true;
    setMessages((current) => [
      ...current,
      { id: `user-${stamp}`, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", steps: [], turnOutputs: [], streaming: true },
    ]);
    setDraft("");
    setRunning(true);
    const controller = new AbortController();
    controllerRef.current = controller;
    let receivedTerminalEvent = false;

    try {
      for await (const streamEvent of streamChat(text, controller.signal)) {
        if (streamEvent.type === "done" || streamEvent.type === "error") receivedTerminalEvent = true;
        patchAssistant(assistantId, streamEvent);
      }
      if (!receivedTerminalEvent) throw new Error("连接已结束，但回答没有完整生成。请重试。");
    } catch (error) {
      if ((error as DOMException).name === "AbortError") {
        patchAssistant(assistantId, { type: "error", message: "已停止生成" });
      } else if (!receivedTerminalEvent) {
        patchAssistant(assistantId, {
          type: "error",
          message: error instanceof Error ? error.message : "连接中断，请稍后重试。",
        });
      }
    } finally {
      setRunning(false);
      controllerRef.current = null;
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const composerProps: ComposerProps = {
    draft,
    running,
    inputRef,
    onDraftChange: setDraft,
    onSubmit: submit,
    onStop: () => controllerRef.current?.abort(),
  };

  if (!hasConversation) {
    return (
      <main className="app-shell app-empty">
        <section className="empty-state">
          <h1>智慧经营智能体</h1>
          <p>从一个经营目标开始，我会调用合适的能力完成分析。</p>
          <Composer {...composerProps} />
          <div className="composer-hint">Enter 发送，Shift + Enter 换行 · 当前使用合成演示数据</div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell app-conversation">
      <div className="conversation" ref={scrollRef} onScroll={handleScroll}>
        <div className="conversation-inner">
          {messages.map((message) => <Message message={message} key={message.id} />)}
        </div>
      </div>
      {showLatest && (
        <button className="latest-button" type="button" onClick={() => scrollToLatest()}>
          回到最新
        </button>
      )}
      <footer className="composer-wrap">
        <Composer {...composerProps} />
        <div className="composer-hint">Enter 发送，Shift + Enter 换行 · 当前使用合成演示数据</div>
      </footer>
    </main>
  );
}
