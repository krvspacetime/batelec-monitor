import traceback
from datetime import datetime
from pathlib import Path
from typing import List

from dateutil import parser
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai.gemini import get_structured_response
from db.db import get_db

# Import your SQLAlchemy models
from schemas.schemas import (  # Assuming your models are in models/models.py
    AffectedArea,
    AffectedCustomer,
    Barangay,
    Personnel,
    PowerInterruptionData,
    PowerInterruptionNotice,
    SpecificActivity,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


class AdminRequest(BaseModel):
    force: bool = False
    fb_post_text: str | None = None
    fb_post_images: List[str | Path] = []


@router.post("/")
def admin(
    request: AdminRequest,
    db: Session = Depends(get_db),
):
    try:
        structured_response = get_structured_response(
            force=request.force,
            fb_post_text=request.fb_post_text,
            fb_post_images=request.fb_post_images,
        )
        data_dict = structured_response.model_dump()

        # First check: Is this power interruption related?
        if not data_dict["is_power_interruption_related"]:
            return {
                "message": "Not a power interruption related post",
                "processed_data_preview": data_dict,
            }

        # --- Parse date and times correctly ---
        parsed_date = parser.parse(data_dict["date"]).date()
        parsed_start_time = parser.parse(data_dict["start_time"]).time()
        parsed_end_time = parser.parse(data_dict["end_time"]).time()
        full_start_datetime = datetime.combine(parsed_date, parsed_start_time)
        full_end_datetime = datetime.combine(parsed_date, parsed_end_time)
        # --- End parsing ---

        # Check for existing record with same date
        existing_record = (
            db.query(PowerInterruptionData)
            .filter(PowerInterruptionData.date == parsed_date)
            .first()
        )

        if existing_record:
            # Check if times match
            if (
                existing_record.start_time == full_start_datetime
                and existing_record.end_time == full_end_datetime
            ):
                # Check if affected areas match
                existing_areas = {area.name for area in existing_record.affected_areas}
                new_areas = {
                    area["name"] for area in data_dict.get("affected_areas", [])
                }

                if existing_areas == new_areas:
                    return {
                        "message": "Record already exists in the database",
                        "existing_record": existing_record,
                    }

        # Create new record since either:
        # - No record exists for this date, or
        # - Times don't match, or
        # - Affected areas don't match
        notice_obj = None
        if data_dict.get("notices"):
            notice_data = data_dict["notices"][0]
            notice_obj = PowerInterruptionNotice(
                control_no=notice_data["control_no"],
                date_issued=parser.parse(notice_data["date_issued"]).date(),
                personnel=[
                    Personnel(name=p["name"], position=p["position"])
                    for p in notice_data.get("personnel", [])
                ],
                affected_customers=[
                    AffectedCustomer(name=c)
                    for c in notice_data.get("affected_customers", [])
                ],
                specific_activities=[
                    SpecificActivity(name=a)
                    for a in notice_data.get("specific_activities", [])
                ],
            )

        new_record = PowerInterruptionData(
            is_power_interruption_related=data_dict["is_power_interruption_related"],
            date_created=datetime.utcnow(),  # Changed from current_datetime to use UTC
            reason=data_dict["reason"],
            date=full_start_datetime,  # Changed from parsed_date to full datetime
            start_time=full_start_datetime,
            end_time=full_end_datetime,
            affected_line=data_dict["affected_line"],
            affected_areas=[
                AffectedArea(
                    name=area["name"],
                    barangays=[Barangay(name=b) for b in area.get("barangays", [])],
                )
                for area in data_dict.get("affected_areas", [])
            ],
            affected_customers=[
                AffectedCustomer(name=c)
                for c in data_dict.get("affected_customers", [])
            ],
            specific_activities=[
                SpecificActivity(name=a)
                for a in data_dict.get("specific_activities", [])
            ],
            notice=notice_obj,
        )

        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "message": "Success: New power interruption record created",
            "processed_data_preview": data_dict,
        }

    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
