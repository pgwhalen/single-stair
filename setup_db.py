"""Set up PostgreSQL database with PostGIS extension for zoning data.

Run this once before using load_data.py. Requires:
  createdb urbanism   (if the database doesn't exist yet)
"""

from sqlalchemy import create_engine, text

DB_URL = "postgresql://pgwhalen@localhost:5432/urbanism"


def main():
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
        print("PostGIS extension ready in 'urbanism' database.")
        print("Next step: python load_data.py")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print()
        print("Make sure PostgreSQL is running and the database exists:")
        print("  createdb urbanism")
        print("Then re-run this script.")


if __name__ == "__main__":
    main()
