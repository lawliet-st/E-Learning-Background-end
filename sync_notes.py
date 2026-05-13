import csv
import json
import logging

logging.basicConfig(level=logging.INFO)

# 此腳本為未來與 IBM Notes 資料庫溝通的橋樑。
# 目前採用「讀取 IT 匯出的 CSV」的設計模式，待實際主機環境確認後可改為直接打 Notes API 或連接 Database View。

def sync_users_from_csv(file_path: str):
    """
    預期的 CSV 格式標頭：
    employee_id, national_id, name, email, department, title, status
    """
    logging.info(f"Starting to sync users from {file_path}")
    # TODO: Initialize SQLAlchemy session
    # from backend.database import SessionLocal
    # db = SessionLocal()
    
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                # 簡單驗證
                if row.get('status') != 'Active':
                    logging.info(f"Skipping inactive user: {row.get('employee_id')}")
                    continue
                
                # TODO: 
                # 1. 透過 row['employee_id'] 查詢 SQLite/SQL Server 中是否已有該員工
                # 2. 如果沒有，使用 auth.get_password_hash(row['national_id']) 建立新帳號並 INSERT
                # 3. 如果有，則 update name, department, title
                
                count += 1
            
            # db.commit()
            logging.info(f"Sync complete. Processed {count} active users.")
    except Exception as e:
        # db.rollback()
        logging.error(f"Failed to sync IBM Notes data: {str(e)}")
    finally:
        # db.close()
        pass

if __name__ == "__main__":
    # 測試執行入口
    # sync_users_from_csv("/path/to/it/daily_export.csv")
    logging.info("IBM Notes Sync Task module ready.")
