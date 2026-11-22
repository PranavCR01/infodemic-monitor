from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database — no defaults: missing env var must fail loudly, not connect to localhost
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "videos"
    SUPABASE_JWT_SECRET: str = ""

    # Inference
    INFERENCE_PROVIDER: str = "openai"  # "openai" | "anthropic"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # LangGraph pipeline (T11, #38). Off by default: the single-call provider above
    # stays the live path. When on, the graph runs on every video and falls back to
    # the single call on an exception, a timeout or a run without a result.
    USE_GRAPH_PIPELINE: bool = False
    GRAPH_PIPELINE_VERSION: str = "graph_v1"
    GRAPH_TIMEOUT_SECONDS: float = 900.0       # wall clock for one graph run
    GRAPH_MODEL_TIMEOUT_SECONDS: float = 60.0  # one provider call
    # Postgres DSN for LangGraph checkpoints (a `langgraph` schema). Empty = in-memory
    # checkpoints: a retried task then starts the graph from the beginning.
    LANGGRAPH_CHECKPOINT_DSN: str = ""
    # Share the retrieval MCP server's Redis query cache (T13) with the graph's workers.
    GRAPH_SHARED_RETRIEVAL: bool = True

    # Whisper
    WHISPER_PROVIDER: str = "faster_whisper"  # "faster_whisper" | "openai"
    WHISPER_MODEL_SIZE: str = "base"  # tiny | base | small | medium | large-v3

    # Storage
    STORAGE_BACKEND: str = "supabase"  # "supabase" | "local"
    LOCAL_STORAGE_ROOT: str = "/app/storage"

    # Celery
    CELERY_CONCURRENCY: int = 1

    # Pipeline limits
    MAX_INPUT_CHARS: int = 128_000
    PUBMED_RESULTS_PER_CLAIM: int = 2

    # Evidence retrieval for the LangGraph pipeline (app/core/retrieval).
    # Both NCBI values are optional: a key raises NCBI's limit from 3 to 10 requests/s.
    NCBI_API_KEY: str = ""
    NCBI_EMAIL: str = ""
    RETRIEVAL_MAX_RESULTS_PER_QUERY: int = 20

    # Migrations
    RUN_MIGRATIONS: bool = True  # set False on Railway worker service

    # Auth
    REQUIRE_AUTH: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
