import os
import requests

from flask import request
from sqlalchemy import text
from werkzeug.security import check_password_hash

from app import db
from models import Task
from sqlalchemy import func

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

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

# =====================
# HANDLE INCOMING EVENTS
# =====================
def handle_webhook(data):
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            psid = event["sender"]["id"]

            # =========================
            # BUTTON / POSTBACK HANDLER
            # =========================
            if "postback" in event:
                payload = event["postback"]["payload"]

                # 👉 BALANCE BUTTON
                if payload == "BALANCE":
                    send_message(psid, "💰 Balance feature working.")

                # 👉 TASKS BUTTON
                elif payload == "TASKS":
                    user_id = get_user_id_by_psid(psid)
                    if not user_id:
                        send_message(psid, "❌ Please LOGIN first.")
                        return

                    if not can_do_task(user_id):
                        send_message(psid, "⏳ Please wait 10–15 seconds before next task.")
                        return

                    task = db.session.query(Task).order_by(func.random()).first()
                    if not task:
                        send_message(psid, "⚠️ No tasks available right now.")
                        return

                    save_state(psid, f"task:{task.id}")
                    send_message(psid, f"🧠 Task:\n{task.question}")

                # 👉 INFO BUTTON
                elif payload == "INFO":
                    send_message(
                        psid,
                        "ℹ️ Account Info\n\n"
                        "If Messenger becomes inactive,\n"
                        "you can re-activate using your IFD\n"
                        "from the website."
                    )

                return  # ⛔ IMPORTANT: stop here after postback

            # =========================
            # TEXT MESSAGE HANDLER
            # =========================
            if "message" in event and "text" in event["message"]:
                text_msg = event["message"]["text"].strip().lower()

                # START / HI
                if text_msg in ["hi", "hello", "start"]:
                    send_message(
                        psid,
                        "👋 Hi! Welcome to iFund Marketing Messenger Bot!\n\n"
                        "Type LOGIN to connect your account."
                    )

                # LOGIN FLOW
                elif text_msg == "login":
                    send_message(psid, "Please enter your USERNAME:")
                    save_state(psid, "awaiting_username")

                # ALL OTHER STATES (TASK ANSWER, PASSWORD, ETC)
                else:
                    process_state(psid, text_msg)

# =====================
# STATE HANDLING
# =====================
def save_state(psid, state):
    db.session.execute(
        text("""
            INSERT INTO messenger_states (psid, state)
            VALUES (:psid, :state)
            ON CONFLICT (psid)
            DO UPDATE SET state = :state
        """),
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

    if state == "awaiting_username":
        save_state(psid, f"awaiting_password|{message}")
        send_message(psid, "Please enter your PASSWORD:")

    elif state and state.startswith("awaiting_password"):
        username = state.split("|")[1]
        password = message
        verify_user(psid, username, password)

    else:
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

