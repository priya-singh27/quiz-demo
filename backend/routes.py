from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Optional
import logging
import hashlib

from models import Question
from db import get_db
from schemas import (
    QuestionRequest, QuestionResponse, QuestionType,
    MultipleChoiceData, TrueFalseData, FillInBlanksData, MatchFollowingData
)
from services import QuestionService, AIService

logger = logging.getLogger(__name__)

question_router = APIRouter(prefix="/questions", tags=["questions"])

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

@question_router.post("/generate")
async def generate_questions(request: QuestionRequest, db: Session = Depends(get_db)):
    """
    Generate questions using AI and save new ones to database.
    Always generates fresh questions, saves non-duplicates to DB.
    """
    
    logger.info(f"Starting question generation for {request.num_questions} {request.question_type.value} questions")
    logger.info(f"Subject: {request.subject.value}, Difficulty: {request.difficulty.value}")
    
    try:
        logger.info("Calling AI service to generate questions...")
        question_dicts = await AIService.generate_questions_with_ai(request)
        logger.info(f"AI generated {len(question_dicts)} question dictionaries")
        
        if not question_dicts:
            raise HTTPException(status_code=500, detail="AI failed to generate any questions")
        
        saved_questions = []
        frontend_questions = []
        duplicates_found = 0
        
        for i, question_data in enumerate(question_dicts):
            try:
                logger.info(f"Processing question {i+1}/{len(question_dicts)}")
                
                is_duplicate = check_duplicate_question(
                    db, 
                    question_data['question_text'], 
                    request.subject.value, 
                    request.question_type.value
                )
                
                if is_duplicate:
                    duplicates_found += 1
                    logger.info(f"Duplicate found, skipping save: {question_data['question_text'][:50]}...")
                else:
                    logger.info(f"Saving new question to database...")
                    db_question = QuestionService.save_question_to_db(question_data, request, db)
                    
                    question_response = QuestionService.get_question_with_details(db, db_question.id)
                    if question_response:
                        saved_questions.append(question_response)
                        logger.info(f"Successfully saved question {db_question.id}")
      
                temp_response = create_question_response_from_dict(question_data, request, i+1)
                frontend_question = convert_to_frontend_format(temp_response)
                frontend_questions.append(frontend_question)
                
            except Exception as e:
                logger.error(f"Error processing question {i+1}: {e}")
                continue
        
        logger.info(f"Summary: {len(saved_questions)} new questions saved, {duplicates_found} duplicates skipped")
        
        if len(frontend_questions) < request.num_questions:
            logger.warning(f"Only got {len(frontend_questions)} questions, requested {request.num_questions}")
        
        final_questions = frontend_questions[:request.num_questions]
        
        if not final_questions:
            raise HTTPException(status_code=500, detail="No questions could be generated")
        
        response_data = {
            "subject": request.subject.value,
            "difficulty": request.difficulty.value,
            "question_type": request.question_type.value,
            "questions": final_questions,
            "source": "ai_generated",
            "stats": {
                "total_returned": len(final_questions),
                "from_database": 0, 
                "newly_generated": len(saved_questions),
                "duplicates_skipped": duplicates_found
            }
        }
        
        logger.info(f"SUCCESS! Returning {len(final_questions)} questions to frontend")
        logger.info(f"Stats: {response_data['stats']}")
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CRITICAL ERROR in generate_questions: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")