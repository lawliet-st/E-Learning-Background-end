from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from typing import List

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

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
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
    return courses

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
def chat_with_gemini(req: schemas.ChatRequest, current_user: models.User = Depends(get_current_user)):
    api_key = get_gemini_api_key()
    if not api_key:
        return {"response": "AI 家教尚未設定 (缺少 API Key)。"}
    
    prompt = f"""
      你是一位專業的企業培訓講師，專長於課程：「{req.courseTitle}」。
      這是一位員工針對該主題提出的問題。
      請用繁體中文回答，語氣專業、友善且具鼓勵性。回答請控制在 100 字以內。
      
      問題：「{req.question}」
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
