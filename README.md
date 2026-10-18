# falkordb-cognee

Use **[FalkorDB](https://www.falkordb.com/)** as the **only** storage backend
for **[Cognee](https://github.com/topoteretes/cognee)** — graph **and**
vectors in one place — and expose it to applications (here: the
[OpenClaw](https://www.openclaw.com/) gateway) through a small Python
sidecar plus a Node plugin.

## ➡️ Recommended: the official Cognee integration for OpenClaw

Cognee now ships an **official OpenClaw integration** that supersedes the
custom plugin and sidecar in this repo for most users. Start there:

- **[`cognee-integrations/integrations/openclaw`](https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw)**.
  The official `cognee-openclaw` memory plugin. With FalkorDB behind it you get
  one named graph per agent plus:
  - **Multi scope memory**: separate datasets for company, user and agent scope. Each dataset is its own FalkorDB graph.
  - **Per agent graphs**: with more than one agent configured, each agent's files and chat route to `{agentDatasetPrefix}-{agentId}`, its own graph.
  - **Auto recall and auto index**: memories are injected before each agent run and memory markdown files sync to Cognee after each turn.
  - **Session tracking**: recall turns are captured as session Q&A. `session_end` bridges them into the graph via `/improve`.
  - **14 search types**: from `CHUNKS` vector search to `GRAPH_COMPLETION` and chain of thought graph reasoning, all answered from the FalkorDB graph.
  - **CLI**: `openclaw cognee setup | index | status | health | scopes | forget | improve`.
- **[`skills/falkor/SKILL.md`](https://github.com/topoteretes/cognee-integrations/blob/main/integrations/openclaw/skills/falkor/SKILL.md)**.
  A self contained, agent runnable recipe that builds a custom Cognee image
  with the FalkorDB hybrid adapter registered through `sitecustomize.py`,
  runs Cognee plus FalkorDB with docker compose, verifies the adapter
  actually registered, and wires the OpenClaw plugin to it. FalkorDB serves
  as **both** the graph store and the vector store, with per dataset
  isolation (`ENABLE_BACKEND_ACCESS_CONTROL=True`) so every dataset gets its
  own FalkorDB graph.

What this repo still adds on top of the official path:

- `scripts/cognee_falkor_naming.py`: human readable FalkorDB graph names
  (`agent_will`) instead of dataset UUID keys, config driven, including a
  `dataset-name` strategy built for the official plugin's per agent datasets.
- `scripts/cognee_falkor_resilience.py`: a tolerant graph read so one
  malformed record cannot blank out recall for a whole graph.
- Operational learnings in [`docs/SETUP.md`](docs/SETUP.md): rate limit safe
  model pins, `DATASET_QUEUE_MAX_CONCURRENT=1` for bulk ingest, SQLite lock
  avoidance, and why small per topic memory files extract reliably while one
  big `MEMORY.md` does not.

The custom sidecar documented below still works and remains a minimal
reference, but new setups should prefer the official plugin plus skill above.

## What this repo is for

Cognee, by default, expects a separate graph store (Kuzu / Neo4j) **and** a
separate vector store (LanceDB / Chroma / Qdrant / …). The
`cognee-community-hybrid-adapter-falkor` package lets you collapse both into
a single FalkorDB instance, but wiring it up is non-obvious — there are
specific environment variables, a side-effect import, and matching
adapter-version requirements.

This repo is a **working, end-to-end recipe** for that setup, plus the
glue we used to plug the result into OpenClaw as a memory plugin
(legacy reference architecture, see the official integration above for
new setups):

```
   Application (OpenClaw gateway, etc.)
        │
        ▼
   Memory plugin (Node)  ─── HTTP ───►  Cognee sidecar
                                        (Python FastAPI, host venv or Docker,
                                         listens on 127.0.0.1:8765)
                                              │
                                              ▼
                                        FalkorDB (Redis fork)
                                          one named graph per user
                                          (e.g. "will", "will__elizabeth")
                                          + vector indexes
```

The point of having this repo is so the next person (or future-me) doesn't
have to re-discover:

- which Cognee env vars are mandatory and what their non-obvious names are
  (e.g. `LLM_API_KEY` vs `OPENAI_API_KEY`),
- that `cognee_community_hybrid_adapter_falkor` must be imported for its
  side effects **before** calling Cognee,
- that the FalkorDB adapter is versioned alongside Cognee and the two must
  be upgraded together (Cognee 1.x ⟶ adapter ≥ 0.3.0),
- that on Linux distros with an older system `libsqlite3` (e.g. Ubuntu
  24.04 / 3.45.x) Cognee 1.x SEGVs in the SQLite SELECT parser unless
  Python's `sqlite3` is shimmed to `pysqlite3-binary`
  (see [`docs/SETUP.md` §3.1](docs/SETUP.md)),
- the exact OpenClaw plugin descriptor shape required by `registerService`,
- the OpenClaw config keys that silently abort the gateway if you get them
  wrong.

## Multiple graphs & friendly naming

In multi-user mode (`ENABLE_BACKEND_ACCESS_CONTROL=true`, the default here)
Cognee routes each user to their **own** isolated FalkorDB graph. The
community adapter would name those after the dataset UUID; this repo instead
registers thin handler subclasses (`scripts/cognee_falkor_naming.py`) through
the adapter's **public** extension API so graphs get readable names —
`will@example.com` → graph `will`, `will_agent_elizabeth@example.com` →
`will__elizabeth`. The rule is fully env-driven (overrides map, email
local-part, dataset-id, or static); see
[`docs/SETUP.md` §3.2](docs/SETUP.md). Set
`ENABLE_BACKEND_ACCESS_CONTROL=false` for legacy single-graph mode.

## Supported Cognee versions

Verified against **Cognee 1.0.x and 1.1.x** with
`cognee-community-hybrid-adapter-falkor>=0.3.0,<0.4`. The pinned default
in `scripts/00_install_cognee.sh` is **`cognee==1.1.0`**.

Cognee 1.1.0 introduced a few breaking changes the sidecar handles for
you, but they're worth knowing about if you embed Cognee 1.1.0 yourself:

- **New dataset handler env vars** — `GRAPH_DATASET_DATABASE_HANDLER`
  and `VECTOR_DATASET_DATABASE_HANDLER` must be set to
  `falkor_graph_local` and `falkor_vector_local` respectively for
  Cognee to route per-dataset graphs/vectors through the FalkorDB
  hybrid adapter. The sidecar sets both defaults.
- **`cognee.search()` response shape changed** — 1.0.x returned
  `list[str]`; 1.1.0 returns `list[dict]` of the form
  `{dataset_id, dataset_name, dataset_tenant_id, search_result: [str,...]}`.
  The `/recall` endpoint flattens this back to `list[str]` so the
  documented `{ok, results: string[]}` contract holds.
- **Default LLM changed to `gpt-5-mini`** — Cognee 1.1.0 ships two
  separate model knobs (`LLM_MODEL` and `BAML_LLM_MODEL`, the latter
  for cognify's extraction pipeline) and defaults **both** to
  `gpt-5-mini`, which requires OpenAI organization verification.
  The sidecar pins both to `openai/gpt-4o-mini` / `gpt-4o-mini` and
  mirrors `LLM_API_KEY → BAML_LLM_API_KEY`.
- **New resource-cap env vars** — `DATABASE_MAX_LRU_CACHE_SIZE` and
  `DATASET_QUEUE_MAX_CONCURRENT` bound the new dataset LRU eviction
  and cognify concurrency added in 1.1.0; small defaults (4 / 2) are
  set by the sidecar.
- **`COGNEE_SKIP_CONNECTION_TEST`** — 1.1.0 added a startup LLM
  connectivity probe that can hang on slow/cold networks (notably
  inside Docker). Set to `true` to bypass.

## What's in here

```
falkordb-cognee/
├── README.md               ← you are here
├── docs/
│   └── SETUP.md            ← the full step-by-step setup guide
├── scripts/                ← every script used to install + manage the stack
│   ├── 00_install_cognee.sh
│   ├── 01_test_cognee_falkor.py / 01_run.sh
│   ├── 02_cognee_sidecar.py
│   ├── cognee_falkor_naming.py  ← friendly FalkorDB graph names (config-driven)
│   ├── cognee_falkor_resilience.py ← recall survives malformed graph records
│   ├── 03_run_sidecar.sh
│   ├── 04_cognee_sidecar.service / 04_install_service.sh / 04b_status.sh / 04c_takeover.sh
│   ├── 05_smoke_sidecar.sh
│   ├── 08_install_cognee_plugin.sh
│   ├── 09b_fix_slot.sh
│   ├── 10_redeploy_plugin.sh
│   └── 11b_set_userid_guy.sh
├── docker/                 ← run the sidecar as a container (alternative to host venv)
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   └── .env.example
├── plugin/
│   └── openclaw-cognee/    ← the Node plugin source (3 files)
│       ├── package.json
│       ├── openclaw.plugin.json
│       └── index.js
└── examples/               ← (placeholder for sample queries / demos)
```

## Quick start (legacy custom sidecar)

> For new setups use the official integration linked at the top. This quick
> start builds the legacy sidecar and custom plugin, kept as a reference.

The whole flow is documented in [`docs/SETUP.md`](docs/SETUP.md). The short
version (assuming you have FalkorDB on `localhost:6379`, Python 3.11–3.13,
Node 22, and `OPENAI_API_KEY` exported):

### Pinned versions

| Package | Version | Where it's pinned |
|---------|---------|-------------------|
| `cognee` | **1.1.0** | [`scripts/00_install_cognee.sh`](scripts/00_install_cognee.sh) |
| `cognee-community-hybrid-adapter-falkor` | **>=0.3.0,<0.4** | [`scripts/00_install_cognee.sh`](scripts/00_install_cognee.sh) |
| `falkordb` (Python client) | `>=1.0.9,<2.0.0` | [`scripts/00_install_cognee.sh`](scripts/00_install_cognee.sh) |
| `pysqlite3-binary` | latest (bundles SQLite ≥3.51) | [`scripts/00_install_cognee.sh`](scripts/00_install_cognee.sh) — required on Linux, see [`docs/SETUP.md` §3.1](docs/SETUP.md) |

To bump cognee, edit `scripts/00_install_cognee.sh` and the two
references in `docs/SETUP.md` (one in §2 "What was installed", one in §10
the upgrade recipe).

```bash
cd scripts

./00_install_cognee.sh           # venv + cognee + falkor adapter + fastapi
./01_run.sh                      # POC: ingest 3 facts, query them
./04_install_service.sh          # install sidecar as systemd service
./05_smoke_sidecar.sh            # end-to-end curl test

# Optional: wire it into OpenClaw as a memory plugin
./08_install_cognee_plugin.sh
./09b_fix_slot.sh
./11b_set_userid_guy.sh
```

## Status

- ✅ Standalone Cognee + FalkorDB POC working
- ✅ **Production setup migrated to the official [`cognee-openclaw`](https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw) plugin** with the Cognee API server (per agent FalkorDB graphs, named via `cognee_falkor_naming.py`)
- ✅ FastAPI sidecar still available both as a systemd service (`cognee-sidecar.service`)
  and as a Docker container (`docker/`) for minimal reference setups
- ✅ Per-user **multiple, isolated FalkorDB graphs** with human-readable,
  config-driven names (`scripts/cognee_falkor_naming.py`, see
  [`docs/SETUP.md` §3.2](docs/SETUP.md))
- 🚧 `examples/` to be filled with sample prompts / graph queries

## Why FalkorDB

- One process for both graph **and** vector storage (RedisGraph-compatible
  + native vector indexes)
- Speaks the Redis wire protocol → easy to inspect with `redis-cli`
- Already in use here for other projects, so reusing it avoids running
  yet another database

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
