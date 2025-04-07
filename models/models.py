from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class Personnel(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Name of personnel")
    position: str = Field(..., description="Position of personnel")


class AffectedCustomer(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Name of affected customer")


class SpecificActivity(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Name of specific activity")


class Barangay(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Name of the barangay")
    area_id: Optional[int] = None


class AffectedArea(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Name of the affected area")
    barangays: List[Barangay] = Field(default_factory=list, description="List of barangays in the affected area")


class PowerInterruptionNotice(BaseModel):
    id: Optional[int] = None
    control_no: str = Field(..., description="Control number of the notice")
    date_issued: str = Field(..., description="Date the notice was issued")
    personnel: List[Personnel] = Field(default_factory=list, description="List of personnel involved")
    affected_customers: List[AffectedCustomer] = Field(default_factory=list, description="List of affected customers")
    specific_activities: List[SpecificActivity] = Field(
        default_factory=list, description="List of specific activities"
    )


class PowerInterruptionData(BaseModel):
    id: Optional[int] = None
    is_power_interruption_related: bool = Field(
        ..., description="Whether the data is related to a power interruption"
    )
    date_created: str = Field(..., description="Date the data was created")
    reason: str = Field(..., description="Reason for the interruption")
    date: str = Field(..., description="Start date of the interruption")
    start_time: str = Field(..., description="Start time of the interruption")
    end_time: str = Field(..., description="End time of the interruption")
    affected_areas: List[AffectedArea] = Field(
        default_factory=list, description="List of affected areas"
    )
    affected_customers: List[AffectedCustomer] = Field(default_factory=list, description="List of affected customers")
    affected_line: str = Field(..., description="Line affected by the interruption")
    specific_activities: List[SpecificActivity] = Field(
        default_factory=list, description="List of specific activities"
    )
    notice_id: Optional[int] = Field(None, description="ID of the associated notice")
    notice: Optional[PowerInterruptionNotice] = Field(
        None, description="Associated power interruption notice"
    )
