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
uvicorn app.main:app --reload --port 8008
```
Check: `curl 127.0.0.1:8008/health` · `curl 127.0.0.1:8008/api/portfolio?sandbox=true`

### Frontend (Next.js console)
```bash
cd frontend
npm install
npm run dev          # http://localhost:3000  (proxies /api → :8000)
```

## Status

- [x] Portfolio registry (SQLite, all sheet columns except 3 secrets + raw JSON)
- [x] Read API: `/api/portfolio`, `/api/sites/{domain}`, `/api/audit`, `/api/workflows`
- [x] Console dashboard (sandbox + full portfolio, network status chips) + copilot chat
- [x] Copilot: Claude tool-use loop — read_portfolio, get_site (GCMS), get_traffic, apply_to_network (propose)
- [x] Act-gate: propose dry-run → identity-gated human approve → status flips → audit (real submission STUBBED)
- [x] Edit/override: gated + audited `PATCH /api/sites/{domain}`, `PATCH /api/applications/{id}`
- [x] Auth stub (swap in Google OIDC — reuse the 8thloop GCP project)
- [ ] Console UI for approvals + inline edit (backend done; drive via /docs meanwhile)
- [ ] Real apply agent (Skyvern) — swap `apply._execute_apply` when creds land
- [ ] Inbox parser (Gmail) → Publisher ID
- [ ] Live GCMS reads (drop GCMS creds into backend/.env to enable)
- [ ] Read/write RBAC (row + column scopes) — production step

See the build plan artifact for the full milestone map.
