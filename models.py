from __future__ import annotations

from typing import List, Optional, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True) # Using UUID or frontend string ID
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False) # 員工編號 (帳號)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False) # 身分證字號雜湊 (密碼)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    internal_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="employee", nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Store complex TalentProfileData as JSON to avoid excessive table mapping
    profile: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    learning_records: Mapped[List["LearningRecord"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50), default="elective", nullable=False) # compulsory or elective
    status: Mapped[str] = mapped_column(String(50), default="published", nullable=False) # draft, published, closed
    pass_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    is_random_10: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_random_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_random_options: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visual_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    questions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    compulsory_targets: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    publish_history: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)

    learning_records: Mapped[List["LearningRecord"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiz_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    satisfaction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempt_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    user: Mapped["User"] = relationship(back_populates="learning_records")
    course: Mapped["Course"] = relationship(back_populates="learning_records")


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="notice", nullable=False) # system, course_auto, notice
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    course_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    author: Mapped[str] = mapped_column(String(100), default="系統管理員", nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)


