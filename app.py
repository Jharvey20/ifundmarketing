from flask import Flask, render_template, request, redirect, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, ActivationCode, Withdrawal, AdminFund
import random
import time
import os
import requests
from functools import wraps
from flask import session, redirect, url_for
from sqlalchemy import text
from flask import Flask
from models import db

#==========
# CREATE FLASK APP
# ========================
app = Flask(__name__)
db.init_app(app)

def give_task_reward(user):
    earned = random.randint(1, 2)
    user.points += earned
    return earned

# SECRET KEY (REQUIRED FOR SESSION)
app.secret_key = os.environ["SECRET_KEY"]

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))

        user = User.query.get(session["user"])
        if not user or not user.is_admin:
            return redirect(url_for("dashboard"))

        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def can_do_task(user_id):
    log = TaskLog.query.filter_by(user_id=user_id).first()
    if not log:
        return True

    return (datetime.utcnow() - log.last_task_at).seconds >= 15

def update_task_log(user_id, platform):
    log = TaskLog.query.filter_by(user_id=user_id).first()
    if not log:
        log = TaskLog(user_id=user_id, platform=platform)
        db.session.add(log)

    log.last_task_at = datetime.utcnow()
    db.session.commit()

# ======================
# CONFIGURATION
# ======================
import os

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is not set")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()

def send_message(psid, text):
    url = "https://graph.facebook.com/v18.0/me/messages"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    requests.post(url, headers=headers, params=params, json=payload)

# ==========================
# ADMIN ROUTES
# ==========================

from sqlalchemy import func

@app.route("/admin")
@admin_required
def admin_dashboard():

    # ==========================
    # GET ALL USERS
    # ==========================
    users = User.query.all()

    # ==========================
    # TOTAL PAYOUTS PER USER
    # ==========================
    payout_map = dict(
        db.session.query(
            Withdrawal.user_id,
            func.sum(Withdrawal.amount)
        )
        .filter(Withdrawal.status == "approved")
        .group_by(Withdrawal.user_id)
        .all()
    )

    # ==========================
    # LEADERBOARD (TOP EARNERS)
    # ==========================
    leaderboard = []

    for u in users:
        total_payouts = payout_map.get(u.user_id, 0) or 0

        leaderboard.append({
            "username": u.username,
            "balance": u.cash_balance,
            "referrals": u.referrals,
            "total_payouts": total_payouts,
            # rank is based on lifetime earnings
            "rank_score": u.cash_balance + total_payouts
        })

    # SORT HIGHEST EARNINGS FIRST
    leaderboard.sort(
        key=lambda x: x["rank_score"],
        reverse=True
    )

    # ASSIGN RANK NUMBERS
    for i, u in enumerate(leaderboard, start=1):
        u["rank"] = i

    # ==========================
    # DASHBOARD METRICS
    # ==========================

    # Member Earnings = sum of all user balances
    member_earnings = sum(u["balance"] for u in leaderboard)

    # Total Cashouts = sum of approved payouts
    total_cashouts = sum(u["total_payouts"] for u in leaderboard)

    total_funds = db.session.query(
        func.coalesce(func.sum(AdminFund.amount), 0)
    ).scalar()

    # ===== WARNING CHECK =====
    funds_warning = total_funds < member_earnings

    return render_template(
        "admin/dashboard.html",
        total_cashouts=total_cashouts,
        total_users=len(users),
        leaderboard=leaderboard,
        total_funds=total_funds,
        member_earnings=member_earnings,
        funds_warning=funds_warning,
    )

@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():
    withdrawals = Withdrawal.query.order_by(
        Withdrawal.requested_at.desc()
    ).all()

    return render_template(
        "admin/withdrawals.html",
        withdrawals=withdrawals
    )

@app.route("/admin/withdraw/<int:w_id>/<action>")
@admin_required
def process_withdraw(w_id, action):

    w = db.session.get(Withdrawal, w_id)
    if not w or w.status != "pending":
        return redirect("/admin/withdrawals")

    user = User.query.filter_by(user_id=w.user_id).first()

    if action == "approve":
        w.status = "approved"

    # ===== AUTO-DEDUCT FUNDS =====
        fund = AdminFund(
            amount=w.amount,
            type="subtract",
            note=f"Approved withdrawal for {w.user_id}"
)
        db.session.add(fund)
 
    elif action == "reject":
        user.cash_balance += w.amount
        w.status = "rejected"

    w.processed_at = db.func.now()
    db.session.commit()

    return redirect("/admin/withdrawals")


@app.route("/admin/generate-codes", methods=["POST"])
@admin_required
def generate_codes():
    
    count = int(request.form["count"])
    codes = []

    for _ in range(count):
        code = f"ACT-{random.randint(100000,999999)}"
        db.session.add(ActivationCode(code=code))
        codes.append(code)

    db.session.commit()
    session["generated_codes"] = codes

    return redirect("/admin")

