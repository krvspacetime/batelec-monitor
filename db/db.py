from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from schemas.schemas import Base  # Import Base from schemas

# Load environment variables
load_dotenv()

# Get database URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./batelec.db")

# Create engine
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Import all models to ensure they're registered with Base
from schemas.schemas import (
    Personnel,
    AffectedCustomer,
    SpecificActivity,
    PowerInterruptionNotice,
    AffectedArea,
    Barangay,
    PowerInterruptionData
)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create all tables if they don't exist
def create_tables():
    Base.metadata.create_all(bind=engine)
