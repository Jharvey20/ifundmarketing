from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ActivationCode(db.Model):
    __tablename__ = "activation_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    is_used = db.Column(db.Integer, default=0)
    used_by = db.Column(db.String(50), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)

    points = db.Column(db.Integer, default=0)
    cash_balance = db.Column(db.Float, default=0.0)

    referrals = db.Column(db.Integer, default=0)
    referral_balance = db.Column(db.Float, default=0.0)

    activation_code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20))
    amount = db.Column(db.Float)
    method = db.Column(db.String(20))
    account_info = db.Column(db.String(100))
    status = db.Column(db.String(20), default="pending")
    requested_at = db.Column(db.DateTime, default=db.func.now())
    processed_at = db.Column(db.DateTime)
    notify_email = db.Column(db.String(120), nullable=True)

class AdminFund(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20))  # add / subtract
    note = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=db.func.now())

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    task_type = db.Column(db.String(20))  
    # "color" or "math"

    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(50), nullable=False)

    reward = db.Column(db.Float, default=0.02)
    active = db.Column(db.Boolean, default=True)

class TaskLog(db.Model):
    __tablename__ = "task_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    platform = db.Column(db.String(20))  # web / messenger
    last_task_at = db.Column(db.DateTime)
