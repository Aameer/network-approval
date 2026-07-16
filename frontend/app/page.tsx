"use client";
import { useEffect, useState } from "react";
import "./globals.css";

type Net = { id: number; network: string; status: string; publisher_id: string | null };
type Site = {
  domain: string; holding_company: string | null; phase: number;
  category: string | null; status: string | null; country?: string | null;
  redirection?: string | null; is_sandbox: boolean; networks: Net[];
};
type Flow = { id: number; site: string; network: string; state: string; created_by: string; plan: any };
type Audit = { actor: string; actor_kind: string; action: string; target: string | null; created_at: string };
type Registry = { name: string; phase: number; signup_url: string | null; status: string };

const STATUS_COLOR: Record<string, string> = {
  approved: "var(--human)", applied: "var(--c3)", awaiting: "var(--svc)",
  rejected: "#e06666", not_applied: "var(--ext)", re_applied: "var(--agent)",
};
const STATUSES = ["not_applied", "applied", "awaiting", "approved", "rejected", "re_applied"];

async function jpost(url: string, body?: any) {
  const r = await fetch(url, {
    method: "POST", credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { alert("Sign in first (top-right)."); throw new Error("401"); }
  return r.json();
}
async function jpatch(url: string, body: any) {
  const r = await fetch(url, {
    method: "PATCH", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (r.status === 401) { alert("Sign in first (top-right)."); throw new Error("401"); }
  return r.json();
}

export default function Dashboard() {
  const [user, setUser] = useState<any>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [flows, setFlows] = useState<Flow[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [networks, setNetworks] = useState<Registry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    const me = await fetch("/api/auth/me", { credentials: "include" }).then((r) => r.json());
    setUser(me.authenticated ? me.user : null);
    const [p, w, a, nw] = await Promise.all([
      fetch("/api/portfolio", { credentials: "include" }).then((r) => r.json()),
      fetch("/api/workflows?state=awaiting_approval", { credentials: "include" }).then((r) => r.json()),
      fetch("/api/audit?limit=8", { credentials: "include" }).then((r) => r.json()),
      fetch("/api/networks", { credentials: "include" }).then((r) => r.json()),
    ]);
    setSites(p.sites || []); setFlows(w.runs || []); setAudit(a.entries || []); setNetworks(nw.networks || []);
    setLoading(false);
  }
  useEffect(() => { load(); }, []);
  async function login() { await jpost("/api/auth/dev-login"); load(); }
  async function logout() { await jpost("/api/auth/logout"); load(); }

  const sandbox = sites.filter((s) => s.is_sandbox);
  const rest = sites.filter((s) => !s.is_sandbox);

  return (
    <main style={{ maxWidth: 1040, margin: "0 auto", padding: "40px 22px 80px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="mono" style={{ fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>C3 · Command Center</div>
          <h1 style={{ fontSize: 30, letterSpacing: "-.02em", margin: "8px 0 0" }}>Portfolio</h1>
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
          {user
            ? <>signed in · <b style={{ color: "var(--ink)" }}>{user.email}</b> · <a onClick={logout} style={{ cursor: "pointer", color: "var(--c3)" }}>sign out</a></>
            : <button onClick={login} style={btn}>Sign in (stub)</button>}
        </div>
      </div>

      <Copilot onChange={load} />
      <Approvals flows={flows} onChange={load} />

      {loading ? <p style={{ color: "var(--muted)" }}>Loading…</p> : (
        <>
          <Section title="Sandbox" sub="the 3 PoC sites — click chips/phase to act" sites={sandbox} user={user} onChange={load} />
          <Section title={`Rest of portfolio · ${rest.length}`} sub="seeded from the inventory sheet" sites={rest} user={user} onChange={load} collapsed />
        </>
      )}

      <NetworksSection networks={networks} />
      <AuditPanel audit={audit} />
    </main>
  );
}

function NetworksSection({ networks }: { networks: Registry[] }) {
  const [open, setOpen] = useState(false);
  const color = (s: string) => (s === "verified" ? "var(--human)" : s === "pending" ? "var(--c3)" : "var(--ext)");
  const verified = networks.filter((n) => n.status === "verified").length;
  return (
    <section style={{ marginTop: 28 }}>
      <div onClick={() => setOpen(!open)} style={{ cursor: "pointer", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>Networks · {networks.length}</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>registry — {verified} verified · signup URLs discovered once, reused</span>
        <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{open ? "–" : "+"}</span>
      </div>
      {open && (
        <div style={{ marginTop: 12, border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden" }}>
          {networks.map((n, i) => (
            <div key={n.name} style={{ display: "flex", gap: 12, alignItems: "center", padding: "9px 14px", borderBottom: i < networks.length - 1 ? "1px solid var(--line)" : "none", fontSize: 13 }}>
              <span className="mono" style={{ minWidth: 26, color: "var(--muted)" }}>P{n.phase}</span>
              <span className="mono" style={{ minWidth: 128, fontWeight: 600 }}>{n.name}</span>
              <span className="mono" style={{ fontSize: 10.5, color: color(n.status), border: `1px solid ${color(n.status)}`, borderRadius: 12, padding: "1px 8px", minWidth: 74, textAlign: "center" }}>{n.status}</span>
              <span style={{ color: "var(--muted)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.signup_url || "— (discovery target)"}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Approvals({ flows, onChange }: { flows: Flow[]; onChange: () => void }) {
  if (!flows.length) return null;
  async function approve(id: number) { try { await jpost(`/api/workflows/${id}/approve`); onChange(); } catch {} }
  async function reject(id: number) { try { await jpost(`/api/workflows/${id}/reject`, { reason: "declined in console" }); onChange(); } catch {} }
  return (
    <section style={{ marginTop: 24, border: "1px solid var(--c3-line, #6f5230)", borderRadius: 14, background: "color-mix(in srgb, var(--c3) 8%, transparent)", padding: 16 }}>
      <div className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700, marginBottom: 12 }}>
        ⏳ Awaiting approval · {flows.length}
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        {flows.map((f) => (
          <div key={f.id} style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="mono" style={{ fontWeight: 600, fontSize: 13.5 }}>{f.site} → {f.network}</span>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>proposed by {f.created_by} · {f.plan?.documents?.length || 0} docs</span>
              <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <button onClick={() => approve(f.id)} style={{ ...btn }}>Approve</button>
                <button onClick={() => reject(f.id)} style={{ ...btnGhost }}>Reject</button>
              </div>
            </div>
            {f.plan && (
              <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
                email: {f.plan.email} · captcha: {f.plan.captcha}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function Section({ title, sub, sites, user, onChange, collapsed }:
  { title: string; sub: string; sites: Site[]; user: any; onChange: () => void; collapsed?: boolean }) {
  const [open, setOpen] = useState(!collapsed);
  return (
    <section style={{ marginTop: 28 }}>
      <div onClick={() => setOpen(!open)} style={{ cursor: "pointer", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>{title}</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{sub}</span>
        <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{open ? "–" : "+"}</span>
      </div>
      {open && <div style={{ display: "grid", gap: 10, marginTop: 12 }}>{sites.map((s) => <SiteRow key={s.domain} s={s} user={user} onChange={onChange} />)}</div>}
    </section>
  );
}

function SiteRow({ s, user, onChange }: { s: Site; user: any; onChange: () => void }) {
  const need = () => { if (!user) { alert("Sign in first (top-right)."); return false; } return true; };
  async function apply(network: string) { if (!need()) return; try { await jpost("/api/workflows/apply", { domain: s.domain, network }); onChange(); } catch {} }
  async function override(n: Net) {
    if (!need()) return;
    const ns = window.prompt(`Override ${n.network} status (${STATUSES.join(", ")}):`, n.status);
    if (!ns || ns === n.status) return;
    try { await jpatch(`/api/applications/${n.id}`, { status: ns }); onChange(); } catch {}
  }
  async function editPhase() {
    if (!need()) return;
    const p = window.prompt("New phase (0-3):", String(s.phase));
    if (p === null) return;
    try { await jpatch(`/api/sites/${s.domain}`, { phase: Number(p) }); onChange(); } catch {}
  }
  return (
    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 12, padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="mono" style={{ fontWeight: 600, fontSize: 14 }}>{s.domain}</span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>{[s.holding_company, s.country, s.redirection].filter(Boolean).join(" · ") || "—"}</span>
        <span onClick={editPhase} title="click to edit phase" style={{ marginLeft: "auto", cursor: "pointer", fontSize: 10, fontFamily: "var(--mono)", color: "var(--c3)", border: "1px solid var(--line)", borderRadius: 20, padding: "2px 8px" }}>
          phase {s.phase} ✎
        </span>
      </div>
      {s.networks.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {s.networks.map((n) => (
            <span key={n.id} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, fontFamily: "var(--mono)", border: `1px solid ${STATUS_COLOR[n.status] || "var(--line)"}`, color: STATUS_COLOR[n.status] || "var(--muted)", borderRadius: 20, padding: "3px 10px" }}>
              <span onClick={() => override(n)} title="click to override status" style={{ cursor: "pointer" }}>
                {n.network} · {n.status.replace("_", " ")}{n.publisher_id ? ` · ${n.publisher_id}` : ""}
              </span>
              {n.status === "not_applied" && (
                <button onClick={() => apply(n.network)} title="propose application (gated)" style={miniBtn}>▸ apply</button>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AuditPanel({ audit }: { audit: Audit[] }) {
  if (!audit.length) return null;
  return (
    <section style={{ marginTop: 28 }}>
      <div className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>Audit</div>
      <div style={{ marginTop: 10, border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden" }}>
        {audit.map((e, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "9px 14px", borderBottom: i < audit.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
            <span className="mono" style={{ color: e.actor_kind === "human" ? "var(--human)" : e.actor_kind === "agent" ? "var(--agent)" : "var(--muted)", minWidth: 60 }}>{e.actor_kind}</span>
            <span style={{ color: "var(--muted)" }}>{e.actor}</span>
            <span className="mono" style={{ color: "var(--c3)" }}>{e.action}</span>
            <span style={{ color: "var(--muted)", marginLeft: "auto" }}>{e.target}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

type ChatMsg = { role: "user" | "assistant"; content: string; tools?: string[] };
function Copilot({ onChange }: { onChange: () => void }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  async function send() {
    const q = input.trim(); if (!q || busy) return;
    const history = [...msgs, { role: "user" as const, content: q }];
    setMsgs(history); setInput(""); setBusy(true);
    try {
      const r = await fetch("/api/copilot/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) }),
      }).then((x) => x.json());
      setMsgs([...history, { role: "assistant", content: r.reply || r.error || "(no reply)", tools: (r.tools_used || []).map((t: any) => t.tool) }]);
    } catch (e: any) { setMsgs([...history, { role: "assistant", content: "Request failed: " + e.message }]); }
    finally { setBusy(false); onChange(); }
  }
  return (
    <section style={{ marginTop: 24, border: "1px solid var(--line)", borderRadius: 14, background: "var(--paper)", overflow: "hidden" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className="mono" style={{ fontSize: 12, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--c3)", fontWeight: 700 }}>Copilot</span>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>ask the portfolio · can propose applies</span>
      </div>
      <div style={{ maxHeight: 320, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {msgs.length === 0 && <div style={{ color: "var(--muted)", fontSize: 13.5 }}>Try: <i>“which sandbox sites are ready to apply?”</i> · <i>“propose applying dailyreviewtoday to SourceKnowledge”</i></div>}
        {msgs.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "82%" }}>
            <div style={{ background: m.role === "user" ? "color-mix(in srgb, var(--c3) 16%, transparent)" : "var(--ground)", border: "1px solid var(--line)", borderRadius: 10, padding: "9px 13px", fontSize: 14, whiteSpace: "pre-wrap" }}>{m.content}</div>
            {m.tools && m.tools.length > 0 && <div className="mono" style={{ fontSize: 10, color: "var(--human)", marginTop: 4 }}>⚙ {m.tools.join(" · ")}</div>}
          </div>
        ))}
        {busy && <div style={{ color: "var(--muted)", fontSize: 13 }}>thinking…</div>}
      </div>
      <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--line)" }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="Ask the portfolio…" style={{ flex: 1, background: "var(--ground)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 12px", color: "var(--ink)", fontSize: 14 }} />
        <button onClick={send} disabled={busy} style={{ ...btn, opacity: busy ? 0.6 : 1 }}>Send</button>
      </div>
    </section>
  );
}

const btn: React.CSSProperties = { background: "var(--c3)", color: "#0c1016", border: "none", borderRadius: 8, padding: "7px 14px", fontWeight: 700, cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12 };
const btnGhost: React.CSSProperties = { background: "transparent", color: "var(--muted)", border: "1px solid var(--line)", borderRadius: 8, padding: "7px 14px", cursor: "pointer", fontFamily: "var(--mono)", fontSize: 12 };
const miniBtn: React.CSSProperties = { background: "transparent", color: "var(--c3)", border: "1px solid var(--c3)", borderRadius: 12, padding: "0 6px", cursor: "pointer", fontFamily: "var(--mono)", fontSize: 10, lineHeight: "16px" };
