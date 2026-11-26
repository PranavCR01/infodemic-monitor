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
    # Legacy shared secret (HS256). Optional fallback (T48): leave empty once the
    # project's legacy secret is revoked. Asymmetric tokens (ES256/RS256) are checked
    # against the project's JWKS at SUPABASE_URL + /auth/v1/.well-known/jwks.json.
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_JWKS_CACHE_SECONDS: int = 600       # how long a fetched JWKS is fresh
    SUPABASE_JWKS_MIN_REFETCH_SECONDS: int = 30  # at most one JWKS fetch per interval

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
    # Authoritative references for facts of record (T17, design §6): allow-listed pages
    # in config/reference_sources.yaml, searched alongside PubMed for claims tagged
    # fact_of_record. Off by default; only read when USE_GRAPH_PIPELINE is on. Needs
    # migration 0009 (reference_snapshots) before it is turned on.
    USE_REFERENCE_SOURCES: bool = False

    # Upload safeguards (T20, design §1/§15): T10's input limits (size, duration,
    # format, corrupt-file check, rate limit, daily quota) on the legacy
    # POST /videos/upload route. Off by default so existing clients see no change.
    # The signed-upload endpoints (/v1/videos/uploads, /v1/videos) always apply them.
    UPLOAD_SAFEGUARDS: bool = False

    # Playback (T29, design §15 "short-lived signed URLs"): lifetime of the signed
    # read URL the result page's video player gets from GET /v1/jobs/{id}/playback.
    # Long enough to start and seek a 3-minute video; the response carries
    # expires_at so the player asks again when it runs out.
    PLAYBACK_URL_TTL_SECONDS: int = 600

    # Deliberate re-analysis (T55): POST /v1/videos/{id}/reanalyse allows each user at
    # most REANALYSIS_MAX_PER_VIDEO re-runs of one video per rolling
    # REANALYSIS_WINDOW_HOURS (each re-run is one more paid analysis). Over the limit the
    # route answers 429 with Retry-After. On top of that, each user may start at most
    # REANALYSIS_MAX_PER_USER re-runs in the same window across all videos (admins
    # included). 0 in either turns the route off for everyone.
    REANALYSIS_MAX_PER_VIDEO: int = 3
    REANALYSIS_MAX_PER_USER: int = 20
    REANALYSIS_WINDOW_HOURS: int = 24

    # Migrations
    RUN_MIGRATIONS: bool = True  # set False on Railway worker service

    # Auth
    REQUIRE_AUTH: bool = True
    # Role of the local dev user when REQUIRE_AUTH is off (T27): analyst, reviewer or
    # admin. Ignored when auth is on; real roles come from the JWT's app_metadata.
    DEV_USER_ROLE: str = "analyst"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
