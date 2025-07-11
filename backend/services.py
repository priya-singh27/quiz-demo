from typing import List, Optional
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
import os
import logging

from models import (
    Question, MultipleChoiceQuestion, TrueFalseQuestion, 
    FillInBlanksQuestion, MatchFollowingQuestion
)
from schemas import (
    QuestionRequest, QuestionResponse, QuestionType, State,
    MultipleChoiceData, TrueFalseData, FillInBlanksData, MatchFollowingData
)

# fun, new,
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_key = os.getenv("OPENAI_API_KEY")
openrouter = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1", 
    api_key=openai_key
) if openai_key else None

class QuestionService:
    """Service class for question-related operations with normalized schema"""
    
    @staticmethod
    def save_question_to_db(question_data: dict, request: QuestionRequest, db: Session) -> Question:
        """Save a question to the normalized database structure"""
        try:
            # Create main question record
            question = Question(
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
                state=request.state.value
            )
            
            db.add(question)
            db.flush()  # Get the question ID
            
            # Create type-specific record
            if request.question_type == QuestionType.MULTIPLE_CHOICE:
                mc_question = MultipleChoiceQuestion(
                    question_id=question.id,
                    option_a=question_data['options'][0][3:],  # Remove "A) " prefix
                    option_b=question_data['options'][1][3:],  # Remove "B) " prefix
                    option_c=question_data['options'][2][3:],  # Remove "C) " prefix
                    option_d=question_data['options'][3][3:],  # Remove "D) " prefix
                    correct_option=question_data['correct_answer']
                )
                db.add(mc_question)
            
            elif request.question_type == QuestionType.TRUE_FALSE:
                tf_question = TrueFalseQuestion(
                    question_id=question.id,
                    correct_answer=question_data['correct_answer']
                )
                db.add(tf_question)
            
            elif request.question_type == QuestionType.FILL_IN_THE_BLANKS:
                fib_question = FillInBlanksQuestion(
                    question_id=question.id,
                    answers=question_data['blanks']
                )
                db.add(fib_question)
            
            elif request.question_type == QuestionType.MATCH_THE_FOLLOWING:
                match_question = MatchFollowingQuestion(
                    question_id=question.id,
                    pairs=question_data['match_pairs']
                )
                db.add(match_question)
            
            db.commit()
            db.refresh(question)
            logger.info(f"Successfully saved question {question.id} to normalized database")
            return question
            
        except Exception as e:
            logger.error(f"Error saving question to database: {e}")
            db.rollback()
            raise

    @staticmethod
    def get_question_with_details(db: Session, question_id: int) -> Optional[QuestionResponse]:
        """Get a question with its type-specific details"""
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            return None
        
        return QuestionService._convert_db_to_response(question)

    @staticmethod
    def get_questions_from_db(
        db: Session,
        subject: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        limit: int = 10
    ) -> List[QuestionResponse]:
        """Retrieve questions from normalized database with optional filters"""
        try:
            query = db.query(Question)
            
            if subject:
                query = query.filter(Question.subject == subject)
            if difficulty:
                query = query.filter(Question.difficulty == difficulty)
            if question_type:
                query = query.filter(Question.question_type == question_type)
            
            questions = query.limit(limit).all()
            logger.info(f"Retrieved {len(questions)} questions from database")
            
            return [QuestionService._convert_db_to_response(q) for q in questions]
        except Exception as e:
            logger.error(f"Error retrieving questions: {e}")
            raise

    @staticmethod
    def _convert_db_to_response(question: Question) -> QuestionResponse:
        """Convert database question to response format"""
        response = QuestionResponse(
            id=question.id,
            subject=question.subject,
            difficulty=question.difficulty,
            question_type=question.question_type,
            topic=question.topic,
            sub_topic=question.sub_topic,
            question_text=question.question_text,
            explanation=question.explanation,
            elo_rating=question.elo_rating,
            elo_min=question.elo_min,
            elo_max=question.elo_max,
            state=question.state
        )
        
        # Add type-specific data
        if question.question_type == "multiple_choice" and question.multiple_choice:
            mc = question.multiple_choice
            response.multiple_choice_data = MultipleChoiceData(
                option_a=mc.option_a,
                option_b=mc.option_b,
                option_c=mc.option_c,
                option_d=mc.option_d,
                correct_option=mc.correct_option
            )
        
        elif question.question_type == "true_false" and question.true_false:
            tf = question.true_false
            response.true_false_data = TrueFalseData(
                correct_answer=tf.correct_answer
            )
        
        elif question.question_type == "fill_in_the_blanks" and question.fill_in_blanks:
            fib = question.fill_in_blanks
            response.fill_in_blanks_data = FillInBlanksData(
                answers=fib.answers
            )
        
        elif question.question_type == "match_the_following" and question.match_following:
            match = question.match_following
            response.match_following_data = MatchFollowingData(pairs=match.pairs)
        
        return response

    @staticmethod
    def delete_question_by_id(db: Session, question_id: int) -> bool:
        """Delete a question and its type-specific data"""
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            return False
        
        # SQLAlchemy will handle cascade deletes
        db.delete(question)
        db.commit()
        return True

