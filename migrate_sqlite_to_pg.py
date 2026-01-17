from app import app, db
from models import User, ActivationCode, Withdrawal, AdminFund
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLITE_DB = "sqlite:///instance/database.db"
POSTGRES_DB = app.config["SQLALCHEMY_DATABASE_URI"]

sqlite_engine = create_engine(SQLITE_DB)
pg_engine = create_engine(POSTGRES_DB)

SqliteSession = sessionmaker(bind=sqlite_engine)
PgSession = sessionmaker(bind=pg_engine)

sqlite_sess = SqliteSession()
pg_sess = PgSession()

models = [User, ActivationCode, Withdrawal, AdminFund]

for model in models:
    rows = sqlite_sess.query(model).all()
    for row in rows:
        data = row.__dict__.copy()
        data.pop("_sa_instance_state", None)
        pg_sess.add(model(**data))

pg_sess.commit()

print("✅ Migration complete")
