# C3 — Central Command & Control (PoC)

A control plane over the existing systems (GCMS, ppc-redirection, ads-ops-hub, coupon-svp).
This PoC is **one vertical slice** through every layer: log in → see the portfolio →
tell the copilot to apply a site to a network → approve the dry-run → an agent acts →
status updates → the inbox parser pulls the Publisher ID in.

**Anchor:** `dailyreviewtoday` (MUX) → SourceKnowledge.

## Layers & where they live (PoC)

| Layer | In this scaffold |
|---|---|
| Users | `frontend/` Next.js console + Google login (stubbed at `backend/app/routers/auth.py`) |
| C3 core | `backend/app/models.py` (registry + workflow + audit), routers |
| Policy | identity gate (auth), act-gate + `AuditLog` (copilot/agents land next) |
| Agents | *next* — apply-to-network (Skyvern), inbox-parser (Gmail) |
| Capabilities | GCMS GraphQL read (wired next), ads-ops read (stub) |
| External | affiliate network signup, holding-co inbox |

## Run it

### Backend (FastAPI + SQLite)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in as creds arrive
python -m app.seed            # seed registry from data/portfolio_seed.csv
uvicorn app.main:app --reload --port 8000
```
Check: `curl localhost:8000/health` · `curl localhost:8000/api/portfolio?sandbox=true`

### Frontend (Next.js console)
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000  (proxies /api → :8000)
```

## Status

- [x] Portfolio registry (SQLite, seeded from the inventory sheet)
- [x] Read API: `/api/portfolio`, `/api/sites/{domain}`, `/api/audit`
- [x] Console dashboard (sandbox + full portfolio, network status chips)
- [x] Auth stub (swap in Google OIDC — reuse the 8thloop GCP project)
- [ ] Copilot (Claude tool-use loop) + tool belt
- [ ] Act-gate UI (dry-run → approve) + real apply agent (Skyvern)
- [ ] Inbox parser (Gmail) → Publisher ID
- [ ] GCMS GraphQL live reads

See the build plan artifact for the full milestone map.
