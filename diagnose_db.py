#!/usr/bin/env python3
"""
修復腳本：將 MSSQL courses/announcements/users 欄位從 varchar 改為 nvarchar 以支援中文
在 Linux 主機上執行：python3 backend/diagnose_db.py
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from backend.database import SessionLocal
import backend.models as models
from sqlalchemy import text

db = SessionLocal()

print("=== 1. 確認 courses 欄位現況 ===")
with db.bind.connect() as conn:
    result = conn.execute(text("""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'courses'
        ORDER BY ORDINAL_POSITION
    """))
    for row in result:
        print(f"  {row[0]:30s} {row[1]:15s} {row[2] if row[2] else ''}")

print("\n=== 2. ALTER TABLE 修改欄位 ===")

# 單獨逐一 commit 每個 ALTER
single_alters = [
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [title] nvarchar(200) NOT NULL",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [description] nvarchar(MAX)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [category] nvarchar(100)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [duration] nvarchar(50)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [visual_summary] nvarchar(MAX)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [thumbnail] nvarchar(500)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [video_url] nvarchar(500)",
    "ALTER TABLE [dbo].[courses] ALTER COLUMN [pdf_url] nvarchar(500)",
    "ALTER TABLE [dbo].[announcements] ALTER COLUMN [title] nvarchar(200) NOT NULL",
    "ALTER TABLE [dbo].[announcements] ALTER COLUMN [content] nvarchar(MAX) NOT NULL",
    "ALTER TABLE [dbo].[announcements] ALTER COLUMN [author] nvarchar(100) NOT NULL",
    "ALTER TABLE [dbo].[announcements] ALTER COLUMN [image_url] nvarchar(500)",
    "ALTER TABLE [dbo].[users] ALTER COLUMN [name] nvarchar(100) NOT NULL",
    "ALTER TABLE [dbo].[users] ALTER COLUMN [department] nvarchar(100)",
    "ALTER TABLE [dbo].[users] ALTER COLUMN [title] nvarchar(100)",
    # categories.name 有 index, 需先 drop index 再 alter
    "DROP INDEX IF EXISTS [ix_categories_name] ON [dbo].[categories]",
    "ALTER TABLE [dbo].[categories] ALTER COLUMN [name] nvarchar(100) NOT NULL",
    "CREATE UNIQUE INDEX [ix_categories_name] ON [dbo].[categories]([name])",
]

for stmt in single_alters:
    try:
        with db.bind.connect() as conn:
            conn.execute(text("SET XACT_ABORT ON"))
            conn.execute(text(stmt))
            conn.commit()
        print(f"  ✅ {stmt[:80]}")
    except Exception as e:
        err_msg = str(e)
        if "already" in err_msg.lower() or "nvarchar" in err_msg.lower():
            print(f"  ⏭  (已是正確類型) {stmt[:60]}")
        else:
            print(f"  ❌ {stmt[:60]}")
            print(f"     -> {err_msg[:120]}")

print("\n=== 3. 驗證中文寫入 ===")
try:
    course = db.query(models.Course).first()
    if course:
        orig = course.title
        course.title = "中文測試標題✓"
        db.commit()
        db.refresh(course)
        print(f"  寫入: 中文測試標題✓")
        print(f"  讀回: {course.title}")
        course.title = orig
        db.commit()
        print(f"  還原: {course.title}")
        print("  ✅ 中文寫入正常！")
    else:
        print("  沒有課程可測試")
except Exception as e:
    print(f"  ❌ 錯誤: {e}")
    db.rollback()

db.close()
print("\n=== 完成 ===")
