from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


class Settings:
    app_name = "Jubidate AI"
    max_sessions = 10
    max_active_debates = 3
    request_timeout_seconds = int(os.getenv("LITELLM_TIMEOUT_SECONDS", "120"))
    mock_llm = os.getenv("MOCK_LLM_RESPONSES", "false").lower() == "true"

    @property
    def database_path(self) -> Path:
        raw_path = os.getenv("DATABASE_PATH", "backend/data/debate_council.db")
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def cors_origins(self) -> list[str]:
        raw_origins = os.getenv("CORS_ORIGINS") or os.getenv(
            "FRONTEND_ORIGIN", "http://localhost:6001"
        )
        origins: list[str] = []
        for origin in raw_origins.split(","):
            cleaned = origin.strip()
            if not cleaned:
                continue
            origins.append(cleaned)
            if "localhost" in cleaned:
                origins.append(cleaned.replace("localhost", "127.0.0.1"))
            if "127.0.0.1" in cleaned:
                origins.append(cleaned.replace("127.0.0.1", "localhost"))
        for origin in ("http://localhost:6001", "http://127.0.0.1:6001"):
            origins.append(origin)
        return list(dict.fromkeys(origins))

    @property
    def cors_origin_regex(self) -> str | None:
        if os.getenv("ALLOW_LOCALHOST_PORTS", "false").lower() not in {"1", "true", "yes", "on"}:
            return None
        return r"http://(localhost|127\.0\.0\.1):[0-9]+"


settings = Settings()
