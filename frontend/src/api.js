// Thin client for the PreCode API. Same-origin in Docker (nginx proxies /api),
// proxied by Vite in dev.
async function handle(resp) {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return resp.json();
}

export const api = {
  health: () => fetch("/api/health").then(handle),
  priority: () => fetch("/api/priority").then(handle),
  defects: (status = "open") => fetch(`/api/defects?status=${status}`).then(handle),
  ask: (question, history = []) =>
    fetch("/api/agent/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    }).then(handle),
  // Streaming ask (SSE). onEvent receives {type: tool|tool_result|delta|sentence|done, ...}.
  // Resolves with the final `done` event (answer, source, model, citations, suggestions).
  askStream: (question, history = [], onEvent = null) =>
    (async () => {
      const resp = await fetch("/api/agent/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });
      if (!resp.ok || !resp.body) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch { /* keep statusText */ }
        throw new Error(detail);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let done = {};
      for (;;) {
        const { value, done: finished } = await reader.read();
        if (finished) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let type = null;
          let data = null;
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) type = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (type && data) {
            const evt = JSON.parse(data);
            onEvent?.(evt);
            if (type === "done") done = evt;
          }
        }
      }
      return done;
    })(),
};
