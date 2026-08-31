from __future__ import annotations

from typing import List, Optional, Any

from sqlalchemy import Boolean, ForeignKey, Integer, Float, String, Text, JSON, Unicode, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    join_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nine_box_perf: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nine_box_pot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    skill_assessment_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hpi_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hds_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mvpi_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assessment_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="user_profile")


class UserSkill(Base):
    __tablename__ = "user_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    full_mark: Mapped[int] = mapped_column(Integer, default=100)

    user: Mapped["User"] = relationship(back_populates="user_skills")


class UserPerformanceHistory(Base):
    __tablename__ = "user_performance_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[str] = mapped_column(String(20), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped["User"] = relationship(back_populates="performance_history")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    internal_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="employee", nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    learning_records: Mapped[List["LearningRecord"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_profile: Mapped[Optional["UserProfile"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_skills: Mapped[List["UserSkill"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    performance_history: Mapped[List["UserPerformanceHistory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class CourseAttribute(Base):
    __tablename__ = "course_attributes"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    logic: Mapped[int] = mapped_column(Integer, default=50)
    professional: Mapped[int] = mapped_column(Integer, default=50)
    difficulty: Mapped[int] = mapped_column(Integer, default=50)
    importance: Mapped[int] = mapped_column(Integer, default=50)
    knowledge_limit: Mapped[int] = mapped_column(Integer, default=50)

    course: Mapped["Course"] = relationship(back_populates="course_attribute")


class CourseQuestionOption(Base):
    __tablename__ = "course_question_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_db_id: Mapped[int] = mapped_column(ForeignKey("course_questions.id", ondelete="CASCADE"), nullable=False)
    option_order: Mapped[int] = mapped_column(Integer, nullable=False)
    option_text: Mapped[str] = mapped_column(UnicodeText, nullable=False)

    question: Mapped["CourseQuestion"] = relationship(back_populates="options")


class CourseQuestion(Base):
    __tablename__ = "course_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    correct_answer: Mapped[int] = mapped_column(Integer, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="course_questions")
    options: Mapped[List["CourseQuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="CourseQuestionOption.option_order"
    )


class CourseCompulsoryTarget(Base):
    __tablename__ = "course_compulsory_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'department' or 'user'
    target_value: Mapped[str] = mapped_column(Unicode(100), nullable=False)

    course: Mapped["Course"] = relationship(back_populates="compulsory_targets_rel")


class CoursePublishHistory(Base):
    __tablename__ = "course_publish_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(Unicode(100), nullable=False)

    course: Mapped["Course"] = relationship(back_populates="publish_history_rel")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Unicode(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50), default="elective", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="published", nullable=False)
    pass_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    is_random_10: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_random_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_random_options: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(Unicode(50), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visual_summary: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)

    learning_records: Mapped[List["LearningRecord"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
    course_attribute: Mapped[Optional["CourseAttribute"]] = relationship(
        back_populates="course",
        uselist=False,
        cascade="all, delete-orphan",
    )
    course_questions: Mapped[List["CourseQuestion"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
    compulsory_targets_rel: Mapped[List["CourseCompulsoryTarget"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
    publish_history_rel: Mapped[List["CoursePublishHistory"]] = relationship(
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
    title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    content: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="notice", nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    course_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    author: Mapped[str] = mapped_column(Unicode(100), default="系統管理員", nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Unicode(100), unique=True, index=True, nullable=False)
    created_at: Mapped[str] = mapped_column(String(50), nullable=False)
