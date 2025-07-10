from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Question(Base):
    """Main questions table - contains common properties for all question types"""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, index=True, nullable=False)
    difficulty = Column(String, index=True, nullable=False)  # easy, medium, hard
    question_type = Column(String, index=True, nullable=False)  # multiple_choice, true_false, etc.
    topic = Column(String, index=True, nullable=False)
    sub_topic = Column(String, nullable=True)
    question_text = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    elo_rating = Column(Integer, nullable=False)
    elo_min = Column(Integer, nullable=False)
    elo_max = Column(Integer, nullable=False)
    state = Column(String, nullable=False)  
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships to specific question types
    multiple_choice = relationship("MultipleChoiceQuestion", back_populates="question", uselist=False)
    true_false = relationship("TrueFalseQuestion", back_populates="question", uselist=False)
    fill_in_blanks = relationship("FillInBlanksQuestion", back_populates="question", uselist=False)
    match_following = relationship("MatchFollowingQuestion", back_populates="question", uselist=False)

class MultipleChoiceQuestion(Base):
    """Multiple choice specific data"""
    __tablename__ = "multiple_choice_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, unique=True)
    option_a = Column(String, nullable=False)
    option_b = Column(String, nullable=False)
    option_c = Column(String, nullable=False)
    option_d = Column(String, nullable=False)
    correct_option = Column(String, nullable=False)  # 'A', 'B', 'C', or 'D'
    
    question = relationship("Question", back_populates="multiple_choice")

class TrueFalseQuestion(Base):
    """True/False specific data"""
    __tablename__ = "true_false_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, unique=True)
    correct_answer = Column(String, nullable=False)  # 'True' or 'False'
    
    question = relationship("Question", back_populates="true_false")

class FillInBlanksQuestion(Base):
    """Fill in the blanks specific data"""
    __tablename__ = "fill_in_blanks_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, unique=True)
    answers = Column(JSON, nullable=False) 
    
    question = relationship("Question", back_populates="fill_in_blanks")

class MatchFollowingQuestion(Base):
    """Match the following specific data"""
    __tablename__ = "match_following_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    pairs = Column(JSON, nullable=False) 
    
    # Relationship
    question = relationship("Question", back_populates="match_following")