"""
E-Learning 系統與 資訊部 (ISD) MS SQL Server 同步腳本
支援連線至 dev.db.sysco 的 [eLearn].[dbo].[elearning] 資料表 (亦相容 [HRM].[dbo].[eLEARNING] VIEW)
自動同步員工基本資料與歷年績效。

預設連線資訊：
- Server: dev.db.sysco
- Database: eLearn
- User / Pass: lrnuser / userlrn
"""

import os
import json
import logging
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import User
from backend.auth import get_password_hash

logging.basicConfig(level=logging.INFO)

from datetime import datetime

# 預設連線字串 (可由環境變數 MSSQL_CONN_STR 覆蓋)
DEFAULT_MSSQL_CONN_STR = os.getenv(
    "MSSQL_CONN_STR",
    "mssql+pymssql://lrnuser:userlrn@dev.db.sysco/eLearn"
)

def parse_performance_history(row_mapping: dict) -> list[dict]:
    """
    解析來自 MS SQL View / Table 的歷年績效考核評分。
    優先支援相對年份平舖欄位 (perf_y1_rating ~ perf_y5_rating)，自動動態對應近 5 年年份。
    亦備選支援固定年份 (perf_2025) 或 JSON / Key-Value 字串格式。
    """
    records = []
    current_year = datetime.now().year

    # 1. 檢查相對年份平舖欄位 perf_y1_rating ~ perf_y5_rating
    has_flat_y = any(f"perf_y{i}_rating" in row_mapping for i in range(1, 6))
    if has_flat_y:
        for i in range(1, 6):
            col = f"perf_y{i}_rating"
            rating_val = row_mapping.get(col)
            if rating_val and str(rating_val).strip():
                eval_year = str(current_year - i)
                records.append({"year": eval_year, "rating": str(rating_val).strip()})
        if records:
            return records

    # 2. 檢查固定西元年份欄位 (例如 perf_2025, perf_2024...)
    for year_offset in range(1, 6):
        y_str = str(current_year - year_offset)
        col = f"perf_{y_str}"
        if col in row_mapping and row_mapping[col]:
            records.append({"year": y_str, "rating": str(row_mapping[col]).strip()})
    if records:
        return records

    # 3. 備選支援單一字串格式 (JSON 或 Key-Value)
    raw_perf = row_mapping.get("performance_evaluations")
    if not raw_perf:
        return []
    
    raw_perf = str(raw_perf).strip()
    if raw_perf.startswith("[") and raw_perf.endswith("]"):
        try:
            data = json.loads(raw_perf)
            if isinstance(data, list):
                res = []
                for item in data:
                    r = item.get("rating", "C")
                    res.append({"year": str(item.get("year")), "rating": r})
                return res
        except Exception:
            pass

    pairs = raw_perf.split(";")
    for pair in pairs:
        if ":" in pair:
            parts = pair.split(":")
            if len(parts) == 2 and parts[0].strip().isdigit():
                records.append({
                    "year": parts[0].strip(),
                    "rating": parts[1].strip()
                })
    return records

def get_row_value(row: dict, keys: list[str], default: str = "") -> str:
    """彈性從 Data Row 中嘗試多個可能的欄位名稱"""
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return default

