# Cognee + FalkorDB memory backend for OpenClaw

This folder contains everything that was used to set up an
**`openclaw-cognee`** memory plugin for OpenClaw, backed entirely by
**FalkorDB** (graph + vectors) through a **Cognee** Python sidecar.

End-to-end shape:

```
   OpenClaw gateway (Node)
        │  in-process plugin
        ▼
   openclaw-cognee plugin (Node, this repo)  ─── HTTP ───►  Cognee sidecar
                                                            (Python FastAPI,
                                                             systemd service,
                                                             listens on :8765)
                                                                  │
                                                                  ▼
                                                            FalkorDB (Redis fork)
                                                              one named graph per user
                                                              (e.g. "will", "will__elizabeth")
                                                              + vector indexes
```

---

## 1. Prerequisites

These were already in place on this machine:

| Component | Notes |
|-----------|-------|
| FalkorDB | Running on `localhost:6379` (RedisGraph-compatible). Hosts the `cognee` graph. |
| Python 3.12 | System Python (`/usr/bin/python3`) — Cognee 1.x requires 3.11–3.13. |
| Node 22 + OpenClaw CLI | Already installed globally as `openclaw`, with config at `~/.openclaw/openclaw.json` and extensions in `~/.openclaw/extensions/`. |
| `OPENAI_API_KEY` | Available in shell (Cognee re-uses it as `LLM_API_KEY`). |

---

## 2. What was installed

A Python virtualenv lives at:

```
~/.cognee-venv/
```

with these pip packages (installed by `00_install_cognee.sh`):

- `cognee==1.1.0`
- `cognee-community-hybrid-adapter-falkor>=0.3.0,<0.4`  ← FalkorDB graph + vector adapters (1.x compatible)
- `pysqlite3-binary`                          ← bundled SQLite ≥3.51 (see §3.1 below)
- `fastapi`, `uvicorn[standard]`, `python-dotenv`  ← for the sidecar

Cognee 1.0 highlights (vs 0.5.x):

- New high-level API: `remember` / `recall` / `forget` / `improve`
  (the V1 `add` / `cognify` / `search` calls used here still work).
- Session memory is on by default (set `CACHING=false` to disable).
- Multi-user access control is on by default
  (set `ENABLE_BACKEND_ACCESS_CONTROL=false` to keep single-user mode).

---

## 3. Cognee env-var quirks (must be set before importing `cognee`)

These are set by both `01_test_cognee_falkor.py` and `02_cognee_sidecar.py`,
and you need them whenever you call Cognee directly:

```bash
export LLM_API_KEY="$OPENAI_API_KEY"          # NOT OPENAI_API_KEY
export LLM_PROVIDER=openai
export LLM_MODEL=openai/gpt-4o-mini
export EMBEDDING_PROVIDER=openai
export EMBEDDING_MODEL=openai/text-embedding-3-small
export EMBEDDING_DIMENSIONS=1536

# These two are what actually wires Cognee to FalkorDB. The `_named`
# handlers (registered by scripts/cognee_falkor_naming.py) give each graph
# a human-readable name instead of the dataset UUID — see §3.2. Use the
# plain `falkor_graph_local` / `falkor_vector_local` to keep UUID names.
export GRAPH_DATASET_DATABASE_HANDLER=falkor_graph_local_named
export VECTOR_DATASET_DATABASE_HANDLER=falkor_vector_local_named
export GRAPH_DB_URL=localhost
export GRAPH_DB_PORT=6379

# Multi-user mode: each user gets their OWN isolated, named FalkorDB graph.
# This is the default the sidecar ships. Set to false for legacy single-graph
# mode (one shared graph, Cognee's permission system skipped).
export ENABLE_BACKEND_ACCESS_CONTROL=true
```

> **Why multiple graphs need access control:** Cognee only routes each user
> to a separate FalkorDB graph when `ENABLE_BACKEND_ACCESS_CONTROL=true`.
> With it off, every user/dataset collapses into one global graph regardless
> of the handler you pick.

In Python, you also **must** import the adapter for its side-effect
registration *before* calling Cognee:

```python
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
import cognee
```

