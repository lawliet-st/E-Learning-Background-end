from __future__ import annotations

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

# MS SQL Server 正式開發資料庫連線資訊 (dev.db.sysco / eLearn)
# 完全停用 SQLite，全系統嚴格連線至 MS SQL Server
DEFAULT_MSSQL_URL = "mssql+pymssql://lrnuser:userlrn@dev.db.sysco/eLearn"

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("MSSQL_CONN_STR", DEFAULT_MSSQL_URL)
)

def create_app_engine():
    """建立專屬 MS SQL Server dev.db.sysco [eLearn] 連線引擎（SQLite 後備機制已完全停用）"""
    url = SQLALCHEMY_DATABASE_URL
    logging.info(f"Strictly Connecting to MS SQL Server dev.db.sysco: {url.split('@')[-1] if '@' in url else url}")
    
    # 建立 MS SQL Server (pymssql) 引擎，指定 charset=cp950 解決繁體中文亂碼
    connect_args = {"charset": "cp950"}
    mssql_engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, pool_size=10, max_overflow=20)
    
    # 測試連線
    with mssql_engine.connect() as conn:
        logging.info("Successfully connected to MS SQL Server dev.db.sysco [eLearn]!")
    return mssql_engine

engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