def sync_users_from_mssql(mssql_connection_string: Optional[str] = None):
    """
    從 MS SQL Server [eLearn].[dbo].[elearning] 同步員工資料至 E-Learning 資料庫
    """
    conn_str = mssql_connection_string or DEFAULT_MSSQL_CONN_STR
    logging.info(f"Starting MS SQL synchronization using string: {conn_str.split('@')[-1] if '@' in conn_str else conn_str}")
    
    mssql_engine = create_engine(conn_str, connect_args={"charset": "cp950"})
    db: Session = SessionLocal()
    
    try:
        with mssql_engine.connect() as conn:
            # 優先嘗試 [eLearn].[dbo].[elearning]，若失敗則切換至 [HRM].[dbo].[eLEARNING]
            try:
                query = text("SELECT * FROM [dbo].[elearning]")
                result = conn.execute(query)
            except Exception as table_err:
                logging.warning(f"Querying [dbo].[elearning] failed, attempting [HRM].[dbo].[eLEARNING]: {table_err}")
                query = text("SELECT * FROM [HRM].[dbo].[eLEARNING]")
                result = conn.execute(query)

            rows = result.mappings().all()
            
            synced_count = 0
            for row in rows:
                row_dict = dict(row)
                # 彈性對應 ISD 欄位 (EMPID / employee_id, HECNAME / name, IDNO / national_id, STATE / status, DEPT_NO / department)
                emp_id = get_row_value(row_dict, ["EMPID", "employee_id", "emp_id"])
                if not emp_id:
                    continue

                name = get_row_value(row_dict, ["HECNAME", "name", "emp_name"])
                national_id = get_row_value(row_dict, ["IDNO", "national_id", "id_no"])
                status = get_row_value(row_dict, ["STATE", "status", "state"])
                dept = get_row_value(row_dict, ["DEPT_NO", "department", "dept_no"])
                title = get_row_value(row_dict, ["TITLE", "title"])
                email = get_row_value(row_dict, ["EMAIL", "email"])
                cpny_id = get_row_value(row_dict, ["CPNYID", "cpny_id"])
                join_date = get_row_value(row_dict, ["datein", "join_date", "DATEIN"])
                
                # 判斷在職狀態
                is_active = status in ["在職", "Active", "1", "Y", ""]
                
                # 尋找現有使用者
                existing_user = db.query(User).filter(User.employee_id == emp_id).first()
                perf_history = parse_performance_history(row_dict)
                
                if existing_user:
                    # 更新基本資訊
                    if name:
                        existing_user.name = name
                    if email:
                        existing_user.email = email
                    if dept:
                        existing_user.department = dept
                    if title:
                        existing_user.title = title
                    
                    # 更新 profile JSON
                    current_profile = existing_user.profile or {}
                    if join_date:
                        current_profile["joinDate"] = join_date
                    if cpny_id:
                        current_profile["cpnyId"] = cpny_id
                    if perf_history:
                        current_profile["performanceHistory"] = perf_history
                    existing_user.profile = current_profile
                    
                    # 若已離職可變更角色
                    if not is_active:
                        logging.info(f"User {emp_id} is inactive, setting role to inactive")
                        existing_user.role = "inactive"
                else:
                    # 新增同仁帳號
                    if not is_active:
                        continue # 離職人員不新增
                        
                    hashed_pwd = get_password_hash(national_id) if national_id else get_password_hash("123456")
                    
                    new_user = User(
                        id=f"usr_{emp_id}",
                        employee_id=emp_id,
                        hashed_password=hashed_pwd,
                        name=name or f"員工{emp_id}",
                        email=email or f"{emp_id}@shengyusteel.com",
                        department=dept or "未分配部門",
                        title=title or "同仁",
                        role="employee",
                        profile={
                            "age": 30,
                            "cpnyId": cpny_id,
                            "joinDate": join_date,
                            "performanceHistory": perf_history,
                            "skills": [],
                            "nineBoxPosition": {"performance": "Medium", "potential": "Medium"},
                            "assessment": {"hpi": 0, "hds": 0, "mvpi": 0, "completed": False},
                            "tags": []
                        }
                    )
                    db.add(new_user)
                synced_count += 1
            
            db.commit()
            logging.info(f"Successfully synced {synced_count} employee records from MS SQL.")
            return synced_count
    except Exception as e:
        db.rollback()
        logging.error(f"MS SQL sync failed: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    logging.info("MSSQL Sync Module initialized with server: dev.db.sysco / DB: eLearn")
    try:
        sync_users_from_mssql()
    except Exception as err:
        logging.error(f"Execution test result: {err}")

