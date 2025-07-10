from pydantic import BaseModel
from typing import List, Optional, Dict
from enum import Enum

class Subject(str, Enum):
    PHYSICS = "physics"
    GEOGRAPHY = "geography"
    HISTORY = "history"
    MATHEMATICS = "mathematics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    LITERATURE = "literature"
    COMPUTER_SCIENCE = "computer_science"

class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_IN_THE_BLANKS = "fill_in_the_blanks"
    MATCH_THE_FOLLOWING = "match_the_following"

class State(str, Enum):
    FUN = "fun"
    SERIOUS = "serious"
    EDUCATIONAL = "educational"
    COMPETITIVE = "competitive"

# Request schema
class QuestionRequest(BaseModel):
    subject: Subject
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    num_questions: int = 5
    topic: Optional[str] = None
    sub_topic: Optional[str] = None
    state: State = State.FUN

# Type-specific data schemas
class MultipleChoiceData(BaseModel):
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str

class TrueFalseData(BaseModel):
    correct_answer: str

class FillInBlanksData(BaseModel):
    answers: List[str]

class MatchFollowingData(BaseModel):
    pairs: Dict[str, str]

# Main response schema
class QuestionResponse(BaseModel):
    id: Optional[int] = None
    subject: str
    difficulty: str
    question_type: str
    topic: str
    sub_topic: Optional[str] = None
    question_text: str
    explanation: Optional[str] = None
    elo_rating: int
    elo_min: int
    elo_max: int
    state: str
    
    # Question type specific data (only one will be populated)
    multiple_choice_data: Optional[MultipleChoiceData] = None
    true_false_data: Optional[TrueFalseData] = None
    fill_in_blanks_data: Optional[FillInBlanksData] = None
    match_following_data: Optional[MatchFollowingData] = None

    class Config:
        from_attributes = True

# Other response schemas
class MessageResponse(BaseModel):
    message: str

class SubjectsResponse(BaseModel):
    subjects: List[str]

class DifficultyResponse(BaseModel):
    difficulty_levels: List[str]

class QuestionTypesResponse(BaseModel):
    question_types: List[str]

class StatesResponse(BaseModel):
    states: List[str]