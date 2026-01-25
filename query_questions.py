
import os
import argparse
from dotenv import load_dotenv
from db_models import DatabaseManager

# Load environment variables
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Query stored questions from the database")
    parser.add_argument("--user", type=str, help="Filter by user email")
    parser.add_argument("--limit", type=int, default=10, help="Number of questions to show")
    parser.add_argument("--offset", type=int, default=0, help="Number of questions to skip")
    
    args = parser.parse_args()
    
    # Get database URL from env
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ Error: DATABASE_URL not found in .env")
        return
        
    try:
        manager = DatabaseManager(db_url)
        
        # Determine email to query
        email = args.user or os.getenv("UNIX_EMAIL")
        if not email:
            print("❌ Error: No user email specified. Use --user or set UNIX_EMAIL in .env")
            return
            
        print(f"\nQuerying questions for: {email}")
        
        # Get count
        count = manager.get_question_count(email)
        print(f"Total questions found: {count}")
        
        if count == 0:
            return

        # Get questions
        questions = manager.get_user_questions(email, limit=args.limit, offset=args.offset)
        
        print(f"\nShowing {len(questions)} most recent questions:\n")
        print("-" * 60)
        
        for i, q in enumerate(questions):
            print(f"Question #{args.offset + i + 1} (ID: {q['id']})")
            print(f"Lesson: {q['lesson_name'] or 'Unknown'}")
            print(f"Text: {q['question_text']}")
            print("\nAnswers:")
            
            for ans in q['answers']:
                mark = "[x]" if ans['is_selected'] else "[ ]"
                print(f"  {mark} {ans['text']}")
                
            print("-" * 60)
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
