from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Body, Request
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

from fastapi.staticfiles import StaticFiles
import os
import base64
import json
import urllib.request

# Bypass potential broken system proxies
proxy_support = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy_support)
urllib.request.install_opener(opener)

from .database import Base, engine, get_db, SessionLocal
from . import models, schemas, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 僅建立資料表結構（若尚未存在），資料全部來自 dev.db.sysco
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="E-learning Backend", version="1.0.0", lifespan=lifespan)

# Allow Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse, StreamingResponse

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/uploads/{subpath:path}")
def serve_upload(subpath: str, request: Request):
    file_path = os.path.normpath(os.path.join(UPLOAD_DIR, subpath))
    if not file_path.startswith(UPLOAD_DIR) or not os.path.exists(file_path) or os.path.isdir(file_path):
        raise HTTPException(status_code=404, detail="檔案不存在")
        
    mime_type = "video/mp4" if subpath.endswith(".mp4") else "video/webm" if subpath.endswith(".webm") else None
    range_header = request.headers.get("range")
    
    if mime_type and range_header:
        file_size = os.path.getsize(file_path)
        start, end = 0, file_size - 1
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        if parts[0]:
            start = int(parts[0])
        if len(parts) > 1 and parts[1]:
            end = int(parts[1])
            
        end = min(end, file_size - 1)
        chunk_size = end - start + 1
        
        def file_generator():
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = chunk_size
                while bytes_left > 0:
                    chunk = f.read(min(bytes_left, 1024 * 64))
                    if not chunk:
                        break
                    bytes_left -= len(chunk)
                    yield chunk
                    
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
        }
        return StreamingResponse(file_generator(), status_code=206, media_type=mime_type, headers=headers)
        
    return FileResponse(file_path)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def get_gemini_api_key():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        return api_key
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for env_file in ['.env.local', '.env']:
        env_path = os.path.join(base_dir, env_file)
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        return line.split('=', 1)[1].strip()
    return ""


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/login", response_model=schemas.Token)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.employee_id == req.employee_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="無效的員工編號或密碼")
    
    if not auth.verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="無效的員工編號或密碼")

    access_token = auth.create_access_token(data={"sub": user.employee_id, "role": user.role})
    
    # Dump user safely to dict
    user_dict = {
        "id": user.id,
        "name": user.name,
        "employee_id": user.employee_id,
        "email": user.email,
        "role": user.role,
        "avatar": user.avatar,
        "department": user.department,
        "title": user.title,
        "profile": user.profile
    }
    
    return {"access_token": access_token, "token_type": "bearer", "user": user_dict}


from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="無效的認證")
    employee_id = payload.get("sub")
    if employee_id is None:
        raise HTTPException(status_code=401, detail="無效的認證")
    user = db.query(models.User).filter(models.User.employee_id == employee_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="使用者不存在")
    return user


