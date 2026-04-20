"""
Distributed, stateless Ollama router backed by Redis atomic coordination.

Each router instance:
  - Reads node health/load from Redis
  - Reserves capacity via Lua (atomic)
  - Releases on completion
  - Falls back through model list on failure

Multiple router instances (across replicas) share state through Redis.
"""
import asyncio
import time
import json
from openai import AsyncOpenAI
import redis.asyncio as aioredis
import structlog

from app.config import get_settings
from app.utils.cache import get_redis

log = structlog.get_logger()

# ─────────────────────────────────────────
# Lua: atomic pick-and-reserve
# Returns node name or nil if cluster saturated
# ─────────────────────────────────────────
_RESERVE_LUA = """
local nodes = redis.call('SMEMBERS', KEYS[1])
local best_node = nil
local best_score = nil

for _, node in ipairs(nodes) do
    local healthy     = redis.call('GET', 'llm:node:' .. node .. ':healthy')
    local in_flight   = tonumber(redis.call('GET', 'llm:node:' .. node .. ':in_flight') or '0')
    local max_flight  = tonumber(redis.call('GET', 'llm:node:' .. node .. ':max_in_flight') or '4')
    local latency     = tonumber(redis.call('GET', 'llm:node:' .. node .. ':avg_latency_ms') or '999999')
    local models_json = redis.call('GET', 'llm:node:' .. node .. ':models')

    if healthy == '1' and in_flight < max_flight and models_json
       and string.find(models_json, ARGV[1], 1, true) then
        local score = in_flight * 100000 + latency
        if best_score == nil or score < best_score then
            best_score = score
            best_node  = node
        end
    end
end

if best_node then
    redis.call('INCR', 'llm:node:' .. best_node .. ':in_flight')
    return best_node
end
return nil
"""


class DistributedOllamaRouter:
    def __init__(self) -> None:
        cfg = get_settings()
        self._node_urls: dict[str, str] = {
            f"ollama{i + 1}": url.strip()
            for i, url in enumerate(cfg.ollama_node_list)
        }
        self._clients: dict[str, AsyncOpenAI] = {
            name: AsyncOpenAI(
                base_url=f"{url}/v1",
                api_key="ollama",
                timeout=30.0,
            )
            for name, url in self._node_urls.items()
        }
        self._preferred_models = [
            cfg.llm_model,
            "mistral:7b-instruct-q4_K_M",  # fallback
        ]
        self._global_sem = asyncio.Semaphore(50)  # hard cap on concurrency

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 300,
    ) -> str:
        cfg = get_settings()
        async with self._global_sem:
            last_err: Exception | None = None

            for model in self._preferred_models:
                # Retry once per model (transient errors)
                for attempt in range(2):
                    node = await self._reserve(model)
                    if node is None:
                        log.warning("no_capacity", model=model)
                        break  # Try next model

                    start = time.perf_counter()
                    success = False
                    try:
                        client = self._clients[node]
                        resp = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model,
                                temperature=temperature,
                                messages=messages,
                                max_tokens=max_tokens,
                            ),
                            timeout=30.0,
                        )
                        success = True
                        return resp.choices[0].message.content

                    except Exception as exc:
                        last_err = exc
                        log.warning(
                            "llm_request_error",
                            node=node,
                            model=model,
                            attempt=attempt,
                            error=str(exc),
                        )
                    finally:
                        latency_ms = (time.perf_counter() - start) * 1000
                        await self._release(node, latency_ms, success)

            raise RuntimeError(
                f"All LLM nodes/models exhausted. Last error: {last_err}"
            )

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    async def _reserve(self, model: str) -> str | None:
        r = await get_redis()
        result = await r.eval(_RESERVE_LUA, 1, "llm:nodes", model)
        if result is None:
            return None
        return result if isinstance(result, str) else result.decode()

    async def _release(
        self,
        node: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.decr(f"llm:node:{node}:in_flight")
        # Exponential moving average for latency
        pipe.set(f"llm:node:{node}:avg_latency_ms", int(latency_ms))
        if success:
            pipe.set(f"llm:node:{node}:healthy", 1)
            pipe.set(f"llm:node:{node}:error_count", 0)
        else:
            pipe.incr(f"llm:node:{node}:error_count")
            # Mark unhealthy after 3 consecutive errors
            error_key = f"llm:node:{node}:error_count"
            errors = await r.get(error_key)
            if errors and int(errors) >= 3:
                pipe.set(f"llm:node:{node}:healthy", 0)
        await pipe.execute()

    async def get_status(self) -> list[dict]:
        """Returns current routing table from Redis (for /health endpoint)."""
        r = await get_redis()
        nodes = await r.smembers("llm:nodes")
        result = []
        for node in nodes:
            node_name = node if isinstance(node, str) else node.decode()
            healthy = await r.get(f"llm:node:{node_name}:healthy")
            in_flight = await r.get(f"llm:node:{node_name}:in_flight")
            latency = await r.get(f"llm:node:{node_name}:avg_latency_ms")
            result.append({
                "node": node_name,
                "healthy": healthy == "1" if healthy else False,
                "in_flight": int(in_flight or 0),
                "avg_latency_ms": int(latency or 0),
                "url": self._node_urls.get(node_name, "unknown"),
            })
        return result


# Singleton
_router: DistributedOllamaRouter | None = None


def get_router() -> DistributedOllamaRouter:
    global _router
    if _router is None:
        _router = DistributedOllamaRouter()
    return _router