Cognee still uses **SQLite** for its own relational metadata (datasets,
pipeline state). That's expected and unavoidable.

### 3.1. SQLite gotcha on Linux (Ubuntu 24.04 and similar)

Cognee 1.x triggers a `SIGSEGV` inside the **system** `libsqlite3.so.0`
shipped on Ubuntu 24.04 (3.45.1) the moment Cognee runs its first SELECT
through SQLAlchemy. The crashing stack (from `gdb` on the core dump):

```
__strlen_evex                  ← SEGV in libc strlen
sqlite3DbStrDup
sqlite3WalkSelect / sqlite3SelectPrep / sqlite3Select
sqlite3_prepare_v2
_sqlite3.cpython-312           ← Python stdlib sqlite3 extension
sqlalchemy ... cognee.search(...)
```

The fix is to make Python's `sqlite3` import resolve to the **bundled**
SQLite that ships with the `pysqlite3-binary` wheel (currently 3.51.x).
Both `01_test_cognee_falkor.py` and `02_cognee_sidecar.py` start with
this 10-line shim **before** any `cognee` / `sqlalchemy` import:

```python
try:
    import sys
    import pysqlite3
    sys.modules["sqlite3"] = pysqlite3
    sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2
except ImportError:
    pass
```

`pysqlite3-binary` is installed by `00_install_cognee.sh`. macOS ships a
recent SQLite already, so the shim is a no-op there but does no harm.

> A `sitecustomize.py` placed inside the venv does **not** work on
> Ubuntu, because `/usr/lib/python3.12/sitecustomize.py` is found first
> and shadows it. The shim must live in the entrypoint script.

### 3.2. Naming graphs in FalkorDB

In multi-user mode Cognee gives every user their own FalkorDB graph, but
the community adapter names each one after the dataset **UUID**:

```python
# cognee_community_hybrid_adapter_falkor … create_dataset
graph_db_name = f"{dataset_id}"   # e.g. "4aaeaca4a8255cdca3b9e6cb3310715c"
```

That is unreadable in `redis-cli GRAPH.LIST` and the FalkorDB browser, and
the adapter exposes **no** config hook for it. `scripts/cognee_falkor_naming.py`
fixes this *cleanly* — it subclasses the adapter's two dataset-database
handlers and registers them through the adapter's **public** extension API
(`use_dataset_database_handler`) as `falkor_graph_local_named` /
`falkor_vector_local_named`. (No monkey-patching of private methods.)

The sidecar registers and selects them by default
(`COGNEE_FRIENDLY_GRAPH_NAMES=true`). The naming rule is fully env-driven:

| Env var | Default | Meaning |
|---------|---------|---------|
| `COGNEE_FRIENDLY_GRAPH_NAMES` | `true` | Use named handlers (`false` → native UUID names) |
| `COGNEE_GRAPH_NAME_OVERRIDES` | — | JSON map giving a user an exact name; **wins over everything**. Keyed by email or local-part, e.g. `{"will_agent_elizabeth":"elizabeth"}` |
| `COGNEE_GRAPH_NAME_FROM` | `email-localpart` | Strategy when no override matches: `email-localpart` \| `dataset-id` \| `static` |
| `COGNEE_AGENT_SEPARATOR` | `__` | For `email-localpart`, rewrites `_agent_` → this (`will_agent_elizabeth` → `will__elizabeth`) |
| `COGNEE_GRAPH_NAME_STATIC` | — | The single shared name when `COGNEE_GRAPH_NAME_FROM=static` |

So the OpenClaw user id flows through to a readable graph name:
`will@example.com` → graph **`will`**; `will_agent_elizabeth@example.com`
→ graph **`will__elizabeth`**. All names are sanitised to `[A-Za-z0-9_]`.

> **Overrides are the easy + durable way to name a graph.** The graph name
> is persisted in the `dataset_database` SQLite row and only computed once
> (on first write for a new user/dataset). To pin a name that was renamed
> out-of-band — or to keep names stable if that row is ever rebuilt — list
> it in `COGNEE_GRAPH_NAME_OVERRIDES`.
>
> **Collisions:** two users/datasets that resolve to the same name share one
> graph. The default per-user strategy assumes one logical dataset per user
> (as in this OpenClaw setup); use overrides or `dataset-id` if you need
> stronger isolation guarantees.

