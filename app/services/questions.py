import csv
import io
from typing import List


def build_questions_csv(questions: List[dict]) -> str:
    """Build UTF-8 CSV content from question dictionaries."""
    max_answers = max((len(question.get("answers", [])) for question in questions), default=0)

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    header = ["id", "question_text", "lesson_name", "lesson_url", "created_at", "user_email"]
    header += [f"answer_{index + 1}" for index in range(max_answers)]
    header.append("selected_answer")
    writer.writerow(header)

    for question in questions:
        answers = question.get("answers", [])
        selected = next((answer["text"] for answer in answers if answer.get("is_selected")), "")
        row = [
            question.get("id"),
            question.get("question_text", ""),
            question.get("lesson_name", ""),
            question.get("lesson_url", ""),
            question.get("created_at", ""),
            question.get("user_email", ""),
        ]
        for index in range(max_answers):
            row.append(answers[index]["text"] if index < len(answers) else "")
        row.append(selected)
        writer.writerow(row)

    buffer.seek(0)
    return "\ufeff" + buffer.getvalue()
