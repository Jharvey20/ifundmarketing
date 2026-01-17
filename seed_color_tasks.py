from app import app, db
from models import Task

color_tasks = [
    Task(
        task_type="color",
        question=(
            "Red, Blue, Green, Yellow, Purple,\n"
            "Orange, Pink, Brown, Black, White,\n"
            "Red, Blue, Green, Yellow, Purple,\n"
            "Orange, Pink, Brown, Black, White,\n"
            "Red, Blue, Green, Yellow, Purple\n\n"
            "❓ What is the 20th color?"
        ),
        answer="White",
        reward=0.03
    )
]

with app.app_context():
    db.session.add_all(color_tasks)
    db.session.commit()

print("🎨 Color tasks seeded")