@app.get("/api/users")
def get_users(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    users = db.query(models.User).all()
    res = []
    for u in users:
        prof_obj = u.user_profile
        skills_obj = u.user_skills
        perf_obj = u.performance_history
        
        prof_dict = {
            "age": prof_obj.age if prof_obj and prof_obj.age is not None else 30,
            "joinDate": prof_obj.join_date if prof_obj and prof_obj.join_date else "2023-01-01",
            "nineBoxPosition": {
                "performance": prof_obj.nine_box_perf if prof_obj and prof_obj.nine_box_perf else "High",
                "potential": prof_obj.nine_box_pot if prof_obj and prof_obj.nine_box_pot else "High"
            },
            "assessment": {
                "hpi": prof_obj.hpi_score if prof_obj and prof_obj.hpi_score is not None else 0,
                "hds": prof_obj.hds_score if prof_obj and prof_obj.hds_score is not None else 0,
                "mvpi": prof_obj.mvpi_score if prof_obj and prof_obj.mvpi_score is not None else 0,
                "completed": prof_obj.assessment_completed if prof_obj else False
            },
            "skillAssessmentScore": prof_obj.skill_assessment_score if prof_obj and prof_obj.skill_assessment_score is not None else 0,
            "skills": [{"subject": s.subject, "A": s.score, "fullMark": s.full_mark} for s in skills_obj],
            "performanceHistory": [{"year": p.year, "rating": p.rating} for p in perf_obj]
        }
        
        res.append({
            "id": u.id,
            "employeeId": u.employee_id,
            "employee_id": u.employee_id,
            "name": u.name,
            "email": u.email or u.internal_email or "",
            "internalEmail": u.internal_email,
            "department": u.department or "",
            "title": u.title or "",
            "role": u.role,
            "profile": prof_dict,
            "avatar": u.avatar or ""
        })
    return res

def format_course_dict(c: models.Course) -> dict:
    attrs = c.course_attribute
    attrs_dict = {
        "logic": attrs.logic if attrs else 50,
        "professional": attrs.professional if attrs else 50,
        "difficulty": attrs.difficulty if attrs else 50,
        "importance": attrs.importance if attrs else 50,
        "knowledgeLimit": attrs.knowledge_limit if attrs else 50
    }
    
    questions_list = []
    for q in c.course_questions:
        opts = [o.option_text for o in q.options]
        questions_list.append({
            "id": q.question_id,
            "text": q.text,
            "options": opts,
            "correctAnswer": q.correct_answer
        })

    depts = [t.target_value for t in c.compulsory_targets_rel if t.target_type == "department"]
    uids = [t.target_value for t in c.compulsory_targets_rel if t.target_type == "user"]
    comp_targets_dict = {
        "departments": depts,
        "userIds": uids
    }

    pub_hist_list = []
    for p in c.publish_history_rel:
        pub_hist_list.append({
            "action": p.action,
            "timestamp": p.timestamp,
            "operator": p.operator
        })

    return {
        "id": c.id,
        "title": c.title or "",
        "description": c.description or "",
        "category": c.category or "",
        "type": c.type or "elective",
        "status": c.status or "published",
        "passScore": c.pass_score if c.pass_score is not None else 70,
        "pass_score": c.pass_score if c.pass_score is not None else 70,
        "isRandom10": c.is_random_10 if c.is_random_10 is not None else True,
        "is_random_10": c.is_random_10 if c.is_random_10 is not None else True,
        "isRandomOrder": c.is_random_order if c.is_random_order is not None else False,
        "is_random_order": c.is_random_order if c.is_random_order is not None else False,
        "isRandomOptions": c.is_random_options if c.is_random_options is not None else True,
        "is_random_options": c.is_random_options if c.is_random_options is not None else True,
        "createdAt": c.created_at or "",
        "created_at": c.created_at or "",
        "thumbnail": c.thumbnail or "",
        "videoUrl": c.video_url or "",
        "video_url": c.video_url or "",
        "pdfUrl": c.pdf_url or "",
        "pdf_url": c.pdf_url or "",
        "duration": c.duration or "",
        "durationSeconds": c.duration_seconds if c.duration_seconds is not None else 3600,
        "duration_seconds": c.duration_seconds if c.duration_seconds is not None else 3600,
        "visualSummary": c.visual_summary or "",
        "visual_summary": c.visual_summary or "",
        "attributes": attrs_dict,
        "questions": questions_list,
        "compulsoryTargets": comp_targets_dict,
        "compulsory_targets": comp_targets_dict,
        "publishHistory": pub_hist_list,
        "publish_history": pub_hist_list
    }

def save_course_relational_data(db: Session, course_id: str, course_data: dict, current_user_name: str, new_status: str, old_status: str = None):
    attrs = course_data.get("attributes")
    if attrs and isinstance(attrs, dict):
        c_attr = db.query(models.CourseAttribute).filter(models.CourseAttribute.course_id == course_id).first()
        if not c_attr:
            c_attr = models.CourseAttribute(course_id=course_id)
            db.add(c_attr)
        c_attr.logic = attrs.get("logic", 50)
        c_attr.professional = attrs.get("professional", 50)
        c_attr.difficulty = attrs.get("difficulty", 50)
        c_attr.importance = attrs.get("importance", 50)
        c_attr.knowledge_limit = attrs.get("knowledgeLimit", 50)

    questions = course_data.get("questions")
    if questions is not None and isinstance(questions, list):
        db.query(models.CourseQuestion).filter(models.CourseQuestion.course_id == course_id).delete()
        for q in questions:
            q_obj = models.CourseQuestion(
                course_id=course_id,
                question_id=q.get("id", "q1"),
                text=q.get("text", ""),
                correct_answer=q.get("correctAnswer", 0)
            )
            db.add(q_obj)
            db.flush()
            
            opts = q.get("options", [])
            for idx, opt_text in enumerate(opts):
                opt_obj = models.CourseQuestionOption(
                    question_db_id=q_obj.id,
                    option_order=idx,
                    option_text=opt_text
                )
                db.add(opt_obj)

    comp_targets = course_data.get("compulsoryTargets") if course_data.get("compulsoryTargets") is not None else course_data.get("compulsory_targets")
    if comp_targets is not None and isinstance(comp_targets, dict):
        db.query(models.CourseCompulsoryTarget).filter(models.CourseCompulsoryTarget.course_id == course_id).delete()
        depts = comp_targets.get("departments", [])
        uids = comp_targets.get("userIds", [])
        for d in depts:
            db.add(models.CourseCompulsoryTarget(course_id=course_id, target_type="department", target_value=d))
        for u in uids:
            db.add(models.CourseCompulsoryTarget(course_id=course_id, target_type="user", target_value=u))

    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if old_status is not None and old_status != new_status:
        db.add(models.CoursePublishHistory(
            course_id=course_id,
            action=new_status,
            timestamp=now_str,
            operator=current_user_name
        ))

@app.get("/api/courses")
def get_courses(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    courses = db.query(models.Course).all()
    return [format_course_dict(c) for c in courses]

@app.post("/api/courses")
def create_course(course_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")

    from datetime import datetime
    import time
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    c_id = course_data.get("id") or f"c_{int(time.time() * 1000)}"
    status_val = course_data.get("status", "published")

    v_url = course_data.get("videoUrl") if course_data.get("videoUrl") is not None else course_data.get("video_url", "")
    p_url = course_data.get("pdfUrl") if course_data.get("pdfUrl") is not None else course_data.get("pdf_url", "")

    course = models.Course(
        id=c_id,
        title=course_data.get("title", "未命名課程"),
        description=course_data.get("description", ""),
        category=course_data.get("category", "通用"),
        type=course_data.get("type", "elective"),
        status=status_val,
        pass_score=course_data.get("passScore") if course_data.get("passScore") is not None else course_data.get("pass_score", 70),
        is_random_10=course_data.get("isRandom10") if course_data.get("isRandom10") is not None else course_data.get("is_random_10", True),
        is_random_order=course_data.get("isRandomOrder") if course_data.get("isRandomOrder") is not None else course_data.get("is_random_order", False),
        is_random_options=course_data.get("isRandomOptions") if course_data.get("isRandomOptions") is not None else course_data.get("is_random_options", True),
        created_at=now_str[:10],
        thumbnail=course_data.get("thumbnail", ""),
        video_url=v_url or "",
        pdf_url=p_url or "",
        duration=course_data.get("duration", "60 分鐘"),
        duration_seconds=course_data.get("durationSeconds") if course_data.get("durationSeconds") is not None else course_data.get("duration_seconds", 3600),
        visual_summary=course_data.get("visualSummary") or course_data.get("visual_summary", "")
    )
    db.add(course)
    db.flush()

    save_course_relational_data(db, c_id, course_data, current_user.name, status_val)

    if status_val == "published":
        ann = models.Announcement(
            title=f"📢 【新課上架】{course.category}領域《{course.title}》已正式開課！",
            content=f"由內部講師精心規劃之《{course.title}》現已開放修習！歡迎同仁踴躍點閱學習並參與測驗評量。",
            type="course_auto",
            course_id=course.id,
            created_at=now_str[:16],
            is_pinned=False,
            author="人資部"
        )
        db.add(ann)

    db.commit()
    db.refresh(course)
    return format_course_dict(course)

@app.put("/api/courses/{course_id}")
def update_course(course_id: str, course_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="找不到課程")
        
    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    old_status = course.status
    new_status = course_data.get("status", course.status or "published")

    course.title = course_data.get("title", course.title)
    course.description = course_data.get("description", course.description)
    course.category = course_data.get("category", course.category)
    course.type = course_data.get("type", course.type)
    course.status = new_status
    
    if "passScore" in course_data:
        course.pass_score = course_data["passScore"]
    elif "pass_score" in course_data:
        course.pass_score = course_data["pass_score"]

    if "isRandom10" in course_data:
        course.is_random_10 = course_data["isRandom10"]
    elif "is_random_10" in course_data:
        course.is_random_10 = course_data["is_random_10"]

    if "isRandomOrder" in course_data:
        course.is_random_order = course_data["isRandomOrder"]
    elif "is_random_order" in course_data:
        course.is_random_order = course_data["is_random_order"]

    if "isRandomOptions" in course_data:
        course.is_random_options = course_data["isRandomOptions"]
    elif "is_random_options" in course_data:
        course.is_random_options = course_data["is_random_options"]

    course.thumbnail = course_data.get("thumbnail", course.thumbnail)

    if "videoUrl" in course_data:
        course.video_url = course_data["videoUrl"]
    elif "video_url" in course_data:
        course.video_url = course_data["video_url"]

    if "pdfUrl" in course_data:
        course.pdf_url = course_data["pdfUrl"]
    elif "pdf_url" in course_data:
        course.pdf_url = course_data["pdf_url"]

    course.duration = course_data.get("duration", course.duration)
    
    if "durationSeconds" in course_data:
        course.duration_seconds = course_data["durationSeconds"]
    elif "duration_seconds" in course_data:
        course.duration_seconds = course_data["duration_seconds"]

    if "visualSummary" in course_data:
        course.visual_summary = course_data["visualSummary"]
    elif "visual_summary" in course_data:
        course.visual_summary = course_data["visual_summary"]

    save_course_relational_data(db, course_id, course_data, current_user.name, new_status, old_status)
    
    # Auto announcement if changed from draft/closed to published
    if old_status != "published" and new_status == "published":
        ann = models.Announcement(
            title=f"📢 【新課上架】{course.category}領域《{course.title}》已正式開課！",
            content=f"由內部講師精心規劃之《{course.title}》現已開放修習！歡迎同仁踴躍點閱學習並參與測驗評量。",
            type="course_auto",
            course_id=course.id,
            created_at=now_str[:16],
            is_pinned=False,
            author="人資部"
        )
        db.add(ann)

    db.commit()
    db.refresh(course)
    return format_course_dict(course)

@app.post("/api/courses/{course_id}/duplicate")
def duplicate_course(course_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="找不到課程")
        
    from datetime import datetime
    import time
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_id = f"c_{int(time.time() * 1000)}"

    dup_course = models.Course(
        id=new_id,
        title=f"{course.title} (副本)",
        description=course.description,
        category=course.category,
        type=course.type,
        status="draft", # default to draft for copies
        pass_score=course.pass_score,
        is_random_10=course.is_random_10,
        is_random_order=course.is_random_order,
        is_random_options=course.is_random_options,
        created_at=now_str.split(' ')[0],
        thumbnail=course.thumbnail,
        video_url=course.video_url,
        pdf_url=course.pdf_url,
        duration=course.duration,
        duration_seconds=course.duration_seconds,
        visual_summary=course.visual_summary,
        attributes=course.attributes,
        questions=course.questions,
        compulsory_targets=course.compulsory_targets,
        publish_history=[{
            "status": "draft",
            "timestamp": now_str,
            "operator": current_user.name
        }]
    )
    db.add(dup_course)
    db.commit()
    db.refresh(dup_course)
    return format_course_dict(dup_course)

@app.delete("/api/courses/{course_id}")
def delete_course(course_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="找不到課程")
        
    db.delete(course)
    db.commit()
    return {"status": "ok"}

# --- Categories API ---
@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cats = db.query(models.Category).order_by(models.Category.id.asc()).all()
    if not cats:
        # Auto seed default categories if none
        defaults = ["職安衛", "軟實力", "IT技能", "管理", "行銷", "品質管理", "生產製造"]
        for d in defaults:
            c = models.Category(name=d, created_at="2024-01-01")
            db.add(c)
        db.commit()
        cats = db.query(models.Category).order_by(models.Category.id.asc()).all()
    return [{"id": c.id, "name": c.name, "createdAt": c.created_at} for c in cats]

@app.post("/api/categories")
def create_category(cat_data: schemas.CategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    existing = db.query(models.Category).filter(models.Category.name == cat_data.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="分類名稱已存在")
    from datetime import datetime
    new_cat = models.Category(name=cat_data.name.strip(), created_at=datetime.now().strftime('%Y-%m-%d'))
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return {"id": new_cat.id, "name": new_cat.name, "createdAt": new_cat.created_at}

@app.put("/api/categories/{category_id}")
def update_category(category_id: int, cat_data: schemas.CategoryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="找不到分類")
    old_name = cat.name
    cat.name = cat_data.name.strip()
    # Also update courses with old category name to new category name
    courses = db.query(models.Course).filter(models.Course.category == old_name).all()
    for c in courses:
        c.category = cat.name
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "createdAt": cat.created_at}

@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    cat = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="找不到分類")
    db.delete(cat)
    db.commit()
    return {"status": "ok"}

# --- Announcements API ---
@app.get("/api/announcements")
def get_announcements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    anns = db.query(models.Announcement).order_by(models.Announcement.is_pinned.desc(), models.Announcement.id.desc()).all()
    return [{
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "type": a.type,
        "imageUrl": a.image_url,
        "courseId": a.course_id,
        "createdAt": a.created_at,
        "isPinned": a.is_pinned,
        "author": a.author
    } for a in anns]

@app.post("/api/announcements")
def create_announcement(data: schemas.AnnouncementCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    from datetime import datetime
    img_url = data.image_url if data.image_url is not None else data.imageUrl
    c_id = data.course_id if data.course_id is not None else data.courseId
    pinned = data.is_pinned if data.is_pinned is not None else data.isPinned

    ann = models.Announcement(
        title=data.title,
        content=data.content,
        type=data.type or "notice",
        image_url=img_url,
        course_id=c_id,
        created_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        is_pinned=bool(pinned),
        author=current_user.name
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {
        "id": ann.id,
        "title": ann.title,
        "content": ann.content,
        "type": ann.type,
        "imageUrl": ann.image_url,
        "courseId": ann.course_id,
        "createdAt": ann.created_at,
        "isPinned": ann.is_pinned,
        "author": ann.author
    }

@app.put("/api/announcements/{ann_id}")
def update_announcement(ann_id: int, data: schemas.AnnouncementUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    ann = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="找不到公告")
    if data.title is not None:
        ann.title = data.title
    if data.content is not None:
        ann.content = data.content
    if data.type is not None:
        ann.type = data.type
    
    img_url = data.image_url if data.image_url is not None else data.imageUrl
    if img_url is not None:
        ann.image_url = img_url
        
    c_id = data.course_id if data.course_id is not None else data.courseId
    if c_id is not None:
        ann.course_id = c_id
        
    pinned = data.is_pinned if data.is_pinned is not None else data.isPinned
    if pinned is not None:
        ann.is_pinned = bool(pinned)
        
    db.commit()
    db.refresh(ann)
    return {
        "id": ann.id,
        "title": ann.title,
        "content": ann.content,
        "type": ann.type,
        "imageUrl": ann.image_url,
        "courseId": ann.course_id,
        "createdAt": ann.created_at,
        "isPinned": ann.is_pinned,
        "author": ann.author
    }

@app.delete("/api/announcements/{ann_id}")
def delete_announcement(ann_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    ann = db.query(models.Announcement).filter(models.Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="找不到公告")
    db.delete(ann)
    db.commit()
    return {"status": "ok"}


@app.post("/api/users")
def create_user(user_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    emp_id = user_data.get("employee_id") or user_data.get("employeeId")
    if not emp_id:
        raise HTTPException(status_code=400, detail="缺少員工編號")
        
    existing = db.query(models.User).filter(models.User.employee_id == emp_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="員工編號已存在")
        
    user = models.User(
        id=user_data.get("id"),
        employee_id=emp_id,
        name=user_data.get("name", ""),
        email=user_data.get("email", ""),
        internal_email=user_data.get("internalEmail", user_data.get("internal_email")),
        role=user_data.get("role", "employee"),
        department=user_data.get("department", ""),
        title=user_data.get("title", ""),
        avatar=user_data.get("avatar", "https://picsum.photos/seed/newuser/100/100"),
        hashed_password=auth.get_password_hash(emp_id),
        profile=user_data.get("profile")
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id, "name": user.name, "employee_id": user.employee_id,
        "department": user.department, "title": user.title, "role": user.role,
        "profile": user.profile, "avatar": user.avatar, "internalEmail": user.internal_email,
        "email": user.email
    }

@app.put("/api/users/{user_id}")
def update_user(user_id: str, user_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="權限不足")
        
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到使用者")
        
    if current_user.role == "admin":
        user.role = user_data.get("role", user.role)
        emp_id = user_data.get("employee_id") or user_data.get("employeeId")
        if emp_id:
            user.employee_id = emp_id
            
    user.name = user_data.get("name", user.name)
    user.email = user_data.get("email", user.email)
    user.internal_email = user_data.get("internalEmail", user_data.get("internal_email", user.internal_email))
    user.department = user_data.get("department", user.department)
    user.title = user_data.get("title", user.title)
    user.avatar = user_data.get("avatar", user.avatar)
    
    if "profile" in user_data:
        user.profile = user_data["profile"]
        
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id, "name": user.name, "employee_id": user.employee_id,
        "department": user.department, "title": user.title, "role": user.role,
        "profile": user.profile, "avatar": user.avatar, "internalEmail": user.internal_email,
        "email": user.email
    }

@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到使用者")
        
    db.delete(user)
    db.commit()
    return {"status": "ok"}

@app.post("/api/users/sync")
def sync_users(users_list: List[dict] = Body(...), db: Session = Depends(get_db), request: Request = None):
    expected_token = "NotesSyncSecureToken2026"
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else request.headers.get("x-sync-token", "")
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="驗證失敗，無效的同步 Token")
        
    synced_count = 0
    for u_item in users_list:
        emp_id = u_item.get("employee_id")
        if not emp_id:
            continue
            
        name = u_item.get("name", "")
        dept = u_item.get("department", "")
        title = u_item.get("title", "")
        email = u_item.get("email", "")
        int_email = u_item.get("internal_email", "")
        status_val = u_item.get("status", "active")
        
        user = db.query(models.User).filter(models.User.employee_id == emp_id).first()
        if user:
            if status_val in ["inactive", "terminated"]:
                db.delete(user)
            else:
                user.name = name
                user.department = dept
                user.title = title
                user.email = email
                user.internal_email = int_email
                if user.profile is None:
                    user.profile = {
                        "age": 30, "joinDate": "2026-01-01", "performanceHistory": [], "skills": [],
                        "nineBoxPosition": {"performance": "Medium", "potential": "Medium"},
                        "assessment": {"hpi": 0, "hds": 0, "mvpi": 0, "completed": False}, "tags": [], "skillAssessmentScore": 0
                    }
                synced_count += 1
        else:
            if status_val not in ["inactive", "terminated"]:
                user_id = f"u_sync_{emp_id}"
                user = models.User(
                    id=user_id,
                    employee_id=emp_id,
                    name=name,
                    email=email,
                    internal_email=int_email,
                    role="employee",
                    department=dept,
                    title=title,
                    avatar=f"https://api.dicebear.com/7.x/initials/svg?seed={name}",
                    hashed_password=auth.get_password_hash(emp_id),
                    profile={
                        "age": 30,
                        "joinDate": "2026-01-01",
                        "performanceHistory": [],
                        "skills": [],
                        "nineBoxPosition": {"performance": "Medium", "potential": "Medium"},
                        "assessment": {"hpi": 0, "hds": 0, "mvpi": 0, "completed": False},
                        "tags": [],
                        "skillAssessmentScore": 0
                    }
                )
                db.add(user)
                synced_count += 1
                
    db.commit()
    return {"status": "ok", "synced": synced_count}

@app.post("/api/users/sync-mssql")
def trigger_mssql_sync(current_user: models.User = Depends(get_current_user)):
    if current_user.role not in ["admin", "hr", "manager"]:
        raise HTTPException(status_code=403, detail="僅管理人員可執行資料庫同步")
    try:
        from backend.sync_mssql import sync_users_from_mssql
        synced_count = sync_users_from_mssql()
        return {"status": "ok", "message": f"成功從 dev.db.sysco 同步 {synced_count} 筆員工資料"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MS SQL 同步失敗: {str(e)}")

@app.get("/api/progress")
def get_all_progress(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    records = db.query(models.LearningRecord).all()
    res = []
    for r in records:
        res.append({
            "courseId": r.course_id,
            "userId": r.user_id,
            "completed": r.completed,
            "quizScore": r.quiz_score,
            "satisfaction": r.satisfaction,
            "attemptDate": r.attempt_date,
            "failCount": r.fail_count or 0,
            "lastAttemptTime": r.last_attempt_time or r.attempt_date
        })
    return res

@app.post("/api/progress")
def update_progress(req: schemas.CourseProgressUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    record = db.query(models.LearningRecord).filter_by(user_id=current_user.id, course_id=req.course_id).first()
    if not record:
        record = models.LearningRecord(
            user_id=current_user.id, 
            course_id=req.course_id, 
            completed=req.completed,
            quiz_score=req.quiz_score,
            satisfaction=req.satisfaction,
            attempt_date=now_str,
            fail_count=req.fail_count or 0,
            last_attempt_time=req.last_attempt_time or now_str
        )
        db.add(record)
    else:
        record.completed = req.completed
        if req.quiz_score is not None:
             record.quiz_score = req.quiz_score
        if req.satisfaction is not None:
             record.satisfaction = req.satisfaction
        if req.fail_count is not None:
             record.fail_count = req.fail_count
        if req.last_attempt_time is not None:
             record.last_attempt_time = req.last_attempt_time
        record.attempt_date = now_str
    db.commit()
    return {"status": "ok"}


@app.post("/api/upload")
def upload_file(req: schemas.UploadRequest, current_user: models.User = Depends(get_current_user)):
    file_b64 = req.fileB64
    if file_b64.startswith("data:"):
        file_b64 = file_b64.split(",")[1]
    file_bytes = base64.b64decode(file_b64)

    fname_lower = req.filename.lower()
    if fname_lower.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        sub_folder = "videos"
    elif fname_lower.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
        sub_folder = "documents"
    elif fname_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
        sub_folder = "images"
    else:
        sub_folder = ""

    target_dir = os.path.join(UPLOAD_DIR, sub_folder) if sub_folder else UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, req.filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    rel_url = f"/uploads/{sub_folder}/{req.filename}" if sub_folder else f"/uploads/{req.filename}"
    return {"url": rel_url}
def local_chat_fallback(course_title: str, question: str, course_desc: str = ""):
    q_lower = question.lower()
    if "安全" in q_lower or "危害" in q_lower or "防護" in q_lower or "佩戴" in q_lower:
        ans = "關於安全防護的規範，本課程強調工作現場必須全程佩戴標準安全帽與防護手套。若遇到任何緊急狀況，請依照紅色逃生指示燈的方向進行疏散，並立即通報當班主管與工安課（分機#119）。"
    elif "溝通" in q_lower or "表達" in q_lower or "說服" in q_lower:
        ans = "高效溝通的核心在於『積極聆聽』與『同理心回應』。在與跨部門協調時，建議先認同對方的立場與業務難處，再透過數據分析客觀陳述需求，這能大幅提升溝通的說服力。"
    elif "測驗" in q_lower or "考試" in q_lower or "題目" in q_lower:
        ans = "本課程的測驗共有 3 題選擇題，合格標準為 60 分。題目主要圍繞在課程講義中的核心觀念（如防護具種類、安全逃生步驟或跨部門協商法則），請多加複習講義內容。"
    elif "講義" in q_lower or "教材" in q_lower or "內容" in q_lower or "大綱" in q_lower:
        ans = f"這份教材的核心目的是協助學員快速掌握「{course_title}」的主旨。講義內包含詳細的流程步驟拆解與實際案例分析，請點選上方講義連結下載並仔細閱讀。"
    else:
        ans = f"感謝您的提問！關於您提到的問題，在「{course_title}」的實務應用中極為關鍵。建議您深入對照講義中提及的觀念，並嘗試在日常工作中實踐。如有需要，也可以與部門主管或導師進行一步探討。"
    return f"[備援模擬 AI 講師] {ans}"

def local_visual_fallback(description: str):
    import re
    phrases = [p.strip() for p in re.split(r'[,.，。、]', description) if p.strip()]
    if not phrases:
        phrases = ["核心觀念", "實務應用", "基礎知識", "關鍵績效"]
    phrases = phrases[:4]
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 250" width="100%" height="100%">
      <defs>
        <linearGradient id="centerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#4f46e5" />
          <stop offset="100%" stop-color="#7c3aed" />
        </linearGradient>
        <linearGradient id="nodeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#0284c7" />
          <stop offset="100%" stop-color="#0ea5e9" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="#faf5ff" rx="12"/>
      <circle cx="300" cy="125" r="100" fill="none" stroke="#e0f2fe" stroke-width="2" stroke-dasharray="5 5"/>
      <line x1="300" y1="125" x2="120" y2="60" stroke="#a78bfa" stroke-width="2" />
      <line x1="300" y1="125" x2="480" y2="60" stroke="#a78bfa" stroke-width="2" />
      <line x1="300" y1="125" x2="120" y2="190" stroke="#a78bfa" stroke-width="2" />
      <line x1="300" y1="125" x2="480" y2="190" stroke="#a78bfa" stroke-width="2" />
      <rect x="200" y="100" width="200" height="50" rx="25" fill="url(#centerGrad)" filter="drop-shadow(0px 4px 6px rgba(0,0,0,0.15))"/>
      <text x="300" y="130" fill="#ffffff" font-size="14" font-weight="bold" text-anchor="middle">課程核心架構</text>
    """
    coords = [(40, 40), (400, 40), (40, 170), (400, 170)]
    for idx, phrase in enumerate(phrases):
        if idx >= len(coords):
            break
        x, y = coords[idx]
        short_text = phrase[:12] + "..." if len(phrase) > 12 else phrase
        svg += f"""
          <rect x="{x}" y="{y}" width="160" height="40" rx="8" fill="url(#nodeGrad)" filter="drop-shadow(0px 2px 4px rgba(0,0,0,0.05))"/>
          <text x="{x + 80}" y="{y + 24}" fill="#ffffff" font-size="11" font-weight="medium" text-anchor="middle">{short_text}</text>
        """
    svg += "</svg>"
    return svg

def local_quiz_fallback(pdf_url: str):
    url_lower = pdf_url.lower()
    if "安全" in url_lower or "盛餘" in url_lower or "15" in url_lower or "26" in url_lower:
        questions = [
            {
                "text": "在現場工作時，佩戴安全帽與防護具的主要目的為何？",
                "options": ["應付主管檢查", "確保個人人身安全並降低職業災害風險", "提升工作速度"],
                "correctAnswer": 1
            },
            {
                "text": "關於紅色逃生指示燈的作用，以下敘述何者正確？",
                "options": ["指示辦公室方向", "在火災或緊急狀況時，指引同仁安全撤離至疏散點", "單純裝飾照明"],
                "correctAnswer": 1
            },
            {
                "text": "進入機具生產線之前，最重要執行的安檢程序是？",
                "options": ["直接開機運作以節省時間", "確實確認安全防護防護設施運作正常", "清潔機台周邊"],
                "correctAnswer": 1
            }
        ]
    elif "溝通" in url_lower:
        questions = [
            {
                "text": "高效溝通中的『積極聆聽』，其核心意義是什麼？",
                "options": ["隨時準備反駁對方的論點", "專注於理解說話者的立場、需求與本意", "打斷並強行陳述自己的意見"],
                "correctAnswer": 1
            },
            {
                "text": "在與跨部門溝通協商時，最合適的雙贏手段是？",
                "options": ["一律拒絕對方的任何要求", "提出數據客觀分析，同理對方立場，共同尋求替代方案", "找高階主管強制施壓"],
                "correctAnswer": 1
            },
            {
                "text": "提供建設性回饋 (Constructive Feedback) 的黃金法則是？",
                "options": ["對人不對事地批評", "具體、及時、且指出未來可改善之明確方向", "暗中抱怨而不直接討論"],
                "correctAnswer": 1
            }
        ]
    else:
        questions = [
            {
                "text": "本教材探討的實務觀念，首要目的在於？",
                "options": ["提升實作業務效率與專業素養", "滿足年度教育訓練時數要求", "做為淘汰員工的藉口"],
                "correctAnswer": 0
            },
            {
                "text": "遇到工作異常狀況時，最正確的處理步驟是？",
                "options": ["私下掩蓋不呈報", "立即回報當班主管並與團隊共同排除異常", "怪罪於其他部門同事"],
                "correctAnswer": 1
            },
            {
                "text": "本課程學習完成後，最正確的應用方式是？",
                "options": ["考完試後完全忘記", "融入每日的日常實務工作與跨團隊協同合作中", "私下影印給外人"],
                "correctAnswer": 1
            }
        ]
    return json.dumps(questions, ensure_ascii=False)

@app.post("/api/chat")
def chat_with_gemini(req: schemas.ChatRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    course = None
    if req.courseId:
        course = db.query(models.Course).filter(models.Course.id == req.courseId).first()
    if not course and req.courseTitle:
        course = db.query(models.Course).filter(models.Course.title == req.courseTitle).first()
        
    desc = course.description if course else ""
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": local_chat_fallback(req.courseTitle, req.question, desc)}
        
    pdf_b64 = None
    if course and course.pdf_url and course.pdf_url.startswith("/uploads/"):
        filename = course.pdf_url.replace("/uploads/", "")
        local_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(local_path):
            try:
                with open(local_path, "rb") as f:
                    pdf_bytes = f.read()
                pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
            except Exception as e:
                print("Error reading PDF for chat RAG:", e)
                
    if pdf_b64:
        prompt = f"""
          你是一位專業的企業培訓講師，專長於課程：「{course.title}」。
          請仔細閱讀並參考附件提供的 PDF 講義內容，根據講義內的知識來回答學員提出的問題。
          若講義中找不到答案，可依據您的專業知識回答，但請註明「根據講義及專業補充」。
          請用繁體中文回答，語氣專業、友善且具鼓勵性。回答請控制在 150 字以內。
          
          問題：「{req.question}」
        """
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "application/pdf", "data": pdf_b64}}
                ]
            }]
        }
    else:
        prompt = f"""
          你是一位專業的企業培訓講師，專長於課程：「{req.courseTitle}」。
          課程簡介：{desc}
          這是一位員工針對該主題提出的問題。
          請用繁體中文回答，語氣專業、友善且具鼓勵性。回答請控制在 100 字以內。
          
          問題：「{req.question}」
        """
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    req_obj = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req_obj) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return {"response": text}
    except Exception as e:
        print("Gemini API Connection failed, switching to local fallback:", e)
        return {"response": local_chat_fallback(req.courseTitle, req.question, desc)}

@app.post("/api/generate-visual")
def generate_visual(req: schemas.VisualRequest, current_user: models.User = Depends(get_current_user)):
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": local_visual_fallback(req.description)}
        
    prompt = f"""
      Create a visually appealing SVG infographic or mind map that summarizes the following course description. 
      The SVG should be colorful, modern, and self-contained (no external links).
      It should clearly outline the key takeaways or structure of the course.
      Return ONLY the raw SVG string, starting with <svg> and ending with </svg>.
      
      Course Description:
      {req.description}
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    req_obj = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req_obj) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            
            if "<svg" in text and "</svg>" in text:
                text = "<svg" + text.split("<svg")[1].split("</svg>")[0] + "</svg>"
            return {"response": text}
    except Exception as e:
        print("Gemini API Connection failed, switching to visual fallback:", e)
        return {"response": local_visual_fallback(req.description)}

@app.post("/api/generate-questions")
def generate_questions(req: schemas.GenerateQuestionsRequest, current_user: models.User = Depends(get_current_user)):
    part_url = req.pdfUrl
    if not part_url or not part_url.startswith("/uploads/"):
        return {"response": local_quiz_fallback("")}
        
    filename = part_url.replace("/uploads/", "")
    local_path = os.path.join(UPLOAD_DIR, filename)
    
    if not os.path.exists(local_path):
        return {"response": local_quiz_fallback(part_url)}
        
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": local_quiz_fallback(part_url)}
        
    try:
        with open(local_path, "rb") as f:
            pdf_bytes = f.read()
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    except Exception as e:
        print("Error reading PDF:", e)
        return {"response": local_quiz_fallback(part_url)}
        
    prompt = """
      請根據附件的講義內容，以 JSON 格式出 3 題選擇題。
      每一題必須包含： 
      - text: (字串) 題目內容
      - options: (字串陣列) 3到4個選項
      - correctAnswer: (整數) 正確解答的選項索引 (從0開始計算)
      
      請確保只回傳這格式的純 JSON 陣列 (例如：[{"text": "...", "options": ["A","B"], "correctAnswer": 0}])，不要加任何其他解說文字或是 markdown 標記。
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "application/pdf", "data": pdf_b64}}
            ]
        }]
    }
    
    req_obj = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req_obj) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            return {"response": text}
    except Exception as e:
        print("Gemini API Connection failed, switching to quiz fallback:", e)
        return {"response": local_quiz_fallback(part_url)}
