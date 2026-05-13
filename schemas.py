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

class UploadRequest(BaseModel):
    filename: str
    fileB64: str

class ChatRequest(BaseModel):
    courseTitle: str
    question: str

class VisualRequest(BaseModel):
    description: str

class GenerateQuestionsRequest(BaseModel):
    pdfUrl: str
