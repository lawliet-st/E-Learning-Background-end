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

    # Seed Default Categories
    default_categories = ["職安衛", "軟實力", "IT技能", "管理", "行銷", "品質管理", "生產製造"]
    for cat_name in default_categories:
        cat = models.Category(name=cat_name, created_at="2024-01-01")
        db.add(cat)

    # Seed Announcements
    announcement1 = models.Announcement(
        title="【盛餘領航者】歡迎使用盛餘數位學習平台",
        content="全方位內部培訓平台正式上線，提供各領域專業內訓課程、影音學習與線上測驗，歡迎同仁踴躍進修！",
        type="system",
        created_at="2024-01-01 09:00",
        is_pinned=True,
        author="系統管理員"
    )
    announcement2 = models.Announcement(
        title="📢 【新課上架】職安衛領域《職場安全基礎》已正式開課！",
        content="職場安全基礎包含工作危害防範與緊急應變，請全體同仁於指定時限內完成修習並通過測驗。",
        type="course_auto",
        course_id="c1",
        created_at="2024-01-02 10:00",
        is_pinned=False,
        author="人資部"
    )
    db.add(announcement1)
    db.add(announcement2)

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
            "tags": [],
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
            "tags": [],
            "skillAssessmentScore": 42
        }
    )

    # Add Courses with at least 10 questions each
    course1_questions = [
        {"id": "q1", "text": "發現火災的第一步是什麼？", "options": ["立即逃跑不管他人", "拉響警報並通報", "躲進辦公桌底下", "繼續工作"], "correctAnswer": 1},
        {"id": "q2", "text": "緊急逃生出口應該保持何種狀態？", "options": ["堆放雜物以防外人進入", "標示清楚且暢通無阻", "隨時上鎖保護財產", "拉下鐵捲門"], "correctAnswer": 1},
        {"id": "q3", "text": "進入工廠生產作業區時，同仁應配戴何種基本個人防護裝備？", "options": ["標準安全帽與防護鞋", "一般休閒帽", "耳機聽音樂", "無需佩戴"], "correctAnswer": 0},
        {"id": "q4", "text": "若在廠區發現化學品洩漏，首要處置方式為何？", "options": ["立即徒手清理", "遠離現場並通知工安單位處理", "用水直接沖洗", "裝作沒看見"], "correctAnswer": 1},
        {"id": "q5", "text": "滅火器使用口訣『拉、瞄、壓、掃』中，『拉』是指拉開什麼？", "options": ["拉開安全插銷", "拉開水管", "拉開門窗", "拉開警報器"], "correctAnswer": 0},
        {"id": "q6", "text": "高處作業（超過 2 公尺）必須確實使用下列何項防護設施？", "options": ["安全帶與防墜設施", "普通梯子即可", "厚底鞋", "手套"], "correctAnswer": 0},
        {"id": "q7", "text": "發生職業災害時，當班人員應於多少時限內通報主管與工安課？", "options": ["下個月底前", "立即第一時間通報", "3天內", "無需通報"], "correctAnswer": 1},
        {"id": "q8", "text": "對於用電安全，以下何者為錯誤行為？", "options": ["插座過載使用多孔插頭", "定期檢查電線絕緣", "手部潮濕不碰開關", "損壞電線立即更換"], "correctAnswer": 0},
        {"id": "q9", "text": "職業安全衛生政策的核心精神是？", "options": ["零災害與全員參與", "產量優先於安全", "只要應付法規檢查", "僅由工安人員負責"], "correctAnswer": 0},
        {"id": "q10", "text": "遇到地震時，室內人員的避難三步驟為？", "options": ["趴下、掩護、穩住", "快跑、大叫、跳樓", "搭乘電梯逃生", "站立於窗戶邊"], "correctAnswer": 0},
    ]

    course1 = models.Course(
        id="c1",
        title="職場安全基礎",
        category="職安衛",
        type="compulsory",
        status="published",
        pass_score=70,
        is_random_10=True,
        is_random_order=False,
        created_at="2024-01-02",
        description="了解工作環境中的潛在危害與緊急應變措施，確保自身與他人安全。",
        thumbnail="https://picsum.photos/seed/safety/400/225",
        video_url="https://www.youtube.com/embed/AdXq760YyWA",
        pdf_url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        duration="45 分鐘",
        duration_seconds=2700,
        attributes={"logic": 40, "professional": 80, "difficulty": 30, "importance": 100, "knowledgeLimit": 20},
        questions=course1_questions
    )

    course2_questions = [
        {"id": "q1", "text": "什麼是高效溝通中的『積極聆聽』？", "options": ["隨時準備打斷對方陳述自己的意見", "全神貫注理解說話者的立場與本意", "邊聽邊滑手機處理其他事務", "大聲覆誦對方的每句話"], "correctAnswer": 1},
        {"id": "q2", "text": "非語言溝通（肢體語言、眼神與語調）在溝通成效中扮演何種角色？", "options": ["完全沒有影響", "佔據傳達訊息的極高比例與情緒感受", "只在演講時有用", "比文字更不重要"], "correctAnswer": 1},
        {"id": "q3", "text": "跨部門溝通協商時，最能達成雙贏的最佳策略是？", "options": ["以同理心出發，透過客觀數據共同探討解決方案", "堅持己見並施壓對方配合", "拒絕對話", "一律交由最高主管裁決"], "correctAnswer": 0},
        {"id": "q4", "text": "給予同事建設性回饋 (Feedback) 的原則應為？", "options": ["對事不對人，具體且提出可行建議", "公開場合進行人身攻擊", "模糊不清以避免衝突", "只批評不給建議"], "correctAnswer": 0},
        {"id": "q5", "text": "在撰寫商務電子郵件時，主旨 (Subject) 應該如何呈現？", "options": ["簡潔明確表達郵件核心目的", "留白或只寫『您好』", "寫滿 100 字細節", "只填寫急件二字"], "correctAnswer": 0},
        {"id": "q6", "text": "當與客戶或主管發生意見分歧時，第一步應該？", "options": ["確認彼此對於目標與事實認知是否一致", "立即反駁對方的論點", "私下抱怨", "直接放棄爭取"], "correctAnswer": 0},
        {"id": "q7", "text": "會議溝通中，『會議結論與待辦事項 (Action Items)』的重要性在於？", "options": ["明確分工、責任歸屬與完成期限", "單純填寫會議紀錄交差", "沒有實際用途", "僅供主管審閱"], "correctAnswer": 0},
        {"id": "q8", "text": "溝通漏斗理論指出，『心裡想講的』到『對方實際執行的』往往會遞減，改善之道為？", "options": ["雙向確認 (Check-in) 與定時對焦", "講一次就不再過問", "用更複雜的術語說明", "只用口頭交代不用文字"], "correctAnswer": 0},
        {"id": "q9", "text": "在團隊中表達不同觀點時，如何營造『心理安全感』？", "options": ["接納多元觀點，鼓勵發問與理性討論", "嚴懲提出反對意見的人", "禁止任何質疑", "只聽資深同仁的意見"], "correctAnswer": 0},
        {"id": "q10", "text": "向上溝通（對主管匯報）時，最佳的報告結構為？", "options": ["結論先行 (Bottom Line First)，再陳述支持理由與具體行動", "從背景故事漫談，最後才講結論", "只報喜不報憂", "隱瞞問題直到無法收拾"], "correctAnswer": 0},
    ]

    course2 = models.Course(
        id="c2",
        title="高效溝通技巧",
        category="軟實力",
        type="elective",
        status="published",
        pass_score=70,
        is_random_10=True,
        is_random_order=False,
        created_at="2024-01-05",
        description="學習如何與團隊成員及客戶進行清晰、有說服力的溝通。",
        thumbnail="https://picsum.photos/seed/comm/400/225",
        video_url="https://www.youtube.com/embed/srn5jgp5QDc",
        pdf_url="https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
        duration="1小時 20分",
        duration_seconds=4800,
        attributes={"logic": 60, "professional": 50, "difficulty": 40, "importance": 90, "knowledgeLimit": 30},
        questions=course2_questions
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
        attempt_date="2024-01-10 14:30:00",
        fail_count=0
    ))

    db.commit()
    db.close()
    print("Database seeded successfully with Alice (E10001) and Admin (admin001).")

if __name__ == "__main__":
    seed_data()
