from __future__ import annotations

import os
import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

# MS SQL連線設定 (依據 Terry 處長提供之開發資料庫 dev.db.sysco / eLearn)
DEFAULT_MSSQL_URL = "mssql+pymssql://lrnuser:userlrn@dev.db.sysco/eLearn"

# 允許由環境變數 DATABASE_URL 或 MSSQL_CONN_STR 自訂
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("MSSQL_CONN_STR", DEFAULT_MSSQL_URL)
)

DB_DIR = Path(__file__).resolve().parent / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_FALLBACK_URL = f"sqlite:///{DB_DIR / 'app.db'}"

def create_app_engine():
    """創建設立 SQLAlchemy Engine，優先連線 MS SQL dev.db.sysco (eLearn)，網路斷開時自動降級相容 SQLite"""
    url = SQLALCHEMY_DATABASE_URL
    logging.info(f"Connecting to Database target: {url.split('@')[-1] if '@' in url else url}")
    
    if "sqlite" in url:
        return create_engine(url, connect_args={"check_same_thread": False})
    
    try:
        # 建立 MS SQL Server (pymssql) 引擎
        mssql_engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        # 測試連線
        with mssql_engine.connect() as conn:
            logging.info("Successfully connected to MS SQL Server dev.db.sysco [eLearn]!")
        return mssql_engine
    except Exception as err:
        logging.warning(f"Unable to connect to MS SQL Server dev.db.sysco ({err}). Falling back to local SQLite DB.")
        return create_engine(SQLITE_FALLBACK_URL, connect_args={"check_same_thread": False})

engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

