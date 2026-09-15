from __future__ import annotations

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logging.basicConfig(level=logging.INFO)

class Base(DeclarativeBase):
    pass

# 依序載入環境設定檔
app_env = os.getenv("APP_ENV", "development").lower()
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    for env_name in [f".env.{app_env}", ".env.local", ".env"]:
        for search_dir in [base_dir, os.path.join(base_dir, "backend")]:
            env_file = os.path.join(search_dir, env_name)
            if os.path.exists(env_file):
                load_dotenv(env_file, override=False)
except ImportError:
    pass

# 重新取得載入後的 APP_ENV
app_env = os.getenv("APP_ENV", "development").lower()
is_production = app_env in ["production", "prod"]

# 1. 測試/開發環境 (Development):
DEV_MSSQL_URL = "mssql+pymssql://lrnuser:userlrn@dev.db.sysco/eLearn"

# 2. 正式環境 (Production):
# 帳號/密碼為 Terry 處長提供之正式連線資訊 (lrnuser / User39Lrn)
prod_host = os.getenv("PROD_DB_HOST", os.getenv("DB_HOST", "prd.db.sysco"))
prod_db = os.getenv("PROD_DB_NAME", os.getenv("DB_NAME", "eLearn"))
PROD_MSSQL_URL = f"mssql+pymssql://lrnuser:User39Lrn@{prod_host}/{prod_db}"

# 根據環境選擇預設連線字串
DEFAULT_MSSQL_URL = PROD_MSSQL_URL if is_production else DEV_MSSQL_URL

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("MSSQL_CONN_STR", DEFAULT_MSSQL_URL)
)

def create_app_engine():
    """建立專屬 MS SQL Server 連線引擎（支援開發與正式環境切換）"""
    url = SQLALCHEMY_DATABASE_URL
    masked_url = url.split('@')[-1] if '@' in url else url
    env_label = "PRODUCTION (正式營運)" if is_production else "DEVELOPMENT (測試/開發)"
    logging.info(f"Connecting to MS SQL Server [{env_label}]: {masked_url}")
    
    # 建立 MS SQL Server (pymssql) 引擎 (Unicode 由 pymssql 原生處理)
    mssql_engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
    
    # 測試連線
    with mssql_engine.connect() as conn:
        logging.info(f"Successfully connected to MS SQL Server [{env_label}] ({masked_url})!")
    return mssql_engine

engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


