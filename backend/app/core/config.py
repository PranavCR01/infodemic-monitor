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

    # Migrations
    RUN_MIGRATIONS: bool = True  # set False on Railway worker service

    # Auth
    REQUIRE_AUTH: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Temporary: replaced by main inference provider in Slice C
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
