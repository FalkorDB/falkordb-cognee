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
                                                              graph "cognee"
                                                              + vector indexes
```

---

## 1. Prerequisites

These were already in place on this machine:

| Component | Notes |
|-----------|-------|
| FalkorDB | Running on `localhost:6379` (RedisGraph-compatible). Hosts the `cognee` graph. |
| Python 3.12 | System Python (`/usr/bin/python3`) — Cognee 0.5.x requires 3.11–3.13. |
| Node 22 + OpenClaw CLI | Already installed globally as `openclaw`, with config at `~/.openclaw/openclaw.json` and extensions in `~/.openclaw/extensions/`. |
| `OPENAI_API_KEY` | Available in shell (Cognee re-uses it as `LLM_API_KEY`). |

---

## 2. What was installed

A Python virtualenv lives at:

```
~/work/script/coscripts/.venv/
```

with these pip packages (installed by `00_install_cognee.sh`):

- `cognee==0.5.6`
- `cognee-community-hybrid-adapter-falkor`  ← provides FalkorDB graph + vector adapters
- `fastapi`, `uvicorn[standard]`, `httpx`   ← for the sidecar

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

# These two are what actually wires Cognee to FalkorDB:
export GRAPH_DATASET_DATABASE_HANDLER=falkor_graph_local
export VECTOR_DATASET_DATABASE_HANDLER=falkor_vector_local
export GRAPH_DB_URL=localhost
export GRAPH_DB_PORT=6379

# Single-user mode (skip Cognee's permission system):
export ENABLE_BACKEND_ACCESS_CONTROL=false
```

In Python, you also **must** import the adapter for its side-effect
registration *before* calling Cognee:

```python
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
import cognee
```

Cognee still uses **SQLite** for its own relational metadata (datasets,
pipeline state). That's expected and unavoidable.

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

# 4. Inspect the graph
redis-cli -p 6379 GRAPH.QUERY cognee "MATCH (n) RETURN count(n)"
```

---

## 8. Script index

| # | File                          | Purpose |
|---|-------------------------------|---------|
| 00 | `00_install_cognee.sh`       | Create `.venv`, install Cognee + FalkorDB adapter + FastAPI |
| 01 | `01_test_cognee_falkor.py` / `01_run.sh` | Standalone POC: ingest 3 facts, ask 3 questions |
| 02 | `02_cognee_sidecar.py`       | The FastAPI sidecar |
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

