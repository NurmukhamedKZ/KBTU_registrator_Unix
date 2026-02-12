"""
AI Helper Module for answering test questions using Google Gemini.
"""

import os
import time
import logging
from langchain_openai import ChatOpenAI
from typing import Optional, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 2  # seconds
MAX_RETRY_DELAY = 30  # seconds

class LLMOutput(BaseModel):
    explanation: str
    correct_answer_number: Literal[1,2,3,4] = Field("Ответ в виде номера вопроса")


class AIHelper:
    """Helper class for AI-powered test question answering using Google Gemini."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """
        Initialize the AI helper with Gemini API.
        
        Args:
            api_key: Gemini API key. If not provided, reads from OPENAI_API_KEY env var.
            model: Model name to use (default: gemini-1.5-flash)
        """
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found. Please set it in .env file.")
        
        self.llm = ChatOpenAI(model=model, api_key=self.api_key)
        self.llm_with_structured_output = self.llm.with_structured_output(LLMOutput)
        self.model_name = model
        logger.info(f"AI Helper initialized with model: {model}")
    
    def _call_with_retry(self, prompt: str) -> LLMOutput:
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
                response = self.llm_with_structured_output.invoke(prompt)
                return response
                
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
        options_text = "\n".join([f"Option #{i}: {opt}" for i, opt in enumerate(options, start=1)])
        
        prompt = f"""Ты эксперт в тестах. твоя задача дать один верный ответ на вопрос из 4 возможных ответов

ВАЖНО: Только один вариант правильный

Вопрос: {question}

Варианты ответов:
{options_text}
"""

        # Call AI with retry logic
        result = self._call_with_retry(prompt)
        
        if result is None:
            logger.error("AI unavailable after retries. Defaulting to first option.")
            return 0
        
        # Extract the number from response
        # Handle cases like "1", "1.", "Answer: 1", etc.
        return result.correct_answer_number - 1
        
        # # Fallback: try to find number in response
        # import re
        # numbers = re.findall(r'\d+', result)
        # if numbers:
        #     answer_num = int(numbers[0])
        #     if 1 <= answer_num <= len(options):
        #         logger.info(f"AI selected answer {answer_num} (from regex): {options[answer_num-1][:50]}...")
        #         return answer_num - 1
        
        # logger.warning(f"Could not parse AI response: {result}. Defaulting to first option.")
        # return 0

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
