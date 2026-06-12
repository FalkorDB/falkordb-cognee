# openclaw-cognee (legacy custom plugin)

> **OUT OF DATE.** This custom plugin is superseded by the official
> [`cognee-openclaw`](https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw)
> plugin, which adds multi scope memory, per agent FalkorDB graphs, session
> tracking with an `/improve` bridge, 14 search types and an
> `openclaw cognee` CLI. Pair it with the
> [FalkorDB setup skill](https://github.com/topoteretes/cognee-integrations/blob/main/integrations/openclaw/skills/falkor/SKILL.md)
> to run Cognee with FalkorDB as both graph and vector store.

This directory is kept as a working minimal reference. It is a 3 file Node
plugin that forwards `/remember` and `/recall` over HTTP to the custom
sidecar in [`scripts/02_cognee_sidecar.py`](../../scripts/02_cognee_sidecar.py).
See the repo [README](../../README.md) for the full picture.
