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
  ask: (question) =>
    fetch("/api/agent/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then(handle),
};
