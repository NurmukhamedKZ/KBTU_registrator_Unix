"""
AI Helper Module for answering test questions using Google Gemini.
"""

import os
import time
import logging
from google import genai
from typing import Optional

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2  # seconds
MAX_RETRY_DELAY = 30  # seconds


class AIHelper:
    """Helper class for AI-powered test question answering using Google Gemini."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3-flash-preview"):
        """
        Initialize the AI helper with Gemini API.
        
        Args:
            api_key: Gemini API key. If not provided, reads from GEMINI_API_KEY env var.
            model: Model name to use (default: gemini-1.5-flash)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found. Please set it in .env file.")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model
        logger.info(f"AI Helper initialized with model: {model}")
    
    def _call_with_retry(self, prompt: str) -> Optional[str]:
        """
        Call the AI model with retry logic for handling temporary failures.
        
        Args:
            prompt: The prompt to send to the model
            
        Returns:
            The response text or None if all retries failed
        """
        last_error = None
        retry_delay = INITIAL_RETRY_DELAY
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.models.generate_content(model=self.model_name, contents=prompt)
                return response.text.strip()
                
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check if it's a retryable error (503, 429, etc.)
                is_retryable = any(code in error_str for code in ['503', '429', 'overloaded', 'UNAVAILABLE', 'rate limit'])
                
                if is_retryable and attempt < MAX_RETRIES - 1:
                    logger.warning(f"AI request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    # Exponential backoff with jitter
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                else:
                    # Non-retryable error or last attempt
                    break
        
        logger.error(f"AI request failed after {MAX_RETRIES} attempts: {last_error}")
        return None
    
    def answer_question(self, question: str, options: list[str], context: str = "") -> int:
        """
        Analyze a question and return the index of the correct answer.
        
        Args:
            question: The question text
            options: List of answer options
            context: Optional context from the lecture
            
        Returns:
            Index of the correct answer (0-based)
        """
        # Format options for the prompt
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        
        prompt = f"""Ты эксперт по социально-политическим наукам. Тебе дан вопрос из университетского теста.
Проанализируй вопрос и варианты ответов, затем выбери ТОЛЬКО ОДИН правильный ответ.

ВАЖНО: В ответе напиши ТОЛЬКО номер правильного ответа (1, 2, 3, 4 или 5). Ничего больше.

Вопрос: {question}

Варианты ответов:
{options_text}

{f"Контекст из лекции: {context}" if context else ""}

Правильный ответ (только номер):"""

        # Call AI with retry logic
        answer_text = self._call_with_retry(prompt)
        
        if answer_text is None:
            logger.error("AI unavailable after retries. Defaulting to first option.")
            return 0
        
        # Extract the number from response
        # Handle cases like "1", "1.", "Answer: 1", etc.
        for char in answer_text:
            if char.isdigit():
                answer_num = int(char)
                if 1 <= answer_num <= len(options):
                    logger.info(f"AI selected answer {answer_num}: {options[answer_num-1][:50]}...")
                    return answer_num - 1  # Convert to 0-based index
        
        # Fallback: try to find number in response
        import re
        numbers = re.findall(r'\d+', answer_text)
        if numbers:
            answer_num = int(numbers[0])
            if 1 <= answer_num <= len(options):
                logger.info(f"AI selected answer {answer_num} (from regex): {options[answer_num-1][:50]}...")
                return answer_num - 1
        
        logger.warning(f"Could not parse AI response: {answer_text}. Defaulting to first option.")
        return 0
    
    def answer_multiple_choice(self, question: str, options: list[str], context: str = "") -> list[int]:
        """
        For multiple-choice questions where more than one answer can be correct.
        
        Args:
            question: The question text
            options: List of answer options
            context: Optional context from the lecture
            
        Returns:
            List of indices of correct answers (0-based)
        """
        options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
        
        prompt = f"""Ты эксперт по социально-политическим наукам. Тебе дан вопрос из университетского теста.
Это вопрос с НЕСКОЛЬКИМИ правильными ответами.

ВАЖНО: В ответе напиши ТОЛЬКО номера правильных ответов через запятую (например: 1, 3, 4). Ничего больше.

Вопрос: {question}

Варианты ответов:
{options_text}

{f"Контекст из лекции: {context}" if context else ""}

Правильные ответы (только номера через запятую):"""

        # Call AI with retry logic
        answer_text = self._call_with_retry(prompt)
        
        if answer_text is None:
            logger.error("AI unavailable after retries. Defaulting to first option.")
            return [0]
        
        import re
        numbers = re.findall(r'\d+', answer_text)
        result = []
        for num_str in numbers:
            num = int(num_str)
            if 1 <= num <= len(options):
                result.append(num - 1)  # Convert to 0-based index
        
        if result:
            logger.info(f"AI selected answers: {[options[i][:30] for i in result]}")
            return result
        
        logger.warning(f"Could not parse AI response: {answer_text}. Defaulting to first option.")
        return [0]


def test_ai_helper():
    """Test the AI helper with a sample question."""
    from dotenv import load_dotenv
    load_dotenv()
    
    helper = AIHelper()
    
    # Test single choice
    question = "Что изучает социология?"
    options = [
        "Поведение животных",
        "Общество и социальные отношения",
        "Химические реакции",
        "Звезды и галактики"
    ]
    
    answer_idx = helper.answer_question(question, options)
    print(f"Question: {question}")
    print(f"AI Answer: {options[answer_idx]}")
    print(f"Expected: Общество и социальные отношения")
    

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_ai_helper()
