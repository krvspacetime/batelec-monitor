from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.db import get_db
from ai.gemini import get_structured_response

# Import your SQLAlchemy models
from schemas.schemas import (  # Assuming your models are in models/models.py
    PowerInterruptionData,
    PowerInterruptionNotice,
    AffectedArea,
    Barangay,
    AffectedCustomer,
    SpecificActivity,
    Personnel,
)
from dateutil import parser
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/")
def admin(db: Session = Depends(get_db), force: bool = False):
    try:
        structured_response = get_structured_response(force=force)

        # Convert Pydantic model to SQLAlchemy model
        data_dict = structured_response.model_dump()

        # --- Parse date and times correctly ---
        # Parse the date part once
        parsed_date = parser.parse(data_dict["date"]).date()
        # Parse the time parts
        parsed_start_time = parser.parse(data_dict["start_time"]).time()
        parsed_end_time = parser.parse(data_dict["end_time"]).time()
        # Combine date and time for DateTime columns
        full_start_datetime = datetime.combine(parsed_date, parsed_start_time)
        full_end_datetime = datetime.combine(parsed_date, parsed_end_time)
        # --- End parsing ---

        if structured_response.is_update:
            # Get the existing record based on the date *part* only
            existing_record = (
                db.query(PowerInterruptionData)
                .filter(
                    PowerInterruptionData.date == parsed_date
                )  # Filter by date object
                .first()
            )

            if existing_record:
                # Update fields using parsed values
                existing_record.is_update = data_dict["is_update"]
                existing_record.reason = data_dict["reason"]
                existing_record.date = parsed_date  # Store date object is fine if column allows (SQLite often does) OR use datetime.combine(parsed_date, time.min)
                existing_record.start_time = (
                    full_start_datetime  # Use combined datetime
                )
                existing_record.end_time = full_end_datetime  # Use combined datetime
                existing_record.affected_line = data_dict["affected_line"]

                # --- Relationship Updates ---
                # Clear existing relationships first (simpler approach)
                # Be cautious: This deletes related records if cascade is set!
                # A more robust way involves checking/updating existing related items.
                existing_record.affected_areas = []
                existing_record.affected_customers = []
                existing_record.specific_activities = []

                # Re-add relationships (consider fetching/updating existing related entities instead of always creating new ones)
                for area_data in data_dict.get("affected_areas", []):
                    # Simplified: Create new Area/Barangays. Consider find-or-create logic.
                    area_record = AffectedArea(
                        name=area_data["name"],
                        barangays=[
                            Barangay(name=b) for b in area_data.get("barangays", [])
                        ],
                    )
                    existing_record.affected_areas.append(area_record)

                existing_record.affected_customers = [
                    # Simplified: Create new Customers. Consider find-or-create logic.
                    AffectedCustomer(name=c)
                    for c in data_dict.get("affected_customers", [])
                ]

                existing_record.specific_activities = [
                    # Simplified: Create new Activities. Consider find-or-create logic.
                    SpecificActivity(name=a)
                    for a in data_dict.get("specific_activities", [])
                ]

                # Handle Notice update/creation
                if data_dict.get("notices"):
                    notice_data = data_dict["notices"][0]
                    # Try to find existing notice or create new
                    notice_obj = (
                        db.query(PowerInterruptionNotice)
                        .filter(
                            PowerInterruptionNotice.control_no
                            == notice_data["control_no"]
                        )
                        .first()
                    )
                    if not notice_obj:
                        # Create new notice object
                        notice_obj = PowerInterruptionNotice(
                            control_no=notice_data["control_no"],
                            date_issued=parser.parse(
                                notice_data["date_issued"]
                            ).date(),  # Or .datetime() if column type needs it
                            # Simplified: Always create new related items for notice
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
                        # Add only if new, let relationship assignment handle linking
                        db.add(notice_obj)
                        db.flush()  # Flush to potentially get ID if needed, though relationship assignment is better

                    # Associate with the existing record
                    existing_record.notice = notice_obj  # Assign the object
                else:
                    # If notices payload is empty/null, dissociate any existing notice
                    existing_record.notice = None

                db.commit()
                db.refresh(existing_record)
            else:
                # Handle case where update=True but no record found for the date
                raise HTTPException(
                    status_code=404,
                    detail=f"No record found for date {parsed_date} to update.",
                )

        else:  # Create new record
            # --- Create Notice object first (if any) ---
            notice_obj = None
            if data_dict.get("notices"):
                notice_data = data_dict["notices"][0]
                # Simplified: Always create new notice and related items. Consider find-or-create.
                notice_obj = PowerInterruptionNotice(
                    control_no=notice_data["control_no"],
                    date_issued=parser.parse(
                        notice_data["date_issued"]
                    ).date(),  # Or .datetime()
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
                # Don't add notice_obj to session yet if it's new, let cascade handle it.

            # --- Create new PowerInterruptionData record ---
            new_record = PowerInterruptionData(
                is_update=data_dict["is_update"],
                reason=data_dict["reason"],
                date=parsed_date,  # Store date object OR datetime.combine(parsed_date, time.min)
                start_time=full_start_datetime,  # Use combined datetime
                end_time=full_end_datetime,  # Use combined datetime
                affected_line=data_dict["affected_line"],
                # Create related objects directly (Simplified: always new)
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
                # Assign the single notice object
                notice=notice_obj,
            )

            db.add(new_record)
            db.commit()
            db.refresh(new_record)

        # Return the Pydantic version of the response if needed, or just success
        # You might need to fetch the created/updated data from DB and convert back to Pydantic
        return {
            "message": "Success",
            "processed_data_preview": data_dict,
        }  # Return original dict for now

    except Exception as e:
        db.rollback()
        import traceback

        traceback.print_exc()  # Print full traceback for debugging
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
