// openclaw-cognee: memory plugin that delegates to the cognee-sidecar over HTTP.
// Hooks: before_agent_start (recall), agent_end (capture).
// Sidecar API:
//   POST /remember {text, user_id?, agent_id?}    → {ok}
//   POST /recall   {query, user_id?, agent_id?, top_k?} → {ok, results: string[]}
//   GET  /healthz                                 → {ok}

const DEFAULTS = Object.freeze({
  sidecarUrl: "http://127.0.0.1:8765",
  userId: "alice",
  autoCapture: true,
  autoRecall: true,
  topK: 5,
  timeoutMs: 60_000,
});

function parseConfig(raw) {
  const cfg = { ...DEFAULTS, ...(raw || {}) };
  if (typeof cfg.sidecarUrl !== "string") cfg.sidecarUrl = DEFAULTS.sidecarUrl;
  cfg.sidecarUrl = cfg.sidecarUrl.replace(/\/+$/, "");
  cfg.topK = Number(cfg.topK) || DEFAULTS.topK;
  cfg.timeoutMs = Number(cfg.timeoutMs) || DEFAULTS.timeoutMs;
  return cfg;
}

async function call(cfg, path, body) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), cfg.timeoutMs);
  try {
    const res = await fetch(cfg.sidecarUrl + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    if (!res.ok) {
      throw new Error(`sidecar ${path} -> HTTP ${res.status}: ${await res.text()}`);
    }
    return await res.json();
  } finally {
    clearTimeout(t);
  }
}

function isNonInteractive(trigger) {
  if (!trigger) return false;
  return /cron|schedule|webhook|background|system/i.test(String(trigger));
}

function agentScopedUserId(baseUserId, agentId) {
  if (!agentId || agentId === "main") return baseUserId;
  return `${baseUserId}:agent:${agentId}`;
}

function extractAgentId(ctx) {
  return ctx?.agentId || ctx?.agent?.id || ctx?.agent || undefined;
}

function flattenMessages(messages) {
  if (!Array.isArray(messages)) return "";
  const lines = [];
  for (const m of messages) {
    if (!m) continue;
    const role = m.role || m.author || "msg";
    const content = typeof m.content === "string"
      ? m.content
      : Array.isArray(m.content)
        ? m.content.map((c) => (typeof c === "string" ? c : c?.text || "")).join(" ")
        : (m.text || "");
    if (content && content.trim()) lines.push(`${role}: ${content.trim()}`);
  }
  return lines.join("\n");
}

const cogneePlugin = {
  id: "openclaw-cognee",
  name: "Memory (Cognee)",
  description: "Cognee memory backend (FalkorDB graph + vectors) via local sidecar",
  kind: "memory",

  register(api) {
    try {
      const rawCfg = api.pluginConfig;
      try {
        api.logger.info(`openclaw-cognee: raw pluginConfig = ${JSON.stringify(rawCfg)}`);
      } catch {}

      const cfg = parseConfig(rawCfg);
      api.logger.info(
        `openclaw-cognee: registered (sidecar: ${cfg.sidecarUrl}, user: ${cfg.userId}, autoRecall: ${cfg.autoRecall}, autoCapture: ${cfg.autoCapture})`
      );

      if (typeof api.registerService === "function") {
        api.registerService({
          id: "openclaw-cognee",
          start: async () => {
            try {
              await call(cfg, "/healthz");
              api.logger.info("openclaw-cognee: sidecar reachable");
            } catch (err) {
              api.logger.warn(`openclaw-cognee: sidecar NOT reachable: ${String(err)}`);
            }
          },
          stop: () => {
            api.logger.info("openclaw-cognee: stopped");
          },
        });
      } else {
        api.logger.warn("openclaw-cognee: api.registerService not available, skipping lifecycle");
      }

      if (cfg.autoRecall && typeof api.on === "function") {
        api.on("before_agent_start", async (event, ctx) => {
          if (!event?.prompt || event.prompt.length < 5) return;
          if (isNonInteractive(ctx?.trigger)) {
            api.logger.info("openclaw-cognee: skipping recall for non-interactive trigger");
            return;
          }
          const agentId = extractAgentId(ctx);
          const uid = agentScopedUserId(cfg.userId, agentId);
          try {
            const out = await call(cfg, "/recall", {
              query: event.prompt,
              user_id: uid,
              agent_id: agentId,
              top_k: cfg.topK,
            });
            const results = Array.isArray(out?.results) ? out.results : [];
            if (results.length === 0) return;
            const memoryContext = results
              .map((r) => `- ${typeof r === "string" ? r : JSON.stringify(r)}`)
              .join("\n");
            api.logger.info(`openclaw-cognee: injecting ${results.length} memories into context`);
            return {
              prependContext:
                `<relevant-memories>\n` +
                `The following are stored memories for user "${uid}". ` +
                `Use them to personalize your response:\n` +
                `${memoryContext}\n` +
                `</relevant-memories>`,
            };
          } catch (err) {
            api.logger.warn(`openclaw-cognee: recall failed: ${String(err)}`);
          }
        });
      }

      if (cfg.autoCapture && typeof api.on === "function") {
        api.on("agent_end", async (event, ctx) => {
          if (!event?.success || !event?.messages || event.messages.length === 0) return;
          if (isNonInteractive(ctx?.trigger)) {
            api.logger.info("openclaw-cognee: skipping capture for non-interactive trigger");
            return;
          }
          const agentId = extractAgentId(ctx);
          const uid = agentScopedUserId(cfg.userId, agentId);
          const text = flattenMessages(event.messages);
          if (!text || text.length < 10) return;
          try {
            await call(cfg, "/remember", { text, user_id: uid, agent_id: agentId });
            api.logger.info(`openclaw-cognee: captured turn for ${uid} (${text.length} chars)`);
          } catch (err) {
            api.logger.warn(`openclaw-cognee: capture failed: ${String(err)}`);
          }
        });
      }
    } catch (err) {
      try {
        api.logger.error(`openclaw-cognee: register threw: ${err && err.stack ? err.stack : String(err)}`);
      } catch {}
      throw err;
    }
  },
};

export default cogneePlugin;
