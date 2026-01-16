import random
import string
from datetime import datetime

from app import app
from models import db, ActivationCode


def generate_code():
    return "ACT-" + ''.join(
        random.choices(string.ascii_uppercase + string.digits, k=8)
    )


def generate_codes(quantity):
    with app.app_context():
        created = 0

        while created < quantity:
            code = generate_code()

            # CHECK KUNG MAY KAPAREHO
            exists = ActivationCode.query.filter_by(code=code).first()
            if exists:
                continue

            new_code = ActivationCode(
                code=code,
                is_used=0,
                used_by=None,
                used_at=None
            )

            db.session.add(new_code)
            db.session.commit()

            print(f"[OK] Generated: {code}")
            created += 1


if __name__ == "__main__":
    print("=== ADMIN ACTIVATION CODE GENERATOR ===")
    qty = int(input("How many codes to generate? "))
    generate_codes(qty)
    print("DONE.")
