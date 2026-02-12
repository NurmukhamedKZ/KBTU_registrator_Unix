"""
Database models and operations for storing test questions and answers.

This module handles all PostgreSQL database interactions including:
- User management
- Question storage
- Answer options storage
- Multi-user data isolation
"""

import os
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    """User model - stores user information."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    questions = relationship("Question", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(email='{self.email}')>"


class Question(Base):
    """Question model - stores test questions."""
    __tablename__ = 'questions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    lesson_name = Column(String(500))
    lesson_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="questions")
    answers = relationship("Answer", back_populates="question", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Question(id={self.id}, text='{self.question_text[:50]}...')>"


class Answer(Base):
    """Answer model - stores answer options for questions."""
    __tablename__ = 'answers'
    
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False, index=True)
    answer_text = Column(Text, nullable=False)
    is_selected = Column(Boolean, default=False)  # Was this answer selected by the agent
    position = Column(Integer)  # Order of the answer in the list (0-based)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    question = relationship("Question", back_populates="answers")
    
    def __repr__(self):
        return f"<Answer(id={self.id}, text='{self.answer_text[:30]}...', selected={self.is_selected})>"


class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, database_url: str):
        """
        Initialize database connection.
        
        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.engine = None
        self.Session = None
        self._initialize()
    
    def _initialize(self):
        """Initialize database engine and create tables."""
        try:
            # Create engine with connection pooling
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=5,
                max_overflow=10
            )
            
            # Create all tables
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
            
            # Create session factory
            self.Session = sessionmaker(bind=self.engine)
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def get_or_create_user(self, email: str) -> Optional[User]:
        """
        Get existing user or create a new one.
        
        Args:
            email: User's email address
            
        Returns:
            User object or None if error
        """
        session = self.Session()
        try:
            user = session.query(User).filter_by(email=email).first()
            
            if not user:
                user = User(email=email)
                session.add(user)
                session.commit()
                logger.info(f"Created new user: {email}")
            else:
                logger.debug(f"Found existing user: {email}")
            
            # Refresh to get the latest data
            session.refresh(user)
            return user
            
        except SQLAlchemyError as e:
            logger.error(f"Error getting/creating user: {e}")
            session.rollback()
            return None
        finally:
            session.close()
    
    def save_question_with_answers(
        self,
        user_email: str,
        question_text: str,
        answer_options: List[str],
        selected_answer_idx: int,
        lesson_name: Optional[str] = None,
        lesson_url: Optional[str] = None
    ) -> bool:
        """
        Save a question with all its answer options.
        
        Args:
            user_email: Email of the user answering the question
            question_text: The question text
            answer_options: List of all answer options
            selected_answer_idx: Index of the selected answer (0-based)
            lesson_name: Name of the lesson (optional)
            lesson_url: URL of the lesson (optional)
            
        Returns:
            True if saved successfully, False otherwise
        """
        session = self.Session()
        try:
            # Get or create user
            user = session.query(User).filter_by(email=user_email).first()
            if not user:
                user = User(email=user_email)
                session.add(user)
                session.flush()  # Get the user ID
            
            # Create question
            question = Question(
                user_id=user.id,
                question_text=question_text,
                lesson_name=lesson_name,
                lesson_url=lesson_url
            )
            session.add(question)
            session.flush()  # Get the question ID
            
            # Create answer options
            for idx, answer_text in enumerate(answer_options):
                answer = Answer(
                    question_id=question.id,
                    answer_text=answer_text,
                    is_selected=(idx == selected_answer_idx),
                    position=idx
                )
                session.add(answer)
            
            session.commit()
            logger.info(f"Saved question with {len(answer_options)} answers for user {user_email}")
            return True
            
        except SQLAlchemyError as e:
            logger.error(f"Error saving question: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_user_questions(
        self,
        user_email: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get questions for a specific user.
        
        Args:
            user_email: User's email address
            limit: Maximum number of questions to return
            offset: Number of questions to skip
            
        Returns:
            List of question dictionaries with answers
        """
        session = self.Session()
        try:
            user = session.query(User).filter_by(email=user_email).first()
            if not user:
                return []
            
            questions = (
                session.query(Question)
                .filter_by(user_id=user.id)
                .order_by(Question.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            
            result = []
            for q in questions:
                answers = (
                    session.query(Answer)
                    .filter_by(question_id=q.id)
                    .order_by(Answer.position)
                    .all()
                )
                
                result.append({
                    'id': q.id,
                    'question_text': q.question_text,
                    'lesson_name': q.lesson_name,
                    'lesson_url': q.lesson_url,
                    'created_at': q.created_at.isoformat(),
                    'answers': [
                        {
                            'text': a.answer_text,
                            'is_selected': a.is_selected,
                            'position': a.position
                        }
                        for a in answers
                    ]
                })
            
            return result
            
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving questions: {e}")
            return []
        finally:
            session.close()
    
    def get_question_count(self, user_email: str) -> int:
        """
        Get total number of questions for a user.
        
        Args:
            user_email: User's email address
            
        Returns:
            Number of questions
        """
        session = self.Session()
        try:
            user = session.query(User).filter_by(email=user_email).first()
            if not user:
                return 0
            
            count = session.query(Question).filter_by(user_id=user.id).count()
            return count
            
        except SQLAlchemyError as e:
            logger.error(f"Error counting questions: {e}")
            return 0
        finally:
            session.close()
    
    def get_all_questions(
        self,
        limit: Optional[int] = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all questions from all users (for shared demo)."""
        session = self.Session()
        try:
            query = session.query(Question).order_by(Question.created_at.desc()).offset(offset)
            if limit is not None:
                query = query.limit(limit)
            questions = query.all()
            
            result = []
            for q in questions:
                user = session.query(User).filter_by(id=q.user_id).first()
                answers = (
                    session.query(Answer)
                    .filter_by(question_id=q.id)
                    .order_by(Answer.position)
                    .all()
                )
                
                result.append({
                    'id': q.id,
                    'question_text': q.question_text,
                    'lesson_name': q.lesson_name,
                    'lesson_url': q.lesson_url,
                    'created_at': q.created_at.isoformat(),
                    'user_email': user.email if user else None,
                    'answers': [
                        {
                            'text': a.answer_text,
                            'is_selected': a.is_selected,
                            'position': a.position
                        }
                        for a in answers
                    ]
                })
            
            return result
            
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving questions: {e}")
            return []
        finally:
            session.close()
    
    def get_all_question_count(self) -> int:
        """Get total count of all questions."""
        session = self.Session()
        try:
            return session.query(Question).count()
        except SQLAlchemyError as e:
            logger.error(f"Error counting questions: {e}")
            return 0
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """
        Test database connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            session = self.Session()
            session.execute(text("SELECT 1"))
            session.close()
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
