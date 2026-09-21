import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Voice I/O for the assistant.
 *
 * Speech-to-text, in order of preference:
 *   1. Browser Web Speech API (Chrome/Edge) — no keys, instant.
 *   2. MediaRecorder -> POST /api/voice/transcribe (server Whisper) —
 *      for browsers without built-in recognition.
 *
 * Text-to-speech:
 *   1. Browser speechSynthesis (always available, no keys).
 *   2. Server TTS (/api/voice/speak) — opt-in via UI toggle once configured.
 */
export function useVoice() {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [sttMode, setSttMode] = useState("none"); // none | browser | server
  const [error, setError] = useState(null);

  const recognitionRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SR) {
      const rec = new SR();
      rec.lang = "en-NZ";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      recognitionRef.current = rec;
      setSttMode("browser");
    } else if (navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
      setSttMode("server");
    }
    return () => {
      recognitionRef.current?.abort?.();
      streamRef.current?.getTracks?.().forEach((t) => t.stop());
      window.speechSynthesis?.cancel();
    };
  }, []);

  const startListening = useCallback(
    async (onTranscript) => {
      setError(null);
      const rec = recognitionRef.current;
      if (rec) {
        rec.onresult = (e) => {
          const text = e.results[0][0].transcript;
          setListening(false);
          if (text) onTranscript(text);
        };
        rec.onerror = (e) => {
          setListening(false);
          if (e.error !== "aborted" && e.error !== "no-speech") {
            setError(`speech recognition: ${e.error}`);
          }
        };
        rec.onend = () => setListening(false);
        try {
          rec.start();
          setListening(true);
        } catch {
          setError("couldn't start speech recognition");
          setListening(false);
        }
        return;
      }

      // Server-side STT path: record until stopped, then transcribe.
      if (sttMode === "server") {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          streamRef.current = stream;
          chunksRef.current = [];
          recorderRef.current = new MediaRecorder(stream);
          recorderRef.current.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
          recorderRef.current.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            const blob = new Blob(chunksRef.current, { type: "audio/webm" });
            if (blob.size < 1200) return; // silence / accidental tap
            const form = new FormData();
            form.append("audio", blob, "speech.webm");
            try {
              const resp = await fetch("/api/voice/transcribe", { method: "POST", body: form });
              if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || "transcribe failed");
              const { text } = await resp.json();
              if (text) onTranscript(text);
            } catch (err) {
              setError(String(err.message || err));
            }
          };
          recorderRef.current.start();
          setListening(true);
        } catch (err) {
          setError(`microphone unavailable: ${err.message || err}`);
        }
        return;
      }
      setError("this browser has no speech recognition available");
    },
    [sttMode]
  );

  const stopListening = useCallback(() => {
    const rec = recognitionRef.current;
    if (rec && listening) {
      rec.stop(); // final result arrives via onresult
    } else if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    setListening(false);
  }, [listening]);

  const speak = useCallback(async (text, useServer = false) => {
    window.speechSynthesis?.cancel();
    if (useServer) {
      try {
        const resp = await fetch("/api/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (resp.ok) {
          const blob = await resp.blob();
          const audio = new Audio(URL.createObjectURL(blob));
          setSpeaking(true);
          audio.onended = () => setSpeaking(false);
          await audio.play();
          return;
        }
      } catch { /* fall through to browser TTS */ }
    }
    if (window.speechSynthesis) {
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = 1.05;
      utter.onend = () => setSpeaking(false);
      setSpeaking(true);
      window.speechSynthesis.speak(utter);
    }
  }, []);

  const stopSpeaking = useCallback(() => {
    window.speechSynthesis?.cancel();
    setSpeaking(false);
  }, []);

  return { listening, speaking, sttMode, error, startListening, stopListening, speak, stopSpeaking, setError };
}
