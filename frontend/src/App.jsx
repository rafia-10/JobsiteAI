import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { useVoice } from "./useVoice.js";

const SUGGESTIONS = [
  "What's my priority today and tomorrow?",
  "Any overdue work on site?",
  "What defects are still open?",
  "Who's on site this week?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [conversation, setConversation] = useState([]); // {role: 'user'|'assistant', text, meta}
  const [busy, setBusy] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [health, setHealth] = useState(null);
  const [priority, setPriority] = useState(null);
  const transcriptRef = useRef(null);

  const voice = useVoice();

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "backend unreachable" }));
    api.priority().then(setPriority).catch(() => {});
  }, []);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight });
  }, [conversation]);

  const ask = useCallback(
    async (text) => {
      const q = (text || question).trim();
      if (!q || busy) return;
      setQuestion("");
      setBusy(true);
      setConversation((c) => [...c, { role: "user", text: q }]);
      try {
        const res = await api.ask(q);
        setConversation((c) => [...c, { role: "assistant", text: res.answer, meta: res }]);
        if (voiceOn) voice.speak(res.answer);
      } catch (err) {
        setConversation((c) => [...c, { role: "assistant", text: `Error: ${err.message}`, meta: null }]);
      } finally {
        setBusy(false);
      }
    },
    [question, busy, voiceOn, voice]
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
                <p>Hold the mic and ask, or type below. Everything is answered from the live project database.</p>
                <div className="chips">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {conversation.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="bubble">
                  {m.text}
                  {m.meta && (
                    <div className="meta">
                      {m.meta.source === "llm+tools" ? `model: ${m.meta.model}` : "deterministic fallback"}
                      {m.meta.citations?.length > 0 && " · cited: " + m.meta.citations.map((c) => c.title).join(", ")}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="msg assistant"><div className="bubble thinking">checking the schedule…</div></div>}
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
              placeholder="or type a question…"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
            />
            <button className="send" onClick={() => ask()} disabled={busy || !question.trim()}>ask</button>
          </div>
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
