export type Role = "user" | "assistant";
export type ActId = 1 | 2 | 3;
export type ActState = "waiting" | "running" | "complete";

export interface ActProgress {
  id: ActId;
  label: string;
  detail: string;
  state: ActState;
}

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  acts?: ActProgress[];
  streaming?: boolean;
  error?: boolean;
}

export type StreamEvent =
  | { type: "act"; act: ActId; label?: string; detail?: string; state?: ActState }
  | { type: "delta"; delta: string }
  | { type: "done"; degraded?: boolean }
  | { type: "error"; message: string };
