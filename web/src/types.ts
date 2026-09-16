export type Role = "user" | "assistant";
export type StepState = "running" | "complete" | "error";

export interface RunStep {
  id: string;
  name: string;
  label: string;
  turn: number;
  detail?: string;
  arguments?: unknown;
  result?: unknown;
  state: StepState;
}

export interface TurnOutput {
  turn: number;
  content: string;
}

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  steps?: RunStep[];
  turnOutputs?: TurnOutput[];
  traceId?: string;
  activeTurn?: number;
  streaming?: boolean;
  error?: boolean;
}

export type StreamEvent =
  | { type: "trace"; trace_id: string; state: "running" }
  | { type: "turn"; turn: number; state: "running" }
  | { type: "tool"; id: string; name: string; label?: string; turn: number; detail?: string; arguments?: unknown; result?: unknown; state: StepState }
  | { type: "delta"; turn: number; delta: string }
  | { type: "done"; status: string; trace_id: string; turns: number }
  | { type: "error"; message: string; trace_id?: string };
