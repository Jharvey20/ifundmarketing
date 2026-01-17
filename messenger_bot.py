import os
import requests

from flask import request
from sqlalchemy import text, func
from werkzeug.security import check_password_hash

from app import db
from models import Task
from sqlalchemy import func
from app import db
import random
import time
import threading

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

def send_delayed(psid, message, delay):
    time.sleep(delay)
    send_message(psid, message)

def send_quick_replies(psid, text, replies):
    payload = {
        "recipient": {"id": psid},
        "message": {
            "text": text,
            "quick_replies": [
                {
                    "content_type": "text",
                    "title": r["title"],
                    "payload": r["payload"]
                } for r in replies
            ]
        }
    }
    requests.post(
        f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
        json=payload
    )

# =====================
# SEND MESSAGE FUNCTION
# =====================

def get_user_id_by_psid(psid):
    result = db.session.execute(
        text("""
            SELECT id FROM users
            WHERE messenger_id = :mid
              AND messenger_active = TRUE
        """),
        {"mid": f"IFD-{psid}"}
    ).fetchone()

    return result[0] if result else None

def verify_user(psid, username, password):
    result = db.session.execute(
        text("""
            SELECT id, password_hash
            FROM users
            WHERE username = :username
            AND messenger_active = FALSE
        """),
        {"username": username.strip()}
    ).fetchone()

    if not result:
        send_message(psid, "❌ Account not found or already linked.")
        return

    user_id, password_hash = result

    if not check_password_hash(password_hash, password.strip()):
        send_message(psid, "❌ Invalid password.")
        return

    messenger_code = f"IFD-{psid}"

    db.session.execute(
        text("""
            UPDATE users
            SET messenger_id = :mid,
                messenger_active = TRUE
            WHERE id = :uid
        """),
        {"mid": messenger_code, "uid": user_id}
    )
    db.session.commit()

    send_message(
        psid,
        "✅ Account verified!\n\n"
        f"Your Messenger Activation ID:\n{messenger_code}\n\n"
        "Paste this on the website under:\n'Earn with Messenger'"
    )


