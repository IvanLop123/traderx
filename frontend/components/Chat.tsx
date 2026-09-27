"use client";
import { useState } from "react";
import { Loader2, Send, X } from "lucide-react";
import { api } from "@/lib/api";
export function Chat({
  onClose,
  provider,
}: {
  onClose: () => void;
  provider: string;
}) {
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<{ role: string; text: string }[]>(
    [],
  );
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const q = text.trim();
    if (!q) return;
    setText("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await api("/chat", { message: q });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text:
            r.analysis?.summary ||
            "AI is unavailable: " +
              r.status +
              ". Your quantitative systems continue running.",
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: (e as Error).message },
      ]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <aside className="chat">
      <div className="panel-head">
        <div>
          <h2>Research assistant</h2>
          <small className="muted">
            {provider.toUpperCase()} · Calls only when you send
          </small>
        </div>
        <button
          className="icon-button"
          aria-label="Close chatbot"
          onClick={onClose}
        >
          <X />
        </button>
      </div>
      <div className="chat-messages">
        <div className="chat-note">
          Ask about financial text or research concepts. This assistant has no
          tools, portfolio feed or order access.
        </div>
        {messages.map((m, i) => (
          <div key={i} className={"message " + m.role}>
            <small>{m.role === "user" ? "YOU" : "ASSISTANT"}</small>
            <p>{m.text}</p>
          </div>
        ))}
        {busy && <Loader2 className="spin" size={18} />}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          aria-label="Chat message"
          placeholder="Ask a research question…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          className="icon-button"
          disabled={busy}
          aria-label="Send message"
        >
          <Send size={18} />
        </button>
      </form>
    </aside>
  );
}
