"""
Standalone POC: prove Cognee can remember + recall using ONLY FalkorDB.

Run with:
    source ~/.cognee-venv/bin/activate
    python 01_test_cognee_falkor.py
"""
# --- BEGIN sqlite3 shim ------------------------------------------------------
# See 02_cognee_sidecar.py for the full explanation. Keep this block at the
# very top: it must run before any cognee/sqlalchemy import.
try:
    import sys
    import pysqlite3  # type: ignore
    sys.modules["sqlite3"] = pysqlite3
    sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2
except ImportError:
    pass
# --- END sqlite3 shim --------------------------------------------------------

import asyncio
import os
import pathlib
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.openclaw/.env"))

# Cognee reads LLM_API_KEY (not OPENAI_API_KEY) — map it across.
if os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_KEY"):
    os.environ["LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "openai/gpt-4o-mini")
os.environ.setdefault("EMBEDDING_PROVIDER", "openai")
os.environ.setdefault("EMBEDDING_MODEL", "openai/text-embedding-3-small")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1536")

# Tell cognee to use FalkorDB for both graph and vector dataset handlers
# (otherwise it defaults to kuzu/lancedb and refuses to start in multi-user mode).
os.environ.setdefault("GRAPH_DATASET_DATABASE_HANDLER", "falkor_graph_local")
os.environ.setdefault("VECTOR_DATASET_DATABASE_HANDLER", "falkor_vector_local")
os.environ.setdefault("GRAPH_DB_URL", "localhost")
os.environ.setdefault("GRAPH_DB_PORT", "6379")
# Disable multi-user access control - we don't need it for OpenClaw.
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

import cognee
from cognee import config
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401  side-effect import


async def main() -> None:
    base = pathlib.Path.home() / ".cognee"
    config.system_root_directory(str(base / "system"))
    config.data_root_directory(str(base / "data"))

    config.set_relational_db_config({"db_provider": "sqlite"})

    config.set_vector_db_config({
        "vector_db_provider": "falkor",
        "vector_db_url": "localhost",
        "vector_db_port": 6379,
    })
    config.set_graph_db_config({
        "graph_database_provider": "falkor",
        "graph_database_url": "localhost",
        "graph_database_port": 6379,
    })

    print("[1/4] pruning prior cognee state…")
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)

    print("[2/4] adding sample memories…")
    await cognee.add("Hadar plays tennis at 2pm on Sundays in Ramat Gan.")
    await cognee.add("Guy Lubovitch was born on November 30, 1972.")
    await cognee.add("FalkorDB is a Redis-based graph database used by OpenClaw.")

    print("[3/4] cognify (entity extraction + graph build)…")
    await cognee.cognify()

    print("[4/4] search…")
    from cognee import SearchType
    for q in ("When does Hadar play tennis?",
              "What is FalkorDB?",
              "When was Guy born?"):
        print(f"\nQ: {q}")
        results = await cognee.search(query_type=SearchType.GRAPH_COMPLETION,
                                      query_text=q)
        for r in results:
            print(f"  → {r}")

    print("\nDone. Check FalkorDB browser for graph data.")


if __name__ == "__main__":
    asyncio.run(main())