@app.route("/admin/add-funds", methods=["GET", "POST"])
@admin_required
def add_funds():
    
    if request.method == "POST":
        amount = float(request.form["amount"])
        note = request.form.get("note", "Manual fund update")

        fund = AdminFund(
            amount=amount,
            type="add",
            note=note
        )
        db.session.add(fund)
        db.session.commit()

        flash("Funds added successfully", "success")
        return redirect("/admin")

    return render_template("admin/add_funds.html")

# ======================
# ROUTES
# ======================

@app.route("/")
def home():
    return redirect("/signup")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    # STORE REFERRER ON FIRST VISIT
    if request.method == "GET":
        ref = request.args.get("ref")
        if ref:
            session["referrer"] = ref

    if request.method == "POST":
        code_input = request.form["activation_code"].strip()

        # CHECK ACTIVATION CODE
        code = ActivationCode.query.filter_by(
            code=code_input,
            is_used=0
        ).first()

        if not code:
            flash("Invalid or already used activation code.")
            return redirect("/signup")

        # CREATE USER
        user_id = f"USR-{random.randint(10000,99999)}"
        hashed_pw = generate_password_hash(request.form["password"])

        new_user = User(
            user_id=user_id,
            username=request.form["username"],
            full_name=request.form["full_name"],
            email=request.form["email"],
            password_hash=hashed_pw,
            activation_code=code.code
        )

        db.session.add(new_user)

        # LOCK ACTIVATION CODE
        code.is_used = 1
        code.used_by = user_id

        # REFERRAL BONUS
        referrer_id = session.get("referrer")
        if referrer_id:
            inviter = User.query.filter_by(user_id=referrer_id).first()

            # ❌ PREVENT SELF-REFERRAL
            if inviter and inviter.user_id != user_id:
                inviter.referrals += 1
                inviter.referral_balance += 50.0
                inviter.cash_balance += 50.0

        db.session.commit()

        # CLEAR REFERRER SESSION
        session.pop("referrer", None)

        # LOGIN USER
        session["user"] = user_id
        return redirect("/dashboard")

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("User not found.")
            return redirect("/login")

        if not check_password_hash(user.password_hash, password):
            flash("Wrong password", "error")
            return redirect("/login")

        session.clear()
        session["user"] = user.id   # INTEGER
        flash("Login successful!", "success")
        return redirect("/dashboard")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/signup")

    user = User.query.get(session["user"])
    return render_template("dashboard.html", user=user)

@app.route("/referral")
def referral():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])
    return render_template("referral.html", user=user)


@app.route("/account")
def account():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])
    return render_template("account.html", user=user)

def generate_hard_task():
    task_type = random.choice([
        "counting",
        "big_add",
        "big_sub",
        "multiply",
        "divide",
        "word",
        "logic"
    ])

    # 1️⃣ COUNTING / CAPTCHA
    if task_type == "counting":
        a1 = random.randint(1, 9)
        a2 = random.randint(1, 9)
        question = (
            f"There are {a1} apples, 2 bananas, "
            f"and {a2} apples again. "
            f"How many apples are there?"
        )
        answer = a1 + a2

    # 2️⃣ BIG ADDITION
    elif task_type == "big_add":
        a = random.randint(10000, 999999)
        b = random.randint(10000, 999999)
        question = f"{a} + {b}"
        answer = a + b

    # 3️⃣ BIG SUBTRACTION
    elif task_type == "big_sub":
        a = random.randint(100000, 999999)
        b = random.randint(10000, a)
        question = f"{a} - {b}"
        answer = a - b

    # 4️⃣ MULTIPLICATION
    elif task_type == "multiply":
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        question = f"{a} × {b}"
        answer = a * b

    # 5️⃣ DIVISION (CLEAN)
    elif task_type == "divide":
        b = random.randint(2, 20)
        answer = random.randint(10, 500)
        a = b * answer
        question = f"{a} ÷ {b}"

    # 6️⃣ WORD PROBLEM
    elif task_type == "word":
        box = random.randint(5, 20)
        per_box = random.randint(50, 200)
        question = (
            f"A warehouse has {box} boxes. "
            f"Each box contains {per_box} items. "
            f"How many items are there in total?"
        )
        answer = box * per_box

    # 7️⃣ LOGIC CAPTCHA
    else:
        nums = random.sample(range(1, 30), 6)
        question = (
            f"Count the even numbers only: "
            f"{', '.join(map(str, nums))}"
        )
        answer = len([n for n in nums if n % 2 == 0])

    return question, answer

