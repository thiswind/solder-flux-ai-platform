"""
数据管理平台数据库初始化脚本
"""
import os
import sys

# 添加 backend 到 Python 路径
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, backend_path)

from sqlalchemy import create_engine
from app.models.entities import Base
from app.core.config import get_settings

def init_db():
    """创建所有数据库表"""
    settings = get_settings()
    print(f"正在连接数据库: {settings.database_url}")
    engine = create_engine(settings.database_url)
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成！")

if __name__ == "__main__":
    init_db()
