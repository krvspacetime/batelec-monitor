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


class AffectedAreas(BaseModel):
    name: str = Field(..., description="Name of the affected area")
    barangays: List[str] = Field(
        ..., description="List of barangays in the affected area"
    )


class PowerInterruptionData(BaseModel):
    is_update: bool = Field(..., description="Whether the response is an update")
    reason: str = Field(..., description="Reason for the interruption")
    date: str = Field(..., description="Start date of the interruption")
    start_time: str = Field(..., description="Start time of the interruption")
    end_time: str = Field(..., description="End time of the interruption")
    affected_areas: List[AffectedAreas] = Field(
        ..., description="List of affected areas"
    )
    affected_customers: List[str] = Field(..., description="List of affected customers")
    affected_line: str = Field(..., description="Line affected by the interruption")
    specific_activities: List[str] = Field(
        ..., description="List of specific activities"
    )
    notices: Optional[List[PowerInterruptionNotice]] = Field(
        None, description="List of power interruption notices"
    )
