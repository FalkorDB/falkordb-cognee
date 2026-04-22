# falkordb-cognee

Use **[FalkorDB](https://www.falkordb.com/)** as the **only** storage backend
for **[Cognee](https://github.com/topoteretes/cognee)** — graph **and**
vectors in one place — and expose it to applications (here: the
[OpenClaw](https://www.openclaw.com/) gateway) through a small Python
sidecar plus a Node plugin.

## What this repo is for

Cognee, by default, expects a separate graph store (Kuzu / Neo4j) **and** a
separate vector store (LanceDB / Chroma / Qdrant / …). The
`cognee-community-hybrid-adapter-falkor` package lets you collapse both into
a single FalkorDB instance, but wiring it up is non-obvious — there are
specific environment variables, a side-effect import, and matching
adapter-version requirements.

This repo is a **working, end-to-end recipe** for that setup, plus the
glue we used to plug the result into OpenClaw as a memory plugin:

```
   Application (OpenClaw gateway, etc.)
        │
        ▼
   Memory plugin (Node)  ─── HTTP ───►  Cognee sidecar
                                        (Python FastAPI, systemd service,
                                         listens on 127.0.0.1:8765)
                                              │
                                              ▼
                                        FalkorDB (Redis fork)
                                          graph "cognee"
                                          + vector indexes
```

The point of having this repo is so the next person (or future-me) doesn't
have to re-discover:

- which Cognee env vars are mandatory and what their non-obvious names are
  (e.g. `LLM_API_KEY` vs `OPENAI_API_KEY`),
- that `cognee_community_hybrid_adapter_falkor` must be imported for its
  side effects **before** calling Cognee,
- that the FalkorDB adapter is versioned alongside Cognee and the two must
  be upgraded together,
- the exact OpenClaw plugin descriptor shape required by `registerService`,
- the OpenClaw config keys that silently abort the gateway if you get them
  wrong.

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
│   ├── 03_run_sidecar.sh
│   ├── 04_cognee_sidecar.service / 04_install_service.sh / 04b_status.sh / 04c_takeover.sh
│   ├── 05_smoke_sidecar.sh
│   ├── 08_install_cognee_plugin.sh
│   ├── 09b_fix_slot.sh
│   ├── 10_redeploy_plugin.sh
│   └── 11b_set_userid_guy.sh
├── plugin/
│   └── openclaw-cognee/    ← the Node plugin source (3 files)
│       ├── package.json
│       ├── openclaw.plugin.json
│       └── index.js
└── examples/               ← (placeholder for sample queries / demos)
```

## Quick start

The whole flow is documented in [`docs/SETUP.md`](docs/SETUP.md). The short
version (assuming you have FalkorDB on `localhost:6379`, Python 3.11–3.13,
Node 22, and `OPENAI_API_KEY` exported):

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
- ✅ FastAPI sidecar running as a systemd service (`cognee-sidecar.service`)
- ✅ OpenClaw memory plugin (`openclaw-cognee`) registered and capturing /
  recalling turns under user `guy`
- 🚧 `examples/` to be filled with sample prompts / graph queries

## Why FalkorDB

- One process for both graph **and** vector storage (RedisGraph-compatible
  + native vector indexes)
- Speaks the Redis wire protocol → easy to inspect with `redis-cli`
- Already in use here for other projects, so reusing it avoids running
  yet another database

## License

Personal setup notes; no warranty. The bundled scripts are MIT-style — do
whatever you want with them.
