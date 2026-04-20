# Synapse — Local-First RAG SaaS Platform

Production-ready, self-hosted RAG platform. 100% local inference via Ollama. No data leaves your server.

## Quick Start

```bash
cp .env.example .env     # Edit: change SECRET_KEY + passwords
docker compose up -d     # Pulls LLM (~4 GB first run)
```

| Service    | URL                        |
|------------|----------------------------|
| Frontend   | http://localhost:3000      |
| API docs   | http://localhost:8000/docs |
| Grafana    | http://localhost:3001      |

## Architecture

```
Browser (React)
  └── FastAPI (async, JWT auth, rate limiting)
        ├── PostgreSQL + pgvector  (chunks, users, sessions)
        ├── Redis  (routing state, search cache, rate limits)
        └── LLM Router (distributed, atomic Lua reservation)
              ├── Ollama node 1
              └── Ollama node 2
              ↑
        Health Worker (dedicated node monitor, 5s interval)
```

## Retrieval Pipeline

```
query → embed (MiniLM) → pgvector top-50
  → BM25 fusion (0.7 vector + 0.3 BM25, normalized)
  → CrossEncoder rerank (top-5 → top-3)
  → Ollama LLM (grounded, temperature=0)
  → answer + sources
```

## Configuration (.env)

```env
LLM_MODEL=llama3:8b-instruct-q4_K_M   # or mistral:7b-instruct-q4_K_M
SECRET_KEY=<min-32-chars-random>
POSTGRES_PASSWORD=<strong-password>
```

## Scale

Add Ollama nodes: extend `OLLAMA_NODES=http://ollama1:11434,http://ollama2:11434,...`
Scale API: `docker compose up -d --scale api=3` (stateless, shares Redis)

## Plans

| Plan       | Queries/day |
|------------|-------------|
| free       | 20          |
| pro        | 500         |
| enterprise | 10,000      |

Upgrade: `UPDATE users SET plan = 'pro' WHERE email = '...';`

## Production Checklist

- [ ] Rotate SECRET_KEY (32+ chars, random)
- [ ] Change POSTGRES_PASSWORD + GRAFANA_PASSWORD  
- [ ] Set ALLOWED_ORIGINS to your domain
- [ ] Add TLS via Nginx/Traefik in front
- [ ] Back up postgres_data volume

## Supported File Types

.txt · .md · .py · .js · .ts · .json · .csv · .yaml · .yml · .pdf (needs `pypdf`)