---

## 4. The sidecar (Python FastAPI)

File: `02_cognee_sidecar.py`. It exposes:

| Method | Path        | Purpose |
|--------|-------------|---------|
| GET    | `/healthz`  | sidecar liveness |
| POST   | `/remember` | `{userId, text}` → `cognee.add(...)` + `cognee.cognify()` |
| POST   | `/recall`   | `{userId, query, topK}` → `cognee.search(SearchType.GRAPH_COMPLETION, ...)` |
| POST   | `/prune`    | wipe Cognee's graph for a user |

It's installed as a systemd unit `cognee-sidecar.service` (see
`04_cognee_sidecar.service` and `04_install_service.sh`) and listens on
`127.0.0.1:8765`. Unit ExecStart runs the venv's uvicorn directly,
so no shell activation is required.

Useful commands:

```bash
systemctl status cognee-sidecar
journalctl -u cognee-sidecar -n 100 --no-pager
curl -s http://127.0.0.1:8765/healthz
~/work/script/coscripts/05_smoke_sidecar.sh   # full remember/recall round-trip
```

---

## 5. The OpenClaw plugin (Node)

Folder: `openclaw-cognee/` — three files:

```
openclaw-cognee/
├── package.json          (type: module, no deps, just node 22 fetch)
├── openclaw.plugin.json  (kind: memory, JSON-schema config)
└── index.js              (the plugin)
```

Key things the plugin does in `register(api)`:

1. Reads its config (`sidecarUrl`, `userId`, `topK`, `autoCapture`, `autoRecall`, `timeoutMs`).
2. `api.registerService({ id: "openclaw-cognee", start, stop })`
   — **the descriptor MUST contain `id`, and use `start`/`stop` (not `onStart`/`onStop`).**
   `start` pings `/healthz`.
3. `api.on("before_agent_start", ...)` — pulls memories from `/recall`
   and returns `{ prependContext: "..." }` to inject them into the prompt.
4. `api.on("agent_end", ...)` — POSTs the turn to `/remember`.

Install / re-deploy:

```bash
~/work/script/coscripts/08_install_cognee_plugin.sh   # first install
~/work/script/coscripts/10_redeploy_plugin.sh         # after editing index.js
```

Both scripts copy the folder into `~/.openclaw/extensions/openclaw-cognee/`
and restart the gateway via `openclaw gateway restart`.

---

## 6. OpenClaw config wiring

OpenClaw needs the plugin in **two** places in `~/.openclaw/openclaw.json`:

```jsonc
{
  "plugins": {
    "entries": {
      "openclaw-cognee":  {
        "enabled": true,
        "config": {
          "sidecarUrl": "http://127.0.0.1:8765",
          "userId": "guy",
          "autoCapture": true,
          "autoRecall": true,
          "topK": 5,
          "timeoutMs": 60000
        }
      }
    },
    "slots": {
      "memory": "openclaw-cognee"   // <- the "memory slot" must point here
    }
  }
}
```

Important gotchas learned the hard way:

- The plugin's `configSchema` has `additionalProperties: false`, so any
  unknown key under `entries.openclaw-cognee.config` (e.g. `user` instead
  of `userId`) makes the gateway abort with
  *"invalid config: must NOT have additional properties"*.
- Unknown **top-level** keys (e.g. `plugins.memorySlot` instead of
  `plugins.slots.memory`) also make the gateway abort.
- Backups of `openclaw.json` are made by every script that touches it
  (look for `openclaw.json.bak.*`).

Helper scripts that edit the config:

| Script                       | What it does |
|------------------------------|--------------|
| `08_install_cognee_plugin.sh`| adds the cognee entry to `plugins.entries` |
| `09b_fix_slot.sh`            | sets `plugins.slots.memory` to `openclaw-cognee` |
| `11b_set_userid_guy.sh`      | flips `config.userId` to `guy` |

---

## 7. Verifying it works

