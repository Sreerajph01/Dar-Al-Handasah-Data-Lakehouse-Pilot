# Progress — DAR Lakehouse Pilot

**Last updated:** 2026-10-09 (session start, P0)  
**Current phase:** P0 — Audit, baseline, environment  
**Next action:** User restarts WSL (`wsl --shutdown`) + Docker Desktop; confirm `docker info` Total Memory ≈ 48 GiB; stop or remap `airflow-intro` on port 8080; then begin **P1** (`.\dar.ps1 reset -Force` → `up` → `health`).

---

## Phase status

| Phase | Status | Last evidence | Notes |
|-------|--------|---------------|-------|
| P0 | **RED** (memory gate) | `evidence/2026-10-09/p0-docker-info.log` | WSL config written; 31 GiB until restart |
| P1 | Not started | — | Blocked on P0 memory + port 8080 conflict |
| P2–P12 | Not started | — | |

---

## P0 work log (2026-10-09)

**Commands (evidence files):**

- `evidence/2026-10-09/p0-docker-info.log` — `docker info` (Total Memory **31.06GiB**, CPUs 22)
- `evidence/2026-10-09/p0-gpu-nvidia-smi.log` — CUDA container GPU check (**PASS**)
- `evidence/2026-10-09/p0-dar-containers.log` — 37 `dar-*` containers all **Exited**
- `evidence/2026-10-09/p0-compose-services.log` — 37 compose service names
- `evidence/2026-10-09/p0-s3-proxy-check.log` — no `s3-proxy`; `dar-seaweedfs-s3` present
- `evidence/2026-10-09/p0-rfp-parse.log` — **97** requirements parsed from xlsx
- `evidence/2026-10-09/p0-wslconfig.log` — `%USERPROFILE%\.wslconfig` contents
- `evidence/2026-10-09/p0-dar-help.log` — `dar.ps1` targets
- `evidence/2026-10-09/p0-git-status.log` — branch `master`, tag `baseline`

**Changes:**

- Created `%USERPROFILE%\.wslconfig` (48GB RAM, 14 CPUs, 16GB swap, `vm.max_map_count=262144`)
- Rewrote `docs/STATE_AUDIT.md` from live inventory
- Created this `docs/PROGRESS.md`
- Re-ran RFP parse (requirements.yaml refreshed)

**Open issues:**

1. Docker Desktop still reports **31.06 GiB** — needs WSL shutdown + Docker restart (**manual**)
2. **Port 8080** held by `airflow-intro-airflow-apiserver-1` — conflict risk for SeaweedFS volume status / other services
3. Stack fully down; prior health/unhealthy counts **UNVERIFIED**
4. `backup`/`restore` targets are stubs in `dar.ps1`
5. Host Python not installed — acceptable (container workflow)

---

## Claims vs evidence (P0)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Git repo exists | `p0-git-status.log` | Verified |
| Full stack defines 37 services | `p0-compose-services.log` | Verified |
| No s3-proxy container | `p0-s3-proxy-check.log` | Verified |
| GPU works in Docker | `p0-gpu-nvidia-smi.log` | Verified |
| RFP has 97 requirements | `p0-rfp-parse.log` | Verified |
| Docker has 48 GiB limit | `p0-docker-info.log` | **Failed** — shows 31.06 GiB |
| All services healthy | — | **UNVERIFIED** (stack down) |
| Prior M2/M3 gates | — | **UNVERIFIED** |

---

## Tags / commits

- Existing: `baseline` @ `8facd76`, `363ea88` Baseline local lakehouse pilot
- Pending: `phase-P0-green` after memory gate passes (not tagged yet)
