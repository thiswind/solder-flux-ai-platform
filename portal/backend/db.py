"""数据库引擎与会话 — SQLite 文件库, 与compute/data 库隔离。"""
from __future__ import annotations

import os
import sqlite3

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from . import models
from .auth import hash_password

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "yunxi_portal.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _sqlite_add_column_if_missing(table: str, column: str, col_def: str) -> None:
    """轻量级 SQLite 迁移: 给已存在的表补列。SQLAlchemy create_all 不会加列。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """建表并写入默认管理员账号；旧库自动补 email 列。"""
    models.Base.metadata.create_all(bind=engine)
    # 兼容旧库: 给 users 表补 email 列(注册场景需要)
    _sqlite_add_column_if_missing("users", "email", "VARCHAR(120)")
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.username == "admin").first()
        if not existing:
            db.add(
                models.User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    role="Admin",
                    display_name="系统管理员",
                )
            )
            db.commit()
            print("[Portal] 已创建默认管理员: admin / admin123")
    finally:
        db.close()
