import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("未找到 DATABASE_URL，请检查 .env 文件")

engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
        {"t": table, "c": column},
    ).first()
    return row is not None


def migrate() -> None:
    """为已存在的表补充新增列（create_all 不会给已有表加列）。

    幂等：仅当列不存在时才 ALTER，可安全在每次启动时调用。
    """
    with engine.begin() as conn:
        for col in ("file_hash", "content_hash"):
            if not _column_exists(conn, "data_uploads", col):
                conn.execute(text(f"ALTER TABLE data_uploads ADD COLUMN {col} VARCHAR(64)"))
        if not _column_exists(conn, "solder_paste_data", "row_hash"):
            conn.execute(text("ALTER TABLE solder_paste_data ADD COLUMN row_hash VARCHAR(64)"))