```bash
# 1. Sidecar is up
systemctl is-active cognee-sidecar
curl -s http://127.0.0.1:8765/healthz

# 2. Gateway loaded the plugin
grep -a 'openclaw-cognee\|ready (' /tmp/openclaw/openclaw-$(date +%F).log | tail
#   expect: "openclaw-cognee: registered (... user: guy ...)"
#   then:   "ready (2 plugins: openclaw-cognee, telegram; ...)"

# 3. Live capture/recall (after talking to an agent over Telegram)
grep -a 'openclaw-cognee:' /tmp/openclaw/openclaw-$(date +%F).log | tail
#   expect: "captured turn for guy (... chars)"
#   and:    "injecting N memories into context"

# 4. Inspect the graphs (one per user in multi-user mode)
redis-cli -p 6379 GRAPH.LIST
redis-cli -p 6379 GRAPH.QUERY will "MATCH (n) RETURN count(n)"
```

---

## 8. Script index

| # | File                          | Purpose |
|---|-------------------------------|---------|
| 00 | `00_install_cognee.sh`       | Create `.venv`, install Cognee + FalkorDB adapter + FastAPI |
| 01 | `01_test_cognee_falkor.py` / `01_run.sh` | Standalone POC: ingest 3 facts, ask 3 questions |
| 02 | `02_cognee_sidecar.py`       | The FastAPI sidecar (multi-user, friendly graph names) |
|    | `cognee_falkor_naming.py`    | Config-driven friendly FalkorDB graph-name handlers (see §3.2) |
| 03 | `03_run_sidecar.sh`          | Foreground runner (debug only) |
| 04 | `04_cognee_sidecar.service` / `04_install_service.sh` / `04b_status.sh` / `04c_takeover.sh` | Install + manage systemd service |
| 05 | `05_smoke_sidecar.sh`        | curl-based remember/recall round-trip test |
| 08 | `08_install_cognee_plugin.sh`| Install the Node plugin into `~/.openclaw/extensions/` and patch config |
| 09 | `09b_fix_slot.sh`            | Set `plugins.slots.memory` to `openclaw-cognee` |
| 10 | `10_redeploy_plugin.sh`      | Re-copy plugin source + restart gateway |
| 11 | `11b_set_userid_guy.sh`      | Set `config.userId` to `guy` |
|    | `openclaw-cognee/`           | The Node plugin source (3 files) |

All scripts log to `~/work/openclaw/config/cognee-*.txt` for after-the-fact debugging.

---

## 9. Reproducing the install from scratch

If you ever rebuild this machine, run these in order:

```bash
cd ~/work/script/coscripts

# 1. Python venv + Cognee + FalkorDB adapter + FastAPI
./00_install_cognee.sh

# 2. Quick POC (ingests 3 facts into FalkorDB graph "cognee" and queries them)
./01_run.sh

# 3. Install the sidecar as a systemd service (uses sudo)
./04_install_service.sh
./04b_status.sh                 # confirm "active (running)" on :8765
./05_smoke_sidecar.sh           # end-to-end curl test

# 4. Install the Node plugin into OpenClaw and wire it up
./08_install_cognee_plugin.sh   # copies plugin + adds entry in openclaw.json
./09b_fix_slot.sh               # plugins.slots.memory -> openclaw-cognee
./11b_set_userid_guy.sh         # config.userId -> guy (default was alice)

# 5. Verify
grep -a 'openclaw-cognee\|ready (' /tmp/openclaw/openclaw-$(date +%F).log | tail
```

After step 5 you should see `ready (2 plugins: openclaw-cognee, telegram; ...)`
and on the next agent turn `captured turn for guy (... chars)` in the gateway log.


---

## 10. Upgrading from Cognee 0.5.x to 1.0.x

If you originally installed this stack on Cognee 0.5.x, an in-place
upgrade to 1.0.x needs three things:

1. **Bump the Python packages** (cognee + the FalkorDB adapter must move
   together — 1.x cognee requires `cognee-community-hybrid-adapter-falkor>=0.3.0`).
2. **Add the `pysqlite3` shim** to every Python entrypoint (sidecar +
   POC). See §3.1.
