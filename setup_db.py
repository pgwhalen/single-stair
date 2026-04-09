"""Set up PostgreSQL database with PostGIS extension for zoning data.

Run this once before using load_data.py. Requires:
  createdb urbanism   (if the database doesn't exist yet)
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main():
    load_dotenv()
    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("Error: DB_URL environment variable not set.")
        print("Create a .env file with: DB_URL=postgresql://user@localhost:5432/urbanism")
        return

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
        print("PostGIS extension ready.")
        print("Next step: python load_data.py")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print()
        print("Make sure PostgreSQL is running and the database exists:")
        print("  createdb urbanism")
        print("Then re-run this script.")


if __name__ == "__main__":
    main()
