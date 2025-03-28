from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

# Association tables for many-to-many relationships
notice_personnel = Table(
    "notice_personnel",
    Base.metadata,
    Column(
        "notice_id",
        Integer,
        ForeignKey("power_interruption_notices.id"),
        primary_key=True,
    ),  # Good practice to have PK on assoc tables
    Column("personnel_id", Integer, ForeignKey("personnel.id"), primary_key=True),
)

notice_customers = Table(
    "notice_customers",
    Base.metadata,
    Column(
        "notice_id",
        Integer,
        ForeignKey("power_interruption_notices.id"),
        primary_key=True,
    ),
    Column(
        "customer_id", Integer, ForeignKey("affected_customers.id"), primary_key=True
    ),
)

notice_activities = Table(
    "notice_activities",
    Base.metadata,
    Column(
        "notice_id",
        Integer,
        ForeignKey("power_interruption_notices.id"),
        primary_key=True,
    ),
    Column(
        "activity_id", Integer, ForeignKey("specific_activities.id"), primary_key=True
    ),
)

# Association table for many-to-many relationship between power_interruption_data and affected_areas
data_areas = Table(
    "data_areas",
    Base.metadata,
    Column(
        "data_id", Integer, ForeignKey("power_interruption_data.id"), primary_key=True
    ),
    Column("area_id", Integer, ForeignKey("affected_areas.id"), primary_key=True),
)

# Association table for many-to-many relationship between power_interruption_data and affected_customers
data_customers = Table(
    "data_customers",
    Base.metadata,
    Column(
        "data_id", Integer, ForeignKey("power_interruption_data.id"), primary_key=True
    ),
    Column(
        "customer_id", Integer, ForeignKey("affected_customers.id"), primary_key=True
    ),
)

# *** NEW: Association table for many-to-many relationship between power_interruption_data and specific_activities ***
data_activities = Table(
    "data_activities",
    Base.metadata,
    Column(
        "data_id", Integer, ForeignKey("power_interruption_data.id"), primary_key=True
    ),
    Column(
        "activity_id", Integer, ForeignKey("specific_activities.id"), primary_key=True
    ),
)


class Personnel(Base):
    __tablename__ = "personnel"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)

    notices = relationship(
        "PowerInterruptionNotice",
        secondary=notice_personnel,
        back_populates="personnel",
    )


class AffectedCustomer(Base):
    __tablename__ = "affected_customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    notices = relationship(
        "PowerInterruptionNotice",
        secondary=notice_customers,
        back_populates="affected_customers",
    )
    power_interruption_data = relationship(
        "PowerInterruptionData",
        secondary=data_customers,
        back_populates="affected_customers",
    )


class SpecificActivity(Base):
    __tablename__ = "specific_activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    notices = relationship(
        "PowerInterruptionNotice",
        secondary=notice_activities,
        back_populates="specific_activities",
    )
    # *** CORRECTED: Use the new association table 'data_activities' ***
    power_interruption_data = relationship(
        "PowerInterruptionData",
        secondary=data_activities,  # Specify the association table
        back_populates="specific_activities",
    )


class PowerInterruptionNotice(Base):
    __tablename__ = "power_interruption_notices"

    id = Column(Integer, primary_key=True, index=True)
    control_no = Column(String, unique=True, nullable=False)
    date_issued = Column(DateTime, default=datetime.utcnow)

    personnel = relationship(
        "Personnel", secondary=notice_personnel, back_populates="notices"
    )
    affected_customers = relationship(
        "AffectedCustomer", secondary=notice_customers, back_populates="notices"
    )
    specific_activities = relationship(
        "SpecificActivity", secondary=notice_activities, back_populates="notices"
    )
    # *** CORRECTED: Adjusted back_populates to match PowerInterruptionData.notice ***
    # This now correctly represents a One-to-Many (or potentially One-to-One if uselist=False is added)
    # A notice can have associated interruption data.
    power_interruption_data = relationship(
        "PowerInterruptionData",
        back_populates="notice",  # Match the relationship name in PowerInterruptionData
        # Consider adding uselist=False here if one Notice maps to exactly ONE PowerInterruptionData
        # uselist=False
    )


class AffectedArea(Base):
    __tablename__ = "affected_areas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    barangays = relationship("Barangay", back_populates="area")
    power_interruption_data = relationship(
        "PowerInterruptionData", secondary=data_areas, back_populates="affected_areas"
    )


class Barangay(Base):
    __tablename__ = "barangays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    area_id = Column(Integer, ForeignKey("affected_areas.id"))

    area = relationship("AffectedArea", back_populates="barangays")


class PowerInterruptionData(Base):
    __tablename__ = "power_interruption_data"

    id = Column(Integer, primary_key=True, index=True)
    is_update = Column(Boolean, nullable=False)
    reason = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    affected_line = Column(String, nullable=False)

    # *** NEW: Foreign key linking to the notice this data belongs to ***
    notice_id = Column(
        Integer, ForeignKey("power_interruption_notices.id"), nullable=True
    )  # Or False if data MUST belong to a notice

    affected_areas = relationship(
        "AffectedArea", secondary=data_areas, back_populates="power_interruption_data"
    )
    affected_customers = relationship(
        "AffectedCustomer",
        secondary=data_customers,
        back_populates="power_interruption_data",
    )
    # *** CORRECTED: Use the new association table 'data_activities' ***
    specific_activities = relationship(
        "SpecificActivity",
        secondary=data_activities,  # Specify the association table
        back_populates="power_interruption_data",
    )
    # *** CORRECTED: Relationship to the parent notice ***
    # Renamed from 'notices' to 'notice' as it points to ONE notice
    notice = relationship(
        "PowerInterruptionNotice",
        back_populates="power_interruption_data",  # Match the relationship name in PowerInterruptionNotice
    )
