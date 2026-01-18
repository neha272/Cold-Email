"""Migration: Add resume_display_name column to prospects table."""

import sys

from sqlalchemy import text

from cold_emailer.config import load_config
from cold_emailer.state_store.db import create_database_engine, get_session


def migrate_add_resume_display_name():
    """Add resume_display_name column if it doesn't exist."""
    # Load config
    config = load_config()

    # Create engine
    engine = create_database_engine(config.database.path, echo=False)

    with get_session(engine) as session:
        # Check if column exists
        result = session.execute(text("PRAGMA table_info(prospects)"))
        columns = [row[1] for row in result]

        if "resume_display_name" in columns:
            print("✅ Column 'resume_display_name' already exists. No migration needed.")
            return

        print("📝 Adding 'resume_display_name' column to prospects table...")

        # Add the column
        session.execute(
            text(
                "ALTER TABLE prospects ADD COLUMN resume_display_name VARCHAR(255) DEFAULT 'Neha Sutariya'"
            )
        )

        # Update existing rows to have the default value
        session.execute(
            text(
                "UPDATE prospects SET resume_display_name = 'Neha Sutariya' WHERE resume_display_name IS NULL"
            )
        )

        session.commit()

        print("✅ Migration complete!")
        print("   - Added 'resume_display_name' column")
        print("   - Set default value 'Neha Sutariya' for all existing prospects")


if __name__ == "__main__":
    try:
        migrate_add_resume_display_name()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
