// Realtime WebSocket client for /v1/subscribe.
//
// Opens a single connection scoped to the user's workspace (the server
// derives the workspace from the session cookie). An optional board_id
// filter narrows the stream so we don't repaint the kanban for events
// happening on a different board.
//
// Lifecycle: callers pass an `onEvent` handler; the returned function
// closes the socket. Reconnect-on-drop is handled here with a backoff
// schedule, so callers don't need to babysit transport-level concerns.

export type RealtimeEvent = {
  type: string;
  occurred_at: string | null;
  workspace_id: string;
  board_id: string | null;
  target_id: string | null;
  data: Record<string, unknown>;
};

export type RealtimeReadyFrame = {
  type: "ready";
  workspace_id: string;
};

interface ConnectOptions {
  boardId?: string;
  onEvent: (event: RealtimeEvent) => void;
  onReady?: (frame: RealtimeReadyFrame) => void;
  onStatusChange?: (status: "connecting" | "open" | "closed") => void;
}

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000, 15_000];

export function connectRealtime(opts: ConnectOptions): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let attempt = 0;

  function status(s: "connecting" | "open" | "closed"): void {
    opts.onStatusChange?.(s);
  }

  function open(): void {
    if (closed) return;
    status("connecting");

    // Same-origin upgrade — derive scheme + host from window.location so
    // the SPA works in dev (Vite proxy) and prod (FastAPI-served bundle)
    // without configuration.
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const qs = opts.boardId ? `?board_id=${encodeURIComponent(opts.boardId)}` : "";
    const url = `${scheme}://${window.location.host}/v1/subscribe${qs}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      attempt = 0;
      status("open");
    };

    ws.onmessage = (e) => {
      try {
        const frame = JSON.parse(e.data as string);
        if (frame.type === "ready") {
          opts.onReady?.(frame as RealtimeReadyFrame);
          return;
        }
        opts.onEvent(frame as RealtimeEvent);
      } catch {
        // Ignore non-JSON frames; future heartbeats may use them.
      }
    };

    ws.onclose = () => {
      status("closed");
      if (closed) return;
      const delay =
        RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
      attempt += 1;
      window.setTimeout(open, delay);
    };

    ws.onerror = () => {
      // Let onclose handle the reconnect; nothing to do here.
    };
  }

  open();

  return () => {
    closed = true;
    if (ws && ws.readyState <= WebSocket.OPEN) {
      ws.close();
    }
  };
}
