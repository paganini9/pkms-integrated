"""설정 — 환경변수만이 진실원. 키·시크릿은 절대 코드/파일에 두지 않는다."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # 서비스
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # 저장소 (임베디드·영속)
    oxigraph_path: Path = KNOWLEDGE_DIR / "data" / "oxigraph"
    chroma_path: Path = KNOWLEDGE_DIR / "data" / "chroma"
    ontology_dir: Path = KNOWLEDGE_DIR / "ontology"
    # 상위 온톨로지 승인 편집 오버레이(영속) — 시드(읽기전용)와 분리, 재기동 후 유지 (T-85)
    upper_overlay_path: Path = KNOWLEDGE_DIR / "data" / "upper_overlay.ttl"

    # MOCK 우선 — 키·모델 없이 전 흐름이 동작해야 한다
    embedding_provider: str = "mock"  # mock | local | solar
    local_embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embed_dim: int = 384  # 컬렉션 차원 검증용

    # 추론
    reasoner_timeout_s: int = 60
    satisfy_cache_size: int = 256

    @property
    def seed_ttl(self) -> list[Path]:
        """기동 시 멱등 적재하는 시드 (02 데이터 Agent 소유)."""
        return [
            self.ontology_dir / "m0.ttl",
            self.ontology_dir / "m1_wiper.ttl",
            self.ontology_dir / "rules.ttl",
            self.ontology_dir / "shapes.ttl",
        ]


settings = Settings()