3. **Wipe stale on-disk state**, because the 1.0 schema (relational
   metadata under `~/.cognee/` and FalkorDB graphs) is not
   backwards-compatible with 0.5.

End-to-end recipe used on Ubuntu 24.04:

```bash
# 1. Stop the sidecar
sudo systemctl stop cognee-sidecar

# 2. Snapshot Cognee state (SQLite + caches)
cp -a ~/.cognee ~/.cognee.bak.$(date +%Y%m%d_%H%M%S)

# 3. Upgrade venv
~/.cognee-venv/bin/pip install --upgrade \
    'cognee==1.1.0' \
    'cognee-community-hybrid-adapter-falkor>=0.3.0,<0.4' \
    pysqlite3-binary

# 4. Confirm the shim is present at the top of:
#      scripts/01_test_cognee_falkor.py
#      scripts/02_cognee_sidecar.py

# 5. Wipe stale state for a clean 1.0 schema
mv ~/.cognee ~/.cognee.preupgrade.$(date +%Y%m%d_%H%M%S)
mkdir -p ~/.cognee/{system,data}
redis-cli -p 6379 FLUSHALL    # FalkorDB: drops ALL graphs (not just cognee)

# 6. Restart and smoke
sudo systemctl start cognee-sidecar
curl -s http://127.0.0.1:8765/healthz
curl -s -X POST http://127.0.0.1:8765/remember \
    -H 'Content-Type: application/json' \
    -d '{"text":"the answer is 42","user_id":"probe"}'
curl -s -X POST http://127.0.0.1:8765/recall \
    -H 'Content-Type: application/json' \
    -d '{"query":"what is the answer?","user_id":"probe","top_k":3}'
```

Skipping step 5 will surface as either:

- the same `SIGSEGV` crash loop in `cognee-sidecar.service` (libsqlite3
  parsing a stale schema row), or
- silent "no results" responses because the graph nodes were created by
  the old extractor and the 1.0 retrievers don't recognise them.

If you only want to preserve memory and the upgrade scares you, snapshot
FalkorDB first with `BGSAVE` and copy `dump.rdb` aside before
`FLUSHALL`.

---

## 11. Docker deployment (alternative to the host venv)

Instead of running the sidecar from a host virtualenv + systemd, you can run
it as a container built on the official `cognee/cognee:1.1.0` image. This is
the recommended deployment: it avoids the host SQLite gotcha (§3.1) entirely
and pins the whole toolchain.

The container does **not** run FalkorDB — point it at an already-running
FalkorDB on the host (e.g. the `falkordb/falkordb` image with `-p 6379:6379`).
With `network_mode: host` the sidecar reaches it at `localhost:6379`, which
also matches the `graph_db_url` baked into any existing dataset rows so your
graphs survive the cutover from a host-side sidecar.

```bash
cd docker
cp .env.example .env          # fill in LLM_API_KEY + COGNEE_STATE_DIR
docker compose up -d --build
curl -s http://127.0.0.1:8765/healthz          # {"ok":true}
redis-cli -p 6379 GRAPH.LIST                    # your per-user named graphs
```

Files:

| File | Purpose |
|------|---------|
| `docker/Dockerfile` | Bakes the sidecar + naming module onto `cognee/cognee:1.1.0` |
| `docker/docker-compose.yaml` | Runs the sidecar with `network_mode: host`, multi-user + friendly names |
| `docker/.env.example` | `LLM_API_KEY`, `COGNEE_STATE_DIR`, optional `COGNEE_GRAPH_NAME_OVERRIDES` |

Graph naming is configured the same way as the host sidecar (§3.2) — set the
`COGNEE_GRAPH_NAME_*` vars in `.env` / the compose `environment:` block.

> **Migrating from a host-side sidecar:** stop and disable the host service
> (`systemctl stop/disable cognee-sidecar`) so it releases port 8765, point
> `COGNEE_STATE_DIR` at the existing `~/.cognee`, then `docker compose up -d`.
> The container then serves the same `127.0.0.1:8765` the OpenClaw plugin
> already targets.
