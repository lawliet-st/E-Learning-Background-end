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

from .database import Base, engine, get_db
from . import models, schemas, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
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

@app.get("/uploads/{filename}")
def serve_upload(filename: str, request: Request):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="檔案不存在")
        
    mime_type = "video/mp4" if filename.endswith(".mp4") else "video/webm" if filename.endswith(".webm") else None
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
                    chunk = f.read(min(bytes_left, 1024 * 64)) # 64KB chunks
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
    # Everyone might need to see everyone for metrics? Or admin only.
    users = db.query(models.User).all()
    # Mask passwords
    res = []
    for u in users:
        res.append({
            "id": u.id, "name": u.name, "employee_id": u.employee_id,
            "department": u.department, "title": u.title, "role": u.role,
            "profile": u.profile, "avatar": u.avatar, "internalEmail": u.internal_email
        })
    return res

@app.get("/api/courses")
def get_courses(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    courses = db.query(models.Course).all()
    # Map model to frontend keys
    res = []
    for c in courses:
        res.append({
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "category": c.category,
            "type": c.type,
            "createdAt": c.created_at,
            "thumbnail": c.thumbnail,
            "videoUrl": c.video_url,
            "pdfUrl": c.pdf_url,
            "duration": c.duration,
            "durationSeconds": c.duration_seconds,
            "visualSummary": c.visual_summary,
            "attributes": c.attributes,
            "questions": c.questions,
            "compulsoryTargets": c.compulsory_targets
        })
    return res

@app.post("/api/courses")
def create_course(course_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
    
    existing = db.query(models.Course).filter(models.Course.id == course_data.get("id")).first()
    if existing:
        raise HTTPException(status_code=400, detail="課程已存在")
        
    course = models.Course(
        id=course_data.get("id"),
        title=course_data.get("title", ""),
        description=course_data.get("description", ""),
        category=course_data.get("category", ""),
        type=course_data.get("type", "elective"),
        created_at=course_data.get("createdAt", ""),
        thumbnail=course_data.get("thumbnail", ""),
        video_url=course_data.get("videoUrl", ""),
        pdf_url=course_data.get("pdfUrl", ""),
        duration=course_data.get("duration", "60 分鐘"),
        duration_seconds=course_data.get("durationSeconds", 3600),
        visual_summary=course_data.get("visualSummary", ""),
        attributes=course_data.get("attributes"),
        questions=course_data.get("questions"),
        compulsory_targets=course_data.get("compulsoryTargets")
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course

@app.put("/api/courses/{course_id}")
def update_course(course_id: str, course_data: dict = Body(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")
        
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="找不到課程")
        
    course.title = course_data.get("title", course.title)
    course.description = course_data.get("description", course.description)
    course.category = course_data.get("category", course.category)
    course.type = course_data.get("type", course.type)
    course.thumbnail = course_data.get("thumbnail", course.thumbnail)
    course.video_url = course_data.get("videoUrl", course.video_url)
    course.pdf_url = course_data.get("pdfUrl", course.pdf_url)
    course.duration = course_data.get("duration", course.duration)
    course.duration_seconds = course_data.get("durationSeconds", course.duration_seconds)
    course.visual_summary = course_data.get("visualSummary", course.visual_summary)
    course.attributes = course_data.get("attributes", course.attributes)
    course.questions = course_data.get("questions", course.questions)
    course.compulsory_targets = course_data.get("compulsoryTargets", course.compulsory_targets)
    
    db.commit()
    db.refresh(course)
    return course

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
            "attemptDate": r.attempt_date
        })
    return res

@app.post("/api/progress")
def update_progress(req: schemas.CourseProgressUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from datetime import datetime
    record = db.query(models.LearningRecord).filter_by(user_id=current_user.id, course_id=req.course_id).first()
    if not record:
        record = models.LearningRecord(
            user_id=current_user.id, 
            course_id=req.course_id, 
            completed=req.completed,
            quiz_score=req.quiz_score,
            satisfaction=req.satisfaction,
            attempt_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        db.add(record)
    else:
        record.completed = req.completed
        if req.quiz_score is not None:
             record.quiz_score = req.quiz_score
        if req.satisfaction is not None:
             record.satisfaction = req.satisfaction
        record.attempt_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.commit()
    return {"status": "ok"}

@app.post("/api/upload")
def upload_file(req: schemas.UploadRequest, current_user: models.User = Depends(get_current_user)):
    # To avoid python-multipart, we accept base64 payload.
    file_b64 = req.fileB64
    if file_b64.startswith("data:"):
        file_b64 = file_b64.split(",")[1]
    file_bytes = base64.b64decode(file_b64)
    file_path = os.path.join(UPLOAD_DIR, req.filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    # Return URL starting with /uploads
    return {"url": f"/uploads/{req.filename}"}

@app.post("/api/chat")
def chat_with_gemini(req: schemas.ChatRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": "AI 家教尚未設定 (缺少 API Key)。"}
        
    course = None
    if req.courseId:
        course = db.query(models.Course).filter(models.Course.id == req.courseId).first()
    if not course and req.courseTitle:
        course = db.query(models.Course).filter(models.Course.title == req.courseTitle).first()
        
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
        desc = course.description if course else ""
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
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return {"response": "系統偵測到您的 Gemini API 金鑰無效！請開啟 .env.local 檔案並填入正確的 API Key。"}
        return {"response": "抱歉，我目前無法連線到知識庫。"}
    except Exception as e:
        print("Gemini API Error:", e)
        return {"response": "抱歉，發生了未知的錯誤。"}

@app.post("/api/generate-visual")
def generate_visual(req: schemas.VisualRequest, current_user: models.User = Depends(get_current_user)):
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": ""}
        
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
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return {"response": "ERROR_INVALID_KEY"}
        return {"response": ""}
    except Exception as e:
        print("Gemini API Error:", e)
        return {"response": ""}

@app.post("/api/generate-questions")
def generate_questions(req: schemas.GenerateQuestionsRequest, current_user: models.User = Depends(get_current_user)):
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": ""}
    
    part_url = req.pdfUrl
    if part_url.startswith("/uploads/"):
        filename = part_url.replace("/uploads/", "")
        local_path = os.path.join(UPLOAD_DIR, filename)
    else:
        return {"response": ""}
        
    if not os.path.exists(local_path):
        return {"response": ""}
        
    try:
        with open(local_path, "rb") as f:
            pdf_bytes = f.read()
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    except Exception as e:
        print("Error reading PDF:", e)
        return {"response": ""}
        
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
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return {"response": "ERROR_INVALID_KEY"}
        return {"response": ""}
    except Exception as e:
        print("Gemini API Error in generating questions:", e)
        return {"response": ""}
