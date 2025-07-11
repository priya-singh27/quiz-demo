from sqlalchemy import and_, func
import logging
from sqlalchemy.orm import Session
from models import Question
from schemas import (
    QuestionRequest, QuestionResponse, QuestionType,
    MultipleChoiceData, TrueFalseData, FillInBlanksData, MatchFollowingData
)
logger = logging.getLogger(__name__)

def demonstrate_elo_changes( user_rating, user_attempts, question_rating, question_attempts, is_correct):
    """
    Show how question rating changes based on different user responses
    """
    result = calculate_rating_change_example(
        question_rating, question_attempts,
        user_rating, user_attempts, 
        is_correct
    )
    
    if abs(result['question_change']) <= 5:
        impact = "minimal"
    elif abs(result['question_change']) <= 15:
        impact = "moderate" 
    else:
        impact = "significant"
        
    print(f"💡 Impact on question: {impact}")
    print(f"🧠 Result: {result}")

def calculate_rating_change_example(question_rating, question_attempts, 
                                  user_rating, user_attempts, is_correct):
    """Calculate rating changes for example scenarios"""
    
    user_expected = 1 / (1 + 10 ** ((question_rating - user_rating) / 400))
    question_expected = 1 - user_expected
    
    user_actual = 1.0 if is_correct else 0.0
    question_actual = 0.0 if is_correct else 1.0
    
    user_k = get_k_factor_example(user_rating, user_attempts)
    question_k = get_k_factor_example(question_rating, question_attempts)
    
    user_new_rating = user_rating + int(user_k * (user_actual - user_expected))
    question_new_rating = question_rating + int(question_k * (question_actual - question_expected))
    
    user_new_rating = max(800, min(2400, user_new_rating))
    question_new_rating = max(800, min(2400, question_new_rating))
    
    return {
        'user_expected': user_expected,
        'question_expected': question_expected,
        'user_new_rating': user_new_rating,
        'question_new_rating': question_new_rating,
        'user_change': user_new_rating - user_rating,
        'question_change': question_new_rating - question_rating,
        'user_k': user_k,
        'question_k': question_k
    }

def get_k_factor_example(rating, attempts_count):
    """Get K-factor for rating volatility"""
    if attempts_count < 10:
        return 40
    elif rating < 1000: 
        return 36
    elif rating > 2000:
        return 24
    else:
        return 32

"""
user rating,

user_attempts
= Total number of questions this USER has answered across the entire platform,

question_rating,

question_attempts
= Total number of users who have attempted this specific QUESTION,
"""
scenarios = [
    
        (800, 10, 1000, 0 ,True),
        (800, 10, 1000, 5, False),
        (1000, 15, 1000, 0, True), 
        (1000, 15, 1000, 0, False,),
        (1200, 20, 1000, 0,True,),
        (1200, 20, 1000, 0,False,),
        (1500, 25, 1000, 0,True,),
        (1500, 25, 1000, 0,False),
        (600, 2, 1000, 0,True,),
        (600, 2, 1000, 0,False),
    ]

for user_rating, user_attempts, question_rating, question_attempts, is_correct in scenarios:
    demonstrate_elo_changes(
        user_rating,
        user_attempts,
        question_rating,
        question_attempts,
        is_correct
    )


def check_duplicate_question(db: Session, question_text: str, subject: str, question_type: str) -> bool:
    """Check if a question already exists in the database"""
    existing = db.query(Question).filter(
        and_(
            func.lower(Question.question_text) == question_text.lower().strip(),
            Question.subject == subject,
            Question.question_type == question_type
        )
    ).first()
    
    return existing is not None

def convert_to_frontend_format(question_response: QuestionResponse) -> dict:
    """Convert normalized format to frontend-compatible format"""
    
    logger.info(f"Converting question: {question_response.question_text[:50]}...")
    
    result = {
        "id": question_response.id,
        "topic": question_response.topic,
        "sub_topic": question_response.sub_topic,
        "question": question_response.question_text,
        "explanation": question_response.explanation,
        "elo_rating": question_response.elo_rating,
        "elo_range": [question_response.elo_min, question_response.elo_max],
        "state": question_response.state,
        "options": None,
        "correct_answer": "",
        "blanks": None,
        "match_pairs": None
    }
    
    if question_response.multiple_choice_data:
        mc = question_response.multiple_choice_data
        result["options"] = [
            f"A) {mc.option_a}",
            f"B) {mc.option_b}",
            f"C) {mc.option_c}",
            f"D) {mc.option_d}"
        ]
        result["correct_answer"] = mc.correct_option
    
    elif question_response.true_false_data:
        result["correct_answer"] = question_response.true_false_data.correct_answer
    
    elif question_response.fill_in_blanks_data:
        answers = question_response.fill_in_blanks_data.answers
        result["blanks"] = answers
        result["correct_answer"] = ",".join([str(ans) for ans in answers])
    
    elif question_response.match_following_data:
        pairs = question_response.match_following_data.pairs
        result["match_pairs"] = pairs
        result["correct_answer"] = ",".join([f"{str(k)}={str(v)}" for k, v in pairs.items()])
    
    return result

def create_question_response_from_dict(question_data: dict, request: QuestionRequest, question_id: int) -> QuestionResponse:
    """
    Create a QuestionResponse object from AI-generated question data
    """
    response = QuestionResponse(
        id=question_id,
        subject=request.subject.value,
        difficulty=request.difficulty.value,
        question_type=request.question_type.value,
        topic=question_data['topic'],
        sub_topic=question_data.get('sub_topic'),
        question_text=question_data['question_text'],
        explanation=question_data.get('explanation'),
        elo_rating=question_data['elo_rating'],
        elo_min=question_data['elo_range'][0],
        elo_max=question_data['elo_range'][1],
        state=question_data['state'].value if hasattr(question_data['state'], 'value') else question_data['state']
    )
    
    if request.question_type == QuestionType.MULTIPLE_CHOICE and question_data.get('options'):
        response.multiple_choice_data = MultipleChoiceData(
            option_a=question_data['options'][0][3:],  
            option_b=question_data['options'][1][3:],  
            option_c=question_data['options'][2][3:],  
            option_d=question_data['options'][3][3:],  
            correct_option=question_data['correct_answer']
        )
    
    elif request.question_type == QuestionType.TRUE_FALSE:
        response.true_false_data = TrueFalseData(
            correct_answer=question_data['correct_answer']
        )
    
    elif request.question_type == QuestionType.FILL_IN_THE_BLANKS and question_data.get('blanks'):
        response.fill_in_blanks_data = FillInBlanksData(
            answers=question_data['blanks']
        )
    
    elif request.question_type == QuestionType.MATCH_THE_FOLLOWING and question_data.get('match_pairs'):
        response.match_following_data = MatchFollowingData(
            pairs=question_data['match_pairs']
        )
    
    return response