def send_messenger_dashboard(psid):
    url = "https://graph.facebook.com/v18.0/me/messages"
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "generic",
                    "elements": [
                        {
                            "title": "iFund Marketing Dashboard",
                            "subtitle": "Choose an option",
                            "buttons": [
                                {
                                    "type": "postback",
                                    "title": "💰 Balance",
                                    "payload": "BALANCE"
                                },
                                {
                                    "type": "postback",
                                    "title": "🧮 Do Tasks",
                                    "payload": "TASKS"
                                },
                                {
                                    "type": "postback",
                                    "title": "👤 My Info",
                                    "payload": "INFO"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json=payload
    )

def send_message(psid, text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}

    requests.post(url, params=params, headers=headers, json=payload)

def can_do_task(user_id):
    """
    10–15 seconds cooldown per user (Messenger)
    """
    result = db.session.execute(
        text("""
            SELECT last_task_at
            FROM messenger_task_logs
            WHERE user_id = :uid
        """),
        {"uid": user_id}
    ).fetchone()

    if not result or not result[0]:
        return True

    last_time = result[0]
    return datetime.utcnow() - last_time >= timedelta(seconds=10)

def update_task_log(user_id):
    db.session.execute(
        text("""
            INSERT INTO messenger_task_logs (user_id, last_task_at)
            VALUES (:uid, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET last_task_at = NOW()
        """),
        {"uid": user_id}
    )
    db.session.commit()

def generate_math_task():
    op = random.choice(["+", "-", "*", "/"])

    if op in ["+", "-"]:
        a = random.randint(10000, 999999)
        b = random.randint(10000, 999999)
        answer = a + b if op == "+" else a - b

    elif op == "*":
        a = random.randint(100, 9999)
        b = random.randint(10, 999)
        answer = a * b

    else:  # division – whole number only
        answer = random.randint(10, 9999)
        b = random.randint(2, 99)
        a = answer * b

    question = f"🧮 MATH TASK\n\nSolve:\n{a} {op} {b}"
    return question, str(answer)

COLOR_POOL = [
    "red", "blue", "green", "yellow", "orange",
    "purple", "pink", "brown", "black", "white",
    "gray", "cyan", "magenta", "lime", "teal"
]

def generate_color_memory_task():
    colors = [random.choice(COLOR_POOL) for _ in range(25)]
    index = random.randint(1, 25)  # 1-based for user
    correct_answer = colors[index - 1]

    color_text = ", ".join(colors)

    question = (
        f"🎨 COLOR MEMORY TASK\n\n"
        f"{color_text}\n\n"
        f"❓ What is the {index}th color?"
    )

    return question, correct_answer

def run_task_flow(psid, user_id):
    user = User.query.get(user_id)
    username = user.username

    # STEP 1
    send_message(psid, "⏳ Please wait a moment...")
    time.sleep(10)

    # STEP 2
    send_message(psid, "⚙️ Generating task...")
    time.sleep(10)

    # STEP 3 – GENERATE TASK
    question, correct_answer = generate_color_memory_task()
    save_state(psid, f"task_answer:{correct_answer}")

    send_message(
        psid,
        f"🧠 Task generated!\n\n"
        f"Here's your question, {username}:\n\n"
        f"{question}"
    )

    time.sleep(5)

#==
#Incoming Messages
#==

def handle_webhook(data):
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            psid = event["sender"]["id"]

            # =========================
            # POSTBACK HANDLER
            # =========================
            if "postback" in event:
                payload = event["postback"]["payload"]

                # =================
                # BALANCE BUTTON
                # =================
                if payload == "BALANCE":
                    send_message(psid, "💰 Balance feature working.")
                    return

                # =================
                # TASKS BUTTON
                # =================
                elif payload == "TASKS":
                    user_id = get_user_id_by_psid(psid)

                    if not user_id:
                        send_message(psid, "❌ Please LOGIN first.")
                        return

                    if not can_do_task(user_id):
                        send_message(psid, "⏳ Please wait 10–15 seconds before next task.")
                        return

                    # RUN AS BACKGROUND THREAD
                    threading.Thread(
                        target=run_task_flow,
                        args=(psid, user_id)
                    ).start()

                    return

                    # 🔀 RANDOM TASK TYPE
                    task_type = random.choice(["color", "math"])

                    if task_type == "color":
                        question, correct_answer = generate_color_memory_task()
                    else:
                        question, correct_answer = generate_math_task()

                    # save expected answer
                    save_state(psid, f"task_answer:{correct_answer}")

                    send_message(psid, question)
                    return

                # =================
                # INFO BUTTON
                # =================
                elif payload == "INFO":
                    send_message(
                        psid,
                        "ℹ️ Account Info\n\n"
                        "If Messenger becomes inactive,\n"
                        "you can re-activate using your IFD\n"
                        "from the website."
                    )
                    return

            # =========================
            # TEXT MESSAGE HANDLER
            # =========================
            if "message" in event and "text" in event["message"]:
                text_msg = event["message"]["text"].strip()

                # GREETING
                if text_msg.lower() in ["hi", "hello", "start"]:
                    send_message(
                        psid,
                        "👋 Hi! Welcome to iFund Marketing Messenger Bot!\n\n"
                        "Tap TASKS to earn or type LOGIN to connect your account."
                    )
                    return

                # LOGIN FLOW
                if text_msg.lower() == "login":
                    send_message(psid, "Please enter your USERNAME:")
                    save_state(psid, "awaiting_username")
                    return
                # ALL OTHER STATES
                process_state(psid, text_msg)
                return
# =====================
#STATEHANDLING
#=====================
	def save_state(psid, state):
    db.session.execute(
        text("""
            INSERT INTO messenger_states (psid, state)
            VALUES (:psid, :state)
            ON CONFLICT (psid)
            DO UPDATE SET state = :state"""),
        {"psid": psid, "state": state}
    )
    db.session.commit()


def get_state(psid):
    result = db.session.execute(
        text("SELECT state FROM messenger_states WHERE psid = :psid"),
        {"psid": psid}
    ).fetchone()
    return result[0] if result else None


def process_state(psid, message):
    state = get_state(psid)

    # =========================
    # TASK ANSWER HANDLER
    # =========================
    if state and state.startswith("task_answer:"):
        correct_answer = state.split(":", 1)[1]

        user_id = get_user_id_by_psid(psid)
        if not user_id:
            send_message(psid, "❌ Session expired. Please LOGIN again.")
            save_state(psid, None)
            return

        # Simulated processing flow
        send_message(psid, "🔍 Checking answer...")
        time.sleep(10)

        send_message(psid, "📤 Submitting...")
        time.sleep(3)

        send_message(psid, "✅ Submitted")
        time.sleep(2)

        # CHECK ANSWER (case-insensitive)
        if message.strip().lower() == correct_answer.lower():
            reward = get_random_messenger_reward()  # ₱0.0125–₱0.030
            user = User.query.get(user_id)

            user.cash_balance += reward
            update_task_log(user_id, "messenger")
            db.session.commit()

            send_message(
                psid,
                f"🎉 Correct!\n\n"
                f"💰 You received ₱{reward:.4f}\n"
                f"📊 Total Balance: ₱{user.cash_balance:.4f}"
            )
        else:
            send_message(psid, "❌ Wrong answer.")

        # Quick Replies (ManyChat-style)
        send_quick_replies(
            psid,
            "What would you like to do next?",
            [
                {"title": "Next", "payload": "TASKS"},
                {"title": "Dashboard", "payload": "DASHBOARD"},
            ],
        )

        save_state(psid, None)
        return

    # =========================
    # LOGIN FLOW
    # =========================
    if state == "awaiting_username":
        save_state(psid, f"awaiting_password|{message}")
        send_message(psid, "Please enter your PASSWORD:")
        return

    elif state and state.startswith("awaiting_password"):
        username = state.split("|", 1)[1]
        password = message
        verify_user(psid, username, password)
        save_state(psid, None)
        return

    # =========================
    # FALLBACK
    # =========================
    send_message(psid, "❓ Type LOGIN to start.")

# =====================
# VERIFY USER
# =====================
def verify_user(psid, username, password):
    result = db.session.execute(
        text("""
            SELECT id FROM users
            WHERE username = :username
              AND messenger_active = FALSE
        """),
        {"username": username}
    ).fetchone()

    if not result:
        send_message(psid, "❌ Account not found or already linked.")
        return

    messenger_code = f"IFD-{psid}"

    db.session.execute(
        text("""
            UPDATE users
            SET messenger_id = :mid,
                messenger_active = TRUE
            WHERE username = :username
        """),
        {"mid": messenger_code, "username": username}
    )
    db.session.commit()

    send_message(
        psid,
        f"✅ Account verified!\n\n"
        f"Your Messenger Activation ID:\n{messenger_code}\n\n"
        "Paste this on the website under:\nEarn with Messenger"
    )