class AIService:
    """Service class for AI-related operations"""
    
    @staticmethod
    async def generate_questions_with_ai(request: QuestionRequest) -> List[dict]:
        """Generate questions using AI - returns dict format for database saving"""
        if not openrouter:
            raise Exception("AI service not configured - OpenAI API key missing")
        
        prompt = AIService._create_ai_prompt(request)
        logger.info("Created AI prompt successfully")
        
        ai_response = await AIService._call_openrouter(prompt)
        if not ai_response:
            raise Exception("AI service failed to generate response")
        
        logger.info(f"AI response received: {len(ai_response)} characters")
        logger.info(f"AI response preview: {ai_response[:500]}...")
        
        questions = AIService._parse_ai_response(ai_response, request)
        logger.info(f"Parsed {len(questions)} questions from AI response")
        
        if not questions:
            raise Exception("Failed to parse AI response into valid questions")
        
        return questions

    @staticmethod
    async def _call_openrouter(prompt: str) -> str:
        """Call OpenRouter API"""
        try:
            logger.info("Calling OpenRouter API...")
            
            completion = await openrouter.chat.completions.create(
                model="openai/gpt-4o-mini", 
                messages=[
                    {"role": "system", "content": "You are an expert educational content creator. You must follow the exact format specified."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            response_text = completion.choices[0].message.content
            logger.info(f"OpenRouter response length: {len(response_text)}")
            
            return response_text
            
        except Exception as e:
            logger.error(f"OpenRouter failed: {e}")
            return None

    @staticmethod
    def _create_ai_prompt(request: QuestionRequest) -> str:
        """Create a clean, simple prompt for AI"""
        
        subject_name = request.subject.value.replace("_", " ").title()
        topic_text = f" about {request.topic}" if request.topic else ""
        
        prompt = f"""Create {request.num_questions} {request.difficulty.value} level {request.question_type.value.replace('_', ' ')} questions for {subject_name}{topic_text}.

CRITICAL: Use this EXACT format for each question:

"""

        if request.question_type == QuestionType.MULTIPLE_CHOICE:
            prompt += """TOPIC: Electric Current
SUBTOPIC: SI Units
QUESTION: What is the fundamental unit of electric current?
A) Volt
B) Watt
C) Ampere
D) Ohm
ANSWER: C
EXPLANATION: The ampere is the SI base unit for electric current.
RATING: 1100

---

"""
        
        elif request.question_type == QuestionType.TRUE_FALSE:
            prompt += """TOPIC: Energy Conservation
SUBTOPIC: Physics Laws
QUESTION: Energy can be created and destroyed according to physics laws.
ANSWER: False
EXPLANATION: According to the law of conservation of energy, energy cannot be created or destroyed.
RATING: 1250

---

"""
        
        elif request.question_type == QuestionType.FILL_IN_THE_BLANKS:
            prompt += """TOPIC: Speed of Light
SUBTOPIC: Physical Constants
QUESTION: The speed of light in vacuum is _____ meters per second.
BLANKS: 3×10⁸
EXPLANATION: The speed of light in vacuum is exactly 299,792,458 m/s.
RATING: 1350

---

"""
        
        else: 
            prompt += """TOPIC: Chemical Elements
SUBTOPIC: Periodic Table
QUESTION: Match the following chemical elements with their symbols:
PAIRS: Hydrogen=H, Oxygen=O, Carbon=C, Nitrogen=N
EXPLANATION: These are the symbols for common chemical elements.
RATING: 1200

---

"""
        
        prompt += f"""
Generate exactly {request.num_questions} questions using this EXACT format.
- Use TOPIC, SUBTOPIC, QUESTION, ANSWER/BLANKS/PAIRS, EXPLANATION, RATING
- Separate each question with "---"
- No extra text or formatting
- Make questions educational and accurate
"""
        
        return prompt

    @staticmethod
    def _parse_ai_response(ai_response: str, request: QuestionRequest) -> List[dict]:
        """Parse AI response with improved parsing logic"""
        
        logger.info(f"Parsing AI response of length {len(ai_response)}")
        
        questions = []
        question_blocks = ai_response.split("---")
        logger.info(f"Found {len(question_blocks)} potential question blocks")
        
        for i, block in enumerate(question_blocks):
            block = block.strip()
            if not block or len(block) < 30:
                logger.debug(f"Skipping block {i+1}: too short ({len(block)} chars)")
                continue
            
            logger.info(f"Parsing block {i+1}...")
            logger.debug(f"Block content: {block[:200]}...")
            
            question = AIService._parse_single_question(block, request.question_type, request)
            if question:
                questions.append(question)
                logger.info(f"Successfully parsed question {len(questions)}")
            else:
                logger.warning(f"Failed to parse block {i+1}")
        
        logger.info(f"Total questions parsed: {len(questions)}")
        return questions

    @staticmethod
    def _parse_single_question(block: str, question_type: QuestionType, request: QuestionRequest) -> Optional[dict]:
        """Parse a single question block with flexible parsing"""
        
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        # Initialize all fields
        topic = ""
        sub_topic = None
        question_text = ""
        options = []
        correct_answer = ""
        explanation = ""
        blanks = []
        match_pairs = {}
        elo_rating = 1200 
        
        for line in lines:
            line_upper = line.upper()

            def get_value(text):
                parts = text.split(":", 1)
                return parts[1].strip() if len(parts) > 1 else ""
            
            # More flexible parsing - check for various formats
            if line_upper.startswith("TOPIC:") or line_upper.startswith("Topic:"):
                topic = get_value(line)
            elif line_upper.startswith("SUBTOPIC:") or line_upper.startswith("Sub-topic:") or line_upper.startswith("SUBTOPIC:"):
                sub_topic = get_value(line)
            elif line_upper.startswith("QUESTION:") or line_upper.startswith("Question:"):
                question_text = get_value(line)
            elif line_upper.startswith("EXPLANATION:") or line_upper.startswith("Explanation:"):
                explanation = get_value(line)
            elif line_upper.startswith("RATING:") or line_upper.startswith("ELO Rating:"):
                try:
                    elo_rating = int(get_value(line))
                except ValueError:
                    elo_rating = 1200
            
            # Question type specific parsing
            elif question_type == QuestionType.MULTIPLE_CHOICE:
                if line.startswith(("A)", "B)", "C)", "D)")):
                    options.append(line)
                elif line_upper.startswith("ANSWER:") or line_upper.startswith("Correct Answer:"):
                    correct_answer = line.split(":", 1)[1].strip()
            
            elif question_type == QuestionType.TRUE_FALSE:
                if line_upper.startswith("ANSWER:") or line_upper.startswith("Answer:"):
                    correct_answer = line.split(":", 1)[1].strip()
            
            elif question_type == QuestionType.FILL_IN_THE_BLANKS:
                if line_upper.startswith("BLANKS:") or line_upper.startswith("Blanks:"):
                    blanks_text = line.split(":", 1)[1].strip()
                    blanks = [item.strip() for item in blanks_text.split(",")]
                    correct_answer = blanks_text
            
            elif question_type == QuestionType.MATCH_THE_FOLLOWING:
                if line_upper.startswith("PAIRS:") or line_upper.startswith("Match Pairs:"):
                    pairs_text = line.split(":", 1)[1].strip()
                    pairs = [pair.strip() for pair in pairs_text.split(",")]
                    for pair in pairs:
                        if "=" in pair:
                            key, value = pair.split("=", 1)
                            match_pairs[key.strip()] = value.strip()
                    correct_answer = pairs_text
        
        # Validation with detailed logging
        if not question_text:
            logger.warning(f"No question text found. Available lines: {[l[:50] for l in lines]}")
            return None
        
        if not correct_answer:
            logger.warning(f"No correct answer found for question: {question_text[:50]}...")
            return None
        
        if question_type == QuestionType.MULTIPLE_CHOICE and len(options) < 4:
            logger.warning(f"Multiple choice question missing options: found {len(options)}")
            return None
        
        if question_type == QuestionType.FILL_IN_THE_BLANKS and not blanks:
            logger.warning(f"Fill in blanks question missing blanks")
            return None
        
        if question_type == QuestionType.MATCH_THE_FOLLOWING and len(match_pairs) < 3:
            logger.warning(f"Match question missing pairs: found {len(match_pairs)}")
            return None
        
        if not topic:
            topic = request.subject.value.replace("_", " ").title()
        
        if not sub_topic and request.sub_topic:
            sub_topic = request.sub_topic
        
        elo_rating = max(800, min(2400, elo_rating))
        elo_range = (elo_rating - 200, elo_rating + 200)
        
        # Return as dict for database saving
        return {
            'topic': topic,
            'sub_topic': sub_topic,
            'question_text': question_text,
            'options': options if options else None,
            'correct_answer': correct_answer,
            'explanation': explanation if explanation else None,
            'blanks': blanks if blanks else None,
            'match_pairs': match_pairs if match_pairs else None,
            'elo_rating': elo_rating,
            'elo_range': elo_range,
            'state': request.state
        }