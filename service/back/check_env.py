import sys
import os

print(f"Python version: {sys.version}")

try:
    import fastapi
    print("fastapi: OK")
except ImportError:
    print("fastapi: MISSING")

try:
    import uvicorn
    print("uvicorn: OK")
except ImportError:
    print("uvicorn: MISSING")

try:
    import sqlalchemy
    print("sqlalchemy: OK")
except ImportError:
    print("sqlalchemy: MISSING")

try:
    import psycopg2
    print("psycopg2: OK")
except ImportError:
    print("psycopg2: MISSING")

try:
    import pandas
    print("pandas: OK")
except ImportError:
    print("pandas: MISSING")

# Try to connect to DB if sqlalchemy is present
if 'sqlalchemy' in sys.modules:
    from sqlalchemy import create_engine, text
    from dotenv import load_dotenv
    from pathlib import Path

    _back = os.getcwd()
    _env_file = Path(_back) / ".env"
    load_dotenv(_env_file)

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    db_url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    print(f"Connecting to {db_host}...")
    
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1"))
            print("DB Connection: OK")
    except Exception as e:
        print(f"DB Connection: FAILED ({e})")
else:
    print("Skipping DB check because sqlalchemy is missing.")
