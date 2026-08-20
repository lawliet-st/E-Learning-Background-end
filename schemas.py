from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class LoginRequest(BaseModel):
    employee_id: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]

class CourseProgressUpdate(BaseModel):
    course_id: str
    completed: bool
    quiz_score: Optional[int] = None
    satisfaction: Optional[int] = None
    fail_count: Optional[int] = None
    last_attempt_time: Optional[str] = None

class UploadRequest(BaseModel):
    filename: str
    fileB64: str

class ChatRequest(BaseModel):
    courseTitle: str
    question: str
    courseId: Optional[str] = None

class VisualRequest(BaseModel):
    description: str

class GenerateQuestionsRequest(BaseModel):
    pdfUrl: str

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    type: Optional[str] = "notice"
    image_url: Optional[str] = None
    course_id: Optional[str] = None
    is_pinned: Optional[bool] = False

class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    type: Optional[str] = None
    image_url: Optional[str] = None
    course_id: Optional[str] = None
    is_pinned: Optional[bool] = None

class CategoryCreate(BaseModel):
    name: str

class CategoryUpdate(BaseModel):
    name: str
