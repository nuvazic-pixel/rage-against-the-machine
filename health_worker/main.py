"""
Dedicated health worker — probes each Ollama node on a fixed interval
and writes results to Redis. Decoupled from router instances so multiple
API replicas share consistent health state without competing writes.
"""
import asyncio
import json
import os
import time
import httpx
import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
OLLAMA_NODES_RAW = os.getenv("OLLAMA_NODES", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3:8b-instruct-q4_K_M")
HEALTH_INTERVAL = int(os.getenv("HEALTH_INTERVAL", "5"))
MAX_IN_FLIGHT = int(os.getenv("MAX_IN_FLIGHT", "4"))


def parse_nodes() -> dict[str, str]:
    urls = [u.strip() for u in OLLAMA_NODES_RAW.split(",") if u.strip()]
    return {f"ollama{i + 1}": url for i, url in enumerate(urls)}


async def probe_node(client: httpx.AsyncClient, node_name: str, base_url: str) -> bool:
    """
    Real health check: actually calls inference with 1 token.
    Proves model is loaded and responding — not just container alive.
    """
    try:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        log.debug("probe_ok", node=node_name)
        return True
    except Exception as exc:
        log.warning("probe_failed", node=node_name, error=str(exc))
        return False


async def warmup_node(client: httpx.AsyncClient, base_url: str) -> None:
    """Fire a warmup call to ensure model weights are loaded into memory."""
    try:
        await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 1,
            },
            timeout=60.0,  # Allow longer for initial load
        )
        log.info("warmup_complete", url=base_url)
    except Exception as exc:
        log.warning("warmup_failed", url=base_url, error=str(exc))


async def register_nodes(r: aioredis.Redis, nodes: dict[str, str]) -> None:
    """Write static node config to Redis on startup."""
    pipe = r.pipeline()
    for node_name, base_url in nodes.items():
        pipe.sadd("llm:nodes", node_name)
        pipe.set(f"llm:node:{node_name}:models", json.dumps([LLM_MODEL]))
        pipe.set(f"llm:node:{node_name}:max_in_flight", MAX_IN_FLIGHT)
        pipe.set(f"llm:node:{node_name}:in_flight", 0)
        pipe.set(f"llm:node:{node_name}:avg_latency_ms", 0)
        pipe.set(f"llm:node:{node_name}:error_count", 0)
        pipe.set(f"llm:node:{node_name}:url", base_url)
    await pipe.execute()
    log.info("nodes_registered", nodes=list(nodes.keys()))


async def health_loop(r: aioredis.Redis, nodes: dict[str, str]) -> None:
    async with httpx.AsyncClient() as client:
        # Warmup all nodes on startup
        log.info("warming_up_nodes")
        await asyncio.gather(*[warmup_node(client, url) for url in nodes.values()])

        while True:
            start = time.perf_counter()
            probe_tasks = {
                name: probe_node(client, name, url)
                for name, url in nodes.items()
            }
            results = await asyncio.gather(*probe_tasks.values(), return_exceptions=True)

            pipe = r.pipeline()
            for node_name, result in zip(probe_tasks.keys(), results):
                healthy = result is True
                pipe.set(f"llm:node:{node_name}:healthy", 1 if healthy else 0)
                pipe.set(f"llm:node:{node_name}:last_heartbeat", int(time.time()))
                if healthy:
                    # Reset error count on recovery
                    pipe.set(f"llm:node:{node_name}:error_count", 0)
            await pipe.execute()

            elapsed = time.perf_counter() - start
            sleep_time = max(0.1, HEALTH_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)


async def main() -> None:
    nodes = parse_nodes()
    log.info("health_worker_start", nodes=nodes, interval=HEALTH_INTERVAL)

    r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    # Wait for Redis to be ready
    for attempt in range(30):
        try:
            await r.ping()
            break
        except Exception:
            log.info("waiting_for_redis", attempt=attempt)
            await asyncio.sleep(2)
    else:
        log.error("redis_not_available")
        raise SystemExit(1)

    await register_nodes(r, nodes)
    await health_loop(r, nodes)


if __name__ == "__main__":
    asyncio.run(main())
