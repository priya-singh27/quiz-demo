from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import logging

from db import get_db
from schemas import (
    QuestionRequest
)
from services import QuestionService, AIService
from utils import check_duplicate_question, create_question_response_from_dict, convert_to_frontend_format

logger = logging.getLogger(__name__)

question_router = APIRouter(prefix="/questions", tags=["questions"])

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