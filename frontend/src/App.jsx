import { useEffect, useRef, useState } from "react";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const newSessionId = () => "s-" + Math.random().toString(36).slice(2, 10);

function errorText(status, body) {
  const d = body && body.detail;
  if (typeof d === "string") return status === 503 ? "All providers are unavailable right now. Please try again shortly." : d;
  if (Array.isArray(d)) return "Invalid request: " + d.map((e) => e.msg).join("; ");
  return `Something went wrong (HTTP ${status}).`;
}

export default function App() {
  const [sessionId] = useState(newSessionId); // new session on every page load
  const [items, setItems] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulate, setSimulate] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
  endRef.current?.scrollIntoView({ behavior: "smooth" });
}, [items, loading]);

  async function send() {
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setItems((p) => [...p, { kind: "user", text: message }]);
    setLoading(true);
    try {
      const headers = { "Content-Type": "application/json" };
      if (simulate.trim()) headers["X-Simulate-Failure"] = simulate.trim();
      const body = { session_id: sessionId, message };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();
      const res = await fetch(`${API}/chat`, { method: "POST", headers, body: JSON.stringify(body) });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw { status: res.status, data };
      setItems((p) => [...p, { kind: "assistant", text: data.reply, meta: data.metadata }]);
    } catch (e) {
      const msg = e && e.status ? errorText(e.status, e.data) : "Cannot reach the server. Check your connection and try again.";
      setItems((p) => [...p, { kind: "error", text: msg }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>LLM Chatbot</h1>
        <span className="sid">session {sessionId}</span>
      </header>

      <details className="settings">
        <summary>Session settings</summary>
        <label>
          System prompt
          <textarea
            data-testid="system-prompt-input"
            rows={2}
            placeholder="Optional, e.g. You are a pirate."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </label>
        <label>
          Simulate failure (demo)
          <input value={simulate} placeholder="key_1=429  |  *=429" onChange={(e) => setSimulate(e.target.value)} />
        </label>
      </details>

      <main>
        {items.length === 0 && <p className="empty">Say something to start the conversation.</p>}
        {items.map((m, i) =>
          m.kind === "assistant" ? (
            <div key={i} className="msg assistant" data-testid="assistant-message">
              <div className="text">{m.text}</div>
              <div className="meta">
                <span className={"badge " + m.meta.resolution_source} data-testid="meta-source">{m.meta.resolution_source}</span>
                <span>model: <b data-testid="meta-model">{m.meta.model}</b></span>
                <span>latency: <b data-testid="meta-latency">{m.meta.latency_ms} ms</b></span>
                <span>in: <b data-testid="meta-input-tokens">{m.meta.input_tokens}</b></span>
                <span>out: <b data-testid="meta-output-tokens">{m.meta.output_tokens}</b></span>
                {m.meta.key_id && <span>{m.meta.key_id}{m.meta.fallback_attempts > 0 ? ` (after ${m.meta.fallback_attempts} failover)` : ""}</span>}
              </div>
            </div>
          ) : (
            <div key={i} className={"msg " + m.kind} role={m.kind === "error" ? "alert" : undefined}>
              {m.text}
            </div>
          )
        )}
        {loading && <div className="msg assistant typing">Thinking…</div>}
        <div ref={endRef} />
      </main>

      <footer>
        <textarea
          data-testid="chat-input"
          rows={1}
          value={input}
          placeholder="Type a message…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button data-testid="send-button" onClick={send} disabled={loading}>Send</button>
      </footer>
    </div>
  );
}
