from typing import List, Optional
from pydantic import BaseModel, Field


class Personnel(BaseModel):
    name: str = Field(..., description="Name of personnel")
    position: str = Field(..., description="Position of personnel")


class PowerInterruptionNotice(BaseModel):
    control_no: str = Field(..., description="Control number of the notice")
    date_issued: str = Field(..., description="Date the notice was issued")
    personnel: List[Personnel] = Field(..., description="List of personnel involved")
    affected_customers: List[str] = Field(..., description="List of affected customers")
    specific_activities: List[str] = Field(
        ..., description="List of specific activities"
    )


class InterruptionData(BaseModel):
    date: str = Field(..., description="Date of the interruption")
    day: str = Field(..., description="Day of the week")
    time_range: str = Field(..., description="Time range of the interruption")
    general_notes: Optional[str] = Field(
        None, description="General notes about the interruption"
    )
    affected_area: str = Field(..., description="Area affected by the interruption")
    affected_customers: List[str] = Field(..., description="List of affected customers")
    reason: str = Field(..., description="Reason for the interruption")
    affected_line: str = Field(..., description="Line affected by the interruption")
    specific_activities: List[str] = Field(
        ..., description="List of specific activities"
    )


class PowerInterruptionsResponse(BaseModel):
    reason: str = Field(..., description="Reason for the interruption")
    start_date: str = Field(..., description="Start date of the interruption")
    start_time: str = Field(..., description="Start time of the interruption")
    end_time: str = Field(..., description="End time of the interruption")
    affected_areas: List[str] = Field(..., description="List of affected areas")
    affected_customers: List[str] = Field(..., description="List of affected customers")
    affected_line: str = Field(..., description="Line affected by the interruption")
    specific_activities: List[str] = Field(
        ..., description="List of specific activities"
    )
    notices: Optional[List[PowerInterruptionNotice]] = Field(
        None, description="List of power interruption notices"
    )
