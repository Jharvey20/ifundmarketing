from app import app, db
from models import Task

math_tasks = [
    Task(
        task_type="math",
        question="(48392 + 17485) × 3 − 12947",
        answer="183596",
        reward=0.04
    ),
    Task(
        task_type="math",
        question="(92841 − 34729) ÷ 2 + 9182",
        answer="38156",
        reward=0.04
    )
]

with app.app_context():
    db.session.add_all(math_tasks)
    db.session.commit()

print("🧮 Math tasks seeded")
