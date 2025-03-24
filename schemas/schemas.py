from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from db.db import Base


class PowerInterruption(Base):
    __tablename__ = "power_interruptions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String)
    day = Column(String)
    time_range = Column(String)
    general_notes = Column(String)
    notices = relationship("PowerInterruptionNotice", back_populates="interruption")


class PowerInterruptionNotice(Base):
    __tablename__ = "power_interruption_notices"
    id = Column(Integer, primary_key=True, index=True)
    notice_id = Column(String)
    issuing_organization = Column(String)
    date_issued = Column(String)
    affected_area = Column(String)
    affected_customers = Column(String)
    reason = Column(String)
    affected_line = Column(String)
    specific_activities = Column(String)
    interruption_id = Column(Integer, ForeignKey("power_interruptions.id"))
    interruption = relationship("PowerInterruption", back_populates="notices")
