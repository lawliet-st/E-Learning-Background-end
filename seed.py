import json
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, engine, Base
from backend import models, auth

def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Check if we already seeded
    if db.query(models.User).first():
        print("Database already seeded.")
        return

    # Create Admin
    admin = models.User(
        id="u1",
        employee_id="admin001",
        hashed_password=auth.get_password_hash("A123456789"), # Mock National ID
        name="系統管理員",
        email="admin@company.com",
        internal_email="admin.internal@shengyu.com",
        role="admin",
        department="人資部",
        title="人資經理",
        avatar="https://picsum.photos/seed/admin/100/100",
        profile={
            "age": 35,
            "joinDate": "2018-05-20",
            "performanceHistory": [],
            "skills": [],
            "nineBoxPosition": {"performance": "High", "potential": "High"},
            "assessment": {"hpi": 0, "hds": 0, "mvpi": 0, "completed": False},
            "tags": ["細心", "領導力"],
            "skillAssessmentScore": 0
        }
    )

    # Create Alice (employee)
    alice = models.User(
        id="u2",
        employee_id="E10001",
        hashed_password=auth.get_password_hash("A223456789"),
        name="陳雅婷 (Alice)",
        email="alice@company.com",
        internal_email="alice.chen@shengyu.com",
        role="employee",
        department="業務部",
        title="資深業務代表",
        avatar="https://picsum.photos/seed/alice/100/100",
        profile={
            "age": 29,
            "joinDate": "2023-05-01",
            "performanceHistory": [
                {"year": "2021", "rating": 4.2},
                {"year": "2022", "rating": 4.5},
                {"year": "2023", "rating": 4.8},
            ],
            "skills": [
                {"subject": "業務談判", "A": 90, "fullMark": 100},
                {"subject": "數據分析", "A": 65, "fullMark": 100},
                {"subject": "溝通協調", "A": 95, "fullMark": 100},
            ],
            "nineBoxPosition": {"performance": "High", "potential": "High"},
            "assessment": {
                "hpi": 88, "hds": 45, "mvpi": 92, "completed": True,
            },
            "tags": ["外向", "開朗", "目標導向", "社交高手"],
            "skillAssessmentScore": 42
        }
    )

    # Add Courses
    course1 = models.Course(
        id="c1",
        title="職場安全基礎",
        category="職安衛",
        type="compulsory",
        description="了解工作環境中的潛在危害與緊急應變措施，確保自身與他人安全。",
        thumbnail="https://picsum.photos/seed/safety/400/225",
        video_url="https://www.youtube.com/embed/AdXq760YyWA",
        pdf_url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        duration="45 分鐘",
        duration_seconds=2700,
        attributes={"logic": 40, "professional": 80, "difficulty": 30, "importance": 100, "knowledgeLimit": 20},
        questions=[
            {"id": "q1", "text": "發現火災的第一步是什麼？", "options": ["逃跑", "拉響警報", "躲起來"], "correctAnswer": 1},
            {"id": "q2", "text": "緊急出口應該設在哪裡？", "options": ["隱蔽處", "標示清楚處", "上鎖處"], "correctAnswer": 1},
        ]
    )

    course2 = models.Course(
        id="c2",
        title="高效溝通技巧",
        category="軟實力",
        type="elective",
        description="學習如何與團隊成員及客戶進行清晰、有說服力的溝通。",
        thumbnail="https://picsum.photos/seed/comm/400/225",
        video_url="https://www.youtube.com/embed/srn5jgp5QDc",
        pdf_url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        duration="1小時 20分",
        duration_seconds=4800,
        attributes={"logic": 60, "professional": 50, "difficulty": 40, "importance": 90, "knowledgeLimit": 30},
        questions=[
            {"id": "q1", "text": "什麼是積極聆聽？", "options": ["大聲說話", "全神貫注聽講者", "忽略對方"], "correctAnswer": 1},
        ]
    )


    db.add(admin)
    db.add(alice)
    db.add(course1)
    db.add(course2)
    
    # Progress
    db.add(models.LearningRecord(
        user_id="u2",
        course_id="c1",
        completed=True,
        quiz_score=90,
        satisfaction=5,
        attempt_date="2023-10-01"
    ))

    db.commit()
    db.close()
    print("Database seeded successfully with Alice (E10001) and Admin (admin001).")

if __name__ == "__main__":
    seed_data()
