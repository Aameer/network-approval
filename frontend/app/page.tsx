"use client";
import { useEffect, useState } from "react";
import "./globals.css";

type Net = { network: string; status: string; publisher_id: string | null };
type Site = {
  domain: string; holding_company: string | null; phase: number;
  category: string | null; status: string | null; is_sandbox: boolean; networks: Net[];
};

const STATUS_COLOR: Record<string, string> = {
  approved: "var(--human)", applied: "var(--c3)", awaiting: "var(--svc)",
  rejected: "#e06666", not_applied: "var(--ext)", re_applied: "var(--agent)",
};

export default function Dashboard() {
  const [user, setUser] = useState<any>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    const me = await fetch("/api/auth/me", { credentials: "include" }).then((r) => r.json());
    setUser(me.authenticated ? me.user : null);
    const p = await fetch("/api/portfolio", { credentials: "include" }).then((r) => r.json());
    setSites(p.sites || []);
    setLoading(false);
  }
  useEffect(() => { load(); }, []);

  async function login() {
    await fetch("/api/auth/dev-login", { method: "POST", credentials: "include" });
    load();
  }

  const sandbox = sites.filter((s) => s.is_sandbox);
  const rest = sites.filter((s) => !s.is_sandbox);

  return (
    <main style={{ maxWidth: 1040, margin: "0 auto", padding: "40px 22px 80px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>
            C3 · Command Center
          </div>
          <h1 style={{ fontSize: 30, letterSpacing: "-.02em", margin: "8px 0 0" }}>Portfolio</h1>
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
          {user ? <>signed in · <b style={{ color: "var(--ink)" }}>{user.email}</b></>
                : <button onClick={login} style={btn}>Sign in (stub)</button>}
        </div>
      </div>

      <Copilot />

      {loading ? <p style={{ color: "var(--muted)" }}>Loading…</p> : (
        <>
          <Section title="Sandbox" sub="the 3 PoC sites — live network state" sites={sandbox} />
          <Section title={`Rest of portfolio · ${rest.length}`} sub="seeded from the inventory sheet" sites={rest} collapsed />
        </>
      )}
    </main>
  );
}

type ChatMsg = { role: "user" | "assistant"; content: string; tools?: string[] };

function Copilot() {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    const history = [...msgs, { role: "user" as const, content: q }];
    setMsgs(history);
    setInput("");
    setBusy(true);
    try {
      const r = await fetch("/api/copilot/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) }),
      }).then((x) => x.json());
      const reply = r.reply || r.error || "(no reply)";
      const tools = (r.tools_used || []).map((t: any) => t.tool);
      setMsgs([...history, { role: "assistant", content: reply, tools }]);
    } catch (e: any) {
      setMsgs([...history, { role: "assistant", content: "Request failed: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ marginTop: 24, border: "1px solid var(--line)", borderRadius: 14, background: "var(--paper)", overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>Copilot</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>ask about the portfolio · read-only</span>
      </div>
      <div style={{ maxHeight: 320, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {msgs.length === 0 && (
          <div style={{ color: "var(--muted)", fontSize: 13.5 }}>
            Try: <i>“which sandbox sites are ready to apply, and where?”</i> · <i>“what’s dailyreviewtoday’s status?”</i>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "82%" }}>
            <div style={{
              background: m.role === "user" ? "color-mix(in srgb, var(--c3) 16%, transparent)" : "var(--ground)",
              border: "1px solid var(--line)", borderRadius: 10, padding: "9px 13px", fontSize: 14, whiteSpace: "pre-wrap",
            }}>{m.content}</div>
            {m.tools && m.tools.length > 0 && (
              <div className="mono" style={{ fontSize: 10, color: "var(--human)", marginTop: 4 }}>
                ⚙ {m.tools.join(" · ")}
              </div>
            )}
          </div>
        ))}
        {busy && <div style={{ color: "var(--muted)", fontSize: 13 }}>thinking…</div>}
      </div>
      <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--line)" }}>
        <input
          value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="Ask the portfolio…"
          style={{ flex: 1, background: "var(--ground)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 12px", color: "var(--ink)", fontSize: 14 }}
        />
        <button onClick={send} disabled={busy} style={{ ...btn, opacity: busy ? 0.6 : 1 }}>Send</button>
      </div>
    </section>
  );
}

function Section({ title, sub, sites, collapsed }: { title: string; sub: string; sites: Site[]; collapsed?: boolean }) {
  const [open, setOpen] = useState(!collapsed);
  return (
    <section style={{ marginTop: 30 }}>
      <div onClick={() => setOpen(!open)} style={{ cursor: "pointer", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{sub}</span>
        <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{open ? "–" : "+"}</span>
      </div>
      {open && (
        <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
          {sites.map((s) => <SiteRow key={s.domain} s={s} />)}
        </div>
      )}
    </section>
  );
}

function SiteRow({ s }: { s: Site }) {
  return (
    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 12, padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="mono" style={{ fontWeight: 600, fontSize: 14 }}>{s.domain}</span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>{s.holding_company || "—"}</span>
        <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: "var(--mono)", color: "var(--c3)", border: "1px solid var(--line)", borderRadius: 20, padding: "2px 8px" }}>
          phase {s.phase}
        </span>
      </div>
      {s.networks.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {s.networks.map((n) => (
            <span key={n.network} style={{ fontSize: 11.5, fontFamily: "var(--mono)", border: `1px solid ${STATUS_COLOR[n.status] || "var(--line)"}`, color: STATUS_COLOR[n.status] || "var(--muted)", borderRadius: 20, padding: "3px 10px" }}>
              {n.network} · {n.status.replace("_", " ")}{n.publisher_id ? ` · ${n.publisher_id}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const btn: React.CSSProperties = {
  background: "var(--c3)", color: "#0c1016", border: "none", borderRadius: 8,
  padding: "7px 14px", fontWeight: 700, cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12,
};
