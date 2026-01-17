import os
import requests

from flask import request
from sqlalchemy import text
from werkzeug.security import check_password_hash

from app import db

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

# =====================
# SEND MESSAGE FUNCTION
# =====================

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


# =====================
# HANDLE INCOMING EVENTS
# =====================
def handle_webhook(data):
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            psid = event["sender"]["id"]

            if "message" not in event:
                continue

            if "text" not in event["message"]:
                continue

            text_msg = event["message"]["text"].strip().lower()

            # ---- START FLOW ----
            if text_msg in ["hi", "hello", "start"]:
                send_message(
                    psid,
                    "👋 Hi! Welcome to iFund Marketing Messenger Bot!\n\n"
                    "Type LOGIN to connect your account."
                )

            elif text_msg == "login":
                send_message(psid, "Please enter your USERNAME:")

                # save state (simple version for Phase 1.1)
                save_state(psid, "awaiting_username")

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

