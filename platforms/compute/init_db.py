"""
数据库初始化脚本
创建所有表结构
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app.core.database import engine, Base
from backend.app.models.experiment import Experiment, DataUpload, SolderPasteData

def init_db():
    """创建所有数据库表"""
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("数据库表创建完成！")

if __name__ == "__main__":
    init_db()