# Cognee sidecar image — bakes our customized sidecar on top of the official
# cognee 1.1.0 image so the container keeps:
#   - friendly, config-driven FalkorDB graph names (cognee_falkor_naming.py)
#     so the FalkorDB browser / redis-cli GRAPH.LIST stay readable
#   - per-user multi-tenant mode (ENABLE_BACKEND_ACCESS_CONTROL=true)
#   - /recall response flattening for cognee 1.1.0's new dict shape
#   - LRU + concurrency caps recommended in the 1.1.0 release notes
#
# The Ubuntu 24.04 libsqlite3 SEGV shim baked into the sidecar is a no-op
# here: the cognee/cognee image already ships a modern sqlite3.
#
# Build context is the REPO ROOT (see docker-compose.yaml `context: ..`) so
# the sidecar + naming module are copied from scripts/.
FROM cognee/cognee:1.1.0

# Install the community FalkorDB hybrid adapter into cognee's venv.
# Pinned to >=0.3.1 — 0.3.1 fixes the has_edges() IndexError
# (https://github.com/topoteretes/cognee-community/issues/107).
RUN /app/.venv/bin/python -m ensurepip --upgrade \
 && /app/.venv/bin/python -m pip install --no-cache-dir \
        "cognee-community-hybrid-adapter-falkor>=0.3.1,<0.4" \
        "fastapi" "uvicorn" "python-dotenv" "pydantic[email]"

# Auto-register the FalkorDB providers on every Python startup. Without
# this the env-var-selected provider names fail to resolve.
RUN echo "import cognee_community_hybrid_adapter_falkor.register" \
        > /app/.venv/lib/python3.12/site-packages/sitecustomize.py

# Bring our customized sidecar + naming module into the image. uvicorn runs
# from this WORKDIR, so the two sibling modules are importable.
WORKDIR /app/sidecar
COPY scripts/02_cognee_sidecar.py ./02_cognee_sidecar.py
COPY scripts/cognee_falkor_naming.py ./cognee_falkor_naming.py

# Persistent state (Users + Datasets relational DB, logs) lives under
# /root/.cognee inside the container — mount a volume on it via compose.
ENV PYTHONUNBUFFERED=1 \
    HOME=/root

EXPOSE 8765

CMD ["/app/.venv/bin/uvicorn", "02_cognee_sidecar:app", \
     "--host", "0.0.0.0", "--port", "8765", "--log-level", "info"]