def generate_color_task():
    colors = [
        "red", "blue", "green", "yellow", "orange",
        "purple", "pink", "brown", "black", "white",
        "gray", "cyan", "magenta", "lime", "teal"
    ]

    sequence = random.sample(colors, 6)
    index = random.randint(1, 6)

    question = (
        f"Memorize the colors:\n"
        f"{', '.join(sequence)}\n\n"
        f"What is the {index}th color?"
    )

    answer = sequence[index - 1]
    return question, answer

import random

@app.route("/task", methods=["GET", "POST"])
def task():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])

    COOLDOWN = 30
    now = int(time.time())
    last_time = session.get("last_task_time", 0)
    remaining = COOLDOWN - (now - last_time)

    # =========================
    # SUBMIT ANSWER
    # =========================
    if request.method == "POST":

        if remaining > 0:
            flash("Please wait 30 seconds before next task", "info")
            return redirect("/task")

        correct = session.get("correct_answer")
        user_answer = request.form.get("answer", "").strip()

        if user_answer.isdigit() and int(user_answer) == correct:
            earned = random.randint(1, 2)
            user.points += earned
            flash(f"Correct! +{earned} points 🎉")
        else:
            flash("Wrong answer ❌")

        session["last_task_time"] = now
        db.session.commit()

        return redirect("/task")

    # =========================
    # SHOW TASK OR COOLDOWN
    # =========================
    if remaining > 0:
        return render_template(
            "task.html",
            user=user,
            question=None,
            remaining=remaining
        )

    question, answer = generate_hard_task()
    session["correct_answer"] = answer

    return render_template(
        "task.html",
        user=user,
        question=question,
        remaining=0
    )

@app.route("/color-task", methods=["GET", "POST"])
def color_task():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])

    COOLDOWN = 30
    now = int(time.time())
    last_time = session.get("last_color_task_time", 0)
    remaining = COOLDOWN - (now - last_time)

    # =========================
    # SUBMIT ANSWER
    # =========================
    if request.method == "POST":
        if remaining > 0:
            flash("Please wait 30 seconds before next task", "info")
            return redirect("/color-task")

        correct = session.get("color_correct")
        user_answer = request.form.get("answer", "").lower().strip()

        if user_answer == correct:
            earned = give_task_reward(user)
            flash(f"Correct! +{earned} points 🎉", "success")
        else:
            flash("Wrong answer ❌", "error")

        session["last_color_task_time"] = now
        db.session.commit()
        return redirect("/color-task")

    # =========================
    # SHOW TASK / COOLDOWN
    # =========================
    if remaining > 0:
        return render_template(
            "color_task.html",
            user=user,
            question=None,
            remaining=remaining
        )

    question, answer = generate_color_task()
    session["color_correct"] = answer

    return render_template(
        "color_task.html",
        user=user,
        question=question,
        remaining=0
    )

@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])

    if request.method == "POST":
        amount = float(request.form["amount"])
        method = request.form["method"]
        account = request.form["account"]
        notify_email = request.form["notify_email"]  # ✅ DITO

        if amount < 300:
            flash("Minimum withdrawal is ₱300", "error")
            return redirect("/withdraw")

        if amount > user.cash_balance:
            flash("Insufficient balance", "error")
            return redirect("/withdraw")

        w = Withdrawal(
            user_id=user.user_id,
            amount=amount,
            method=method,
            account_info=account,
            notify_email=notify_email
        )

        user.cash_balance -= amount  # 🔒 lock funds
        db.session.add(w)
        db.session.commit()

        flash("Withdrawal request submitted!", "success")
        return redirect("/dashboard")

    return render_template("withdraw.html", user=user)

@app.route("/my-withdrawals")
def my_withdrawals():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])

    withdrawals = Withdrawal.query.filter_by(
        user_id=user.user_id
    ).order_by(Withdrawal.requested_at.desc()).all()

    return render_template(
        "my_withdrawals.html",
        user=user,
        withdrawals=withdrawals
    )

@app.route("/convert", methods=["POST"])
def convert_points():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])

    # CHECK MINIMUM POINTS
    if user.points < 200:
        flash("You need at least 200 points to convert.")
        return redirect("/dashboard")

    # RANDOM PESO VALUE
    peso = round(random.uniform(2.0, 2.5), 2)

    # DEDUCT POINTS & ADD CASH
    user.points -= 200
    user.cash_balance += peso

    db.session.commit()

    flash(f"Converted 200 points to ₱{peso}")
    return redirect("/dashboard")

@app.route("/convert-page")
def convert_page():
    if "user" not in session:
        return redirect("/login")

    user = User.query.get(session["user"])
    return render_template("convert.html", user=user)

@app.route("/about")
def about():
    return render_template("about.html", title="About iFund Marketing")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/signup")

# ======================
# RUN SERVER
# ======================
if __name__ == "__main__":
   app.run(host="0.0.0.0", port=5000, debug=True)
