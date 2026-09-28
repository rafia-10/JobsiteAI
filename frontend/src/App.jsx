import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { useVoice } from "./useVoice.js";

const STARTERS = [
  "What's my priority today and tomorrow?",
  "What defects are still open?",
  "Who's on site this week?",
  "How is the project tracking overall?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState([]); // {role, text, meta?, streaming?}
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState(null);       // "checking today's tasks…"
  const [suggestions, setSuggestions] = useState(STARTERS);
  const [voiceOn, setVoiceOn] = useState(true);
  const [health, setHealth] = useState(null);
  const [priority, setPriority] = useState(null);
  const transcriptRef = useRef(null);
  const voiceRef = useRef(null);

  const voice = useVoice();
  voiceRef.current = voice;

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "backend unreachable" }));
    api.priority().then(setPriority).catch(() => {});
  }, []);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [conversation, activity]);

  const ask = useCallback(
    async (text) => {
      const q = (text ?? question).trim();
      if (!q || busy) return;
      setQuestion("");
      setBusy(true);
      setSuggestions([]);
      setConversation((c) => [...c, { role: "user", text: q }]);

      // History = everything before this turn, already resolved (streamed msgs excluded).
      const history = conversation
        .filter((m) => !m.streaming && m.text && !m.text.startsWith("Error:"))
        .map((m) => ({ role: m.role, content: m.text }));

      setConversation((c) => [...c, { role: "assistant", text: "", streaming: true, meta: null }]);
      let patchId = null;
      const patch = (fn) =>
        setConversation((c) => {
          const next = [...c];
          const last = next.length - 1;
          next[last] = fn({ ...next[last] });
          return next;
        });

      try {
        const done = await api.askStream(
          q,
          history,
          (evt) => {
            if (evt.type === "tool") {
              setActivity(toolLabel(evt.name));
            } else if (evt.type === "tool_result") {
              setActivity(null);
            } else if (evt.type === "delta") {
              patch((m) => ({ ...m, text: m.text + evt.text }));
            } else if (evt.type === "sentence") {
              if (voiceOn) voiceRef.current?.speak(evt.text);
            }
          },
        );
        patch((m) => ({
          ...m,
          text: done.answer || m.text || "I couldn't produce an answer.",
          streaming: false,
          meta: done,
        }));
        setSuggestions(done.suggestions?.length ? done.suggestions : STARTERS);
      } catch (err) {
        patch((m) => ({ ...m, text: `Error: ${err.message}`, streaming: false }));
        setSuggestions(STARTERS);
      } finally {
        setBusy(false);
        setActivity(null);
      }
    },
    [question, busy, conversation, voiceOn],
  );

  const handleMic = useCallback(() => {
    if (voice.listening) {
      voice.stopListening();
    } else {
      voice.stopSpeaking();
      voice.startListening((text) => ask(text));
    }
  }, [voice, ask]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">PreCode</span>
          <span className="sub">Site Assistant</span>
        </div>
        <div className={`status ${health?.status === "ok" ? "ok" : "bad"}`}>
          {health ? `backend: ${health.status} · db: ${health.database || "?"} · llm: ${health.llm}` : "connecting…"}
        </div>
      </header>

      <main className="layout">
        {/* ------------------------------- conversation --------------- */}
        <section className="chat panel">
          <div className="panel-head">
            <h2>Voice assistant</h2>
            <label className="voice-toggle">
              <input type="checkbox" checked={voiceOn} onChange={(e) => setVoiceOn(e.target.checked)} />
              speak answers
            </label>
          </div>

          <div className="transcript" ref={transcriptRef}>
            {conversation.length === 0 && (
              <div className="empty">
                <p>Hold the mic and ask, or type below. Answers come from the live project database via a real LLM.</p>
                <div className="chips">
                  {suggestions.map((s) => (
                    <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {conversation.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className={`bubble ${m.streaming ? "streaming" : ""}`}>
                  {m.text}
                  {m.streaming && <span className="caret" aria-hidden="true" />}
                  {m.meta && !m.streaming && (
                    <div className="meta">
                      {m.meta.source === "llm+tools" ? `model: ${m.meta.model}` : "deterministic fallback"}
                      {m.meta.citations?.length > 0 && " · cited: " + m.meta.citations.map((c) => c.title).join(", ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && activity && <div className="activity">⚙ {activity}</div>}
          </div>

          {voice.error && <div className="voice-error">{voice.error}</div>}

          <div className="composer">
            <button
              className={`mic ${voice.listening ? "live" : ""} ${voice.speaking ? "speaking" : ""}`}
              onClick={handleMic}
              title={voice.sttMode === "none" ? "no speech recognition in this browser" : `STT: ${voice.sttMode}`}
              disabled={voice.sttMode === "none"}
            >
              {voice.listening ? "● listening…" : voice.speaking ? "🔊 speaking" : "🎙 hold to ask"}
            </button>
            <input
              value={question}
              placeholder={busy ? "assistant is answering…" : "or type a question…"}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              disabled={busy}
            />
            <button className="send" onClick={() => ask()} disabled={busy || !question.trim()}>ask</button>
          </div>

          {conversation.length > 0 && (
            <div className="chips followups">
              {suggestions.map((s) => (
                <button key={s} className="chip" onClick={() => ask(s)} disabled={busy}>{s}</button>
              ))}
            </div>
          )}
        </section>

        {/* ------------------------------- live data ------------------- */}
        <aside className="side">
          <div className="panel">
            <div className="panel-head"><h2>Today's priorities</h2></div>
            {priority ? (
              <>
                <div className="proj-name">{priority.project_name}</div>
                {["overdue", "today", "tomorrow"].map((k) =>
                  priority[k]?.length > 0 && (
                    <div key={k} className="bucket">
                      <h3 className={k}>{k}</h3>
                      {priority[k].map((t) => (
                        <div key={t.task_id} className="task">
                          <span className={`prio ${t.priority}`}>{t.priority}</span>
                          <span className="title">{t.title}</span>
                          <span className="trade">{t.trade}</span>
                          {t.open_defects > 0 && <span className="defect-badge">{t.open_defects} defect{t.open_defects > 1 ? "s" : ""}</span>}
                        </div>
                      ))}
                    </div>
                  )
                )}
                {!priority.overdue?.length && !priority.today?.length && !priority.tomorrow?.length && (
                  <p className="dim">No active tasks in the next 48h.</p>
                )}
              </>
            ) : (
              <p className="dim">loading…</p>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}

function toolLabel(name) {
  const labels = {
    get_priority_tasks: "checking today's schedule…",
    get_project_status: "checking project status…",
    get_defects: "checking defects…",
    get_trades_workload: "checking crews on site…",
    get_tasks: "searching tasks…",
  };
  return labels[name] || `running ${name}…`;
}
