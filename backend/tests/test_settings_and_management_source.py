from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.management_source import ManagementSource
from app.repositories.management_source import ensure_default_management_source


def test_settings_accepts_comma_separated_cors_origins_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AUTHTRACE_DATABASE_URL=sqlite+pysqlite:///:memory:",
                "AUTHTRACE_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.cors_allowed_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


def test_ensure_default_management_source_recovers_from_concurrent_insert(tmp_path: Path) -> None:
    db_path = tmp_path / "authtrace.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    ManagementSource.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

    settings = Settings(
        AUTHTRACE_DATABASE_URL="sqlite+pysqlite:///:memory:",
        AUTHTRACE_MANAGEMENT_BASE_URL="http://localhost:8787",
        AUTHTRACE_MANAGEMENT_SOURCE_KEY="main",
        AUTHTRACE_MANAGEMENT_SOURCE_NAME="默认管理端",
        AUTHTRACE_MANAGEMENT_SOURCE_DESCRIPTION="并发插入测试",
    )

    with session_factory() as db:
        original_flush = db.flush
        inserted = False

        def concurrent_flush(*args: object, **kwargs: object) -> None:
            nonlocal inserted
            if not inserted:
                inserted = True
                with session_factory() as competing_db:
                    competing_db.add(
                        ManagementSource(
                            source_key=settings.management_source_key,
                            source_name="竞争写入",
                            base_url="http://stale.example",
                            description="stale",
                            is_enabled=False,
                        )
                    )
                    competing_db.commit()
            original_flush(*args, **kwargs)

        db.flush = concurrent_flush  # type: ignore[method-assign]

        source = ensure_default_management_source(db, settings)
        db.commit()

        assert source.source_key == "main"
        assert source.source_name == settings.management_source_name
        assert source.base_url == settings.management_base_url
        assert source.description == settings.management_source_description
        assert source.is_enabled is True

    with session_factory() as verify_db:
        rows = verify_db.scalars(select(ManagementSource)).all()
        assert len(rows) == 1
        assert rows[0].source_name == settings.management_source_name
        assert rows[0].base_url == settings.management_base_url
