from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_user: str = "rag"
    db_password: str = "ragpassword"
    db_name: str = "ragdb"
    db_port: int = 5432

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # LLM
    llm_model: str = "llama3:8b-instruct-q4_K_M"
    ollama_nodes: str = "http://localhost:11434"

    # Auth
    secret_key: str = "change-me-in-production-32chars!!"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # App
    environment: str = "production"
    allowed_origins: str = "http://localhost:3000"

    # RAG tuning
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 300
    chunk_overlap_sentences: int = 1
    vector_top_k: int = 50
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    rerank_top_n: int = 5
    final_top_k: int = 3
    max_context_chars: int = 1500
    cache_ttl_seconds: int = 300

    # Rate limits (per plan)
    free_queries_per_day: int = 20
    pro_queries_per_day: int = 500
    enterprise_queries_per_day: int = 10000

    @property
    def ollama_node_list(self) -> list[str]:
        return [n.strip() for n in self.ollama_nodes.split(",") if n.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
