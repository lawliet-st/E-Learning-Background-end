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
from backend.models import User, UserProfile, UserPerformanceHistory
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
    
    mssql_engine = create_engine(conn_str)
    db: Session = SessionLocal()
    
    try:
        with mssql_engine.connect() as conn:
            # 優先嘗試 [HRM].[dbo].[eLEARNING] (HR 正式 View)，次之 [dbo].[elearning]，最後 [dbo].[z_backup_elearning_598]
            query_success = False
            for tbl in ["[HRM].[dbo].[eLEARNING]", "[dbo].[elearning]", "[dbo].[z_backup_elearning_598]"]:
                try:
                    result = conn.execute(text(f"SELECT * FROM {tbl}"))
                    logging.info(f"Successfully connected and querying from {tbl}")
                    query_success = True
                    break
                except Exception as table_err:
                    logging.warning(f"Querying {tbl} not available: {table_err}")
            
            if not query_success:
                raise RuntimeError("No employee source table found in MSSQL")

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
                existing_user = db.query(User).filter(User.EMPID == emp_id).first()
                perf_history = parse_performance_history(row_dict)
                
                target_user = existing_user
                if not target_user:
                    if not is_active:
                        continue # 離職人員不新增
                        
                    target_user = User(
                        EMPID=emp_id,
                        HECNAME=name or f"員工{emp_id}",
                        IDNO=national_id or emp_id,
                        EMAIL=email or f"{emp_id}@shengyusteel.com",
                        DEPT_NO=dept or "未分配部門",
                        TITLE=title or "同仁",
                        STATE="在職",
                        role="employee",
                        datein=join_date,
                        CPNYID=cpny_id or "SYSCO"
                    )
                    db.add(target_user)
                    db.flush()
                else:
                    if name: target_user.HECNAME = name
                    if email: target_user.EMAIL = email
                    if dept: target_user.DEPT_NO = dept
                    if title: target_user.TITLE = title
                    if national_id: target_user.IDNO = national_id
                    if not is_active:
                        target_user.STATE = "離職"
                        target_user.role = "inactive"
                    else:
                        target_user.STATE = "在職"

                # Update UserProfile sub-table
                u_prof = db.query(UserProfile).filter(UserProfile.user_id == target_user.EMPID).first()
                if not u_prof:
                    u_prof = UserProfile(user_id=target_user.EMPID, age=30, nine_box_perf="Medium", nine_box_pot="Medium")
                    db.add(u_prof)
                if join_date:
                    u_prof.join_date = join_date

                # Update UserPerformanceHistory sub-table
                if perf_history:
                    db.query(UserPerformanceHistory).filter(UserPerformanceHistory.user_id == target_user.EMPID).delete()
                    for ph in perf_history:
                        db.add(UserPerformanceHistory(
                            user_id=target_user.EMPID,
                            year=str(ph.get("year", "")),
                            rating=float(ph.get("rating", 0))
                        ))

                synced_count += 1
            
            db.commit()
            logging.info(f"Successfully synced {synced_count} employee records from MS SQL to relational sub-tables.")
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

