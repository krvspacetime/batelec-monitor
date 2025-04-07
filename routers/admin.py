import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dateutil import parser
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from ai.gemini import get_structured_response
from db.supabase import get_supabase, verify_admin_role

# Import models for type hints

# Create a protected router with admin authentication
router = APIRouter(prefix="/admin", tags=["Admin"])


class AdminRequest(BaseModel):
    """
    Request model for the admin endpoint.

    Attributes:
        force: Whether to force a new response from the AI model
        fb_post_text: Text content of a Facebook post
        fb_post_images: List of image paths from a Facebook post
    """

    force: bool = False
    fb_post_text: str | None = None
    fb_post_images: List[str | Path] = []


@router.post("/")
async def admin(
    request: AdminRequest,
    # Protect this route with admin role verification
    user: Dict[str, Any] = Depends(verify_admin_role),
    supabase: Client = Depends(get_supabase),
):
    """
    Process a Facebook post to extract power interruption data and store it in Supabase.

    This endpoint is protected and requires admin authentication.

    Args:
        request: The admin request containing Facebook post data
        user: The authenticated user with admin role
        supabase: The Supabase client

    Returns:
        Dict: A message indicating the result of the operation and processed data preview

    Raises:
        HTTPException: If an error occurs during processing
    """
    try:
        # Get structured response from AI model
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

        # Check for existing record with same date in Supabase
        response = (
            supabase.table("power_interruption_data")
            .select("id, affected_areas(name)")
            .eq("date", parsed_date.isoformat())
            .execute()
        )

        existing_record = None
        if response.data and len(response.data) > 0:
            existing_record = response.data[0]

            # Get the record ID for further queries
            record_id = existing_record["id"]

            # Check if times match
            if (
                existing_record.get("start_time") == full_start_datetime.isoformat()
                and existing_record.get("end_time") == full_end_datetime.isoformat()
            ):
                # Check if affected areas match
                existing_areas = {
                    area["name"] for area in existing_record.get("affected_areas", [])
                }
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

        # First, create a notice if it exists in the data
        notice_id = None
        if data_dict.get("notices"):
            notice_data = data_dict["notices"][0]

            # Insert notice into Supabase
            notice_response = (
                supabase.table("power_interruption_notices")
                .insert(
                    {
                        "control_no": notice_data["control_no"],
                        "date_issued": parser.parse(notice_data["date_issued"])
                        .date()
                        .isoformat(),
                    }
                )
                .execute()
            )

            if notice_response.data and len(notice_response.data) > 0:
                notice_id = notice_response.data[0]["id"]

                # Insert personnel for the notice
                if notice_data.get("personnel"):
                    for person in notice_data["personnel"]:
                        # First insert or get the personnel
                        personnel_response = (
                            supabase.table("personnel")
                            .select("id")
                            .eq("name", person["name"])
                            .eq("position", person["position"])
                            .execute()
                        )

                        personnel_id = None
                        if personnel_response.data and len(personnel_response.data) > 0:
                            personnel_id = personnel_response.data[0]["id"]
                        else:
                            new_personnel_response = (
                                supabase.table("personnel")
                                .insert(
                                    {
                                        "name": person["name"],
                                        "position": person["position"],
                                    }
                                )
                                .execute()
                            )
                            if (
                                new_personnel_response.data
                                and len(new_personnel_response.data) > 0
                            ):
                                personnel_id = new_personnel_response.data[0]["id"]

                        # Link personnel to notice
                        if personnel_id:
                            supabase.table("notice_personnel").insert(
                                {"notice_id": notice_id, "personnel_id": personnel_id}
                            ).execute()

                # Insert affected customers for the notice
                if notice_data.get("affected_customers"):
                    for customer in notice_data["affected_customers"]:
                        # First insert or get the customer
                        customer_response = (
                            supabase.table("affected_customers")
                            .select("id")
                            .eq("name", customer)
                            .execute()
                        )

                        customer_id = None
                        if customer_response.data and len(customer_response.data) > 0:
                            customer_id = customer_response.data[0]["id"]
                        else:
                            new_customer_response = (
                                supabase.table("affected_customers")
                                .insert({"name": customer})
                                .execute()
                            )
                            if (
                                new_customer_response.data
                                and len(new_customer_response.data) > 0
                            ):
                                customer_id = new_customer_response.data[0]["id"]

                        # Link customer to notice
                        if customer_id:
                            supabase.table("notice_customers").insert(
                                {"notice_id": notice_id, "customer_id": customer_id}
                            ).execute()

                # Insert specific activities for the notice
                if notice_data.get("specific_activities"):
                    for activity in notice_data["specific_activities"]:
                        # First insert or get the activity
                        activity_response = (
                            supabase.table("specific_activities")
                            .select("id")
                            .eq("name", activity)
                            .execute()
                        )

                        activity_id = None
                        if activity_response.data and len(activity_response.data) > 0:
                            activity_id = activity_response.data[0]["id"]
                        else:
                            new_activity_response = (
                                supabase.table("specific_activities")
                                .insert({"name": activity})
                                .execute()
                            )
                            if (
                                new_activity_response.data
                                and len(new_activity_response.data) > 0
                            ):
                                activity_id = new_activity_response.data[0]["id"]

                        # Link activity to notice
                        if activity_id:
                            supabase.table("notice_activities").insert(
                                {"notice_id": notice_id, "activity_id": activity_id}
                            ).execute()

        # Now create the main power interruption data record
        new_record_data = {
            "is_power_interruption_related": data_dict["is_power_interruption_related"],
            "date_created": datetime.utcnow().isoformat(),
            "reason": data_dict["reason"],
            "date": full_start_datetime.date().isoformat(),
            "start_time": full_start_datetime.isoformat(),
            "end_time": full_end_datetime.isoformat(),
            "affected_line": data_dict["affected_line"],
        }

        # Add notice_id if a notice was created
        if notice_id:
            new_record_data["notice_id"] = notice_id

        # Insert the main record
        record_response = (
            supabase.table("power_interruption_data").insert(new_record_data).execute()
        )

        if not record_response.data or len(record_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create power interruption record",
            )

        record_id = record_response.data[0]["id"]

        # Process affected areas and their barangays
        if data_dict.get("affected_areas"):
            for area_data in data_dict["affected_areas"]:
                # First insert or get the area
                area_response = (
                    supabase.table("affected_areas")
                    .select("id")
                    .eq("name", area_data["name"])
                    .execute()
                )

                area_id = None
                if area_response.data and len(area_response.data) > 0:
                    area_id = area_response.data[0]["id"]
                else:
                    new_area_response = (
                        supabase.table("affected_areas")
                        .insert({"name": area_data["name"]})
                        .execute()
                    )
                    if new_area_response.data and len(new_area_response.data) > 0:
                        area_id = new_area_response.data[0]["id"]

                # Link area to power interruption data
                if area_id:
                    supabase.table("data_areas").insert(
                        {"data_id": record_id, "area_id": area_id}
                    ).execute()

                    # Process barangays for this area
                    if area_data.get("barangays"):
                        for barangay_name in area_data["barangays"]:
                            # First check if barangay exists
                            barangay_response = (
                                supabase.table("barangays")
                                .select("id")
                                .eq("name", barangay_name)
                                .eq("area_id", area_id)
                                .execute()
                            )

                            if (
                                not barangay_response.data
                                or len(barangay_response.data) == 0
                            ):
                                # Insert new barangay
                                supabase.table("barangays").insert(
                                    {"name": barangay_name, "area_id": area_id}
                                ).execute()

        # Process affected customers
        if data_dict.get("affected_customers"):
            for customer in data_dict["affected_customers"]:
                # First insert or get the customer
                customer_response = (
                    supabase.table("affected_customers")
                    .select("id")
                    .eq("name", customer)
                    .execute()
                )

                customer_id = None
                if customer_response.data and len(customer_response.data) > 0:
                    customer_id = customer_response.data[0]["id"]
                else:
                    new_customer_response = (
                        supabase.table("affected_customers")
                        .insert({"name": customer})
                        .execute()
                    )
                    if (
                        new_customer_response.data
                        and len(new_customer_response.data) > 0
                    ):
                        customer_id = new_customer_response.data[0]["id"]

                # Link customer to power interruption data
                if customer_id:
                    supabase.table("data_customers").insert(
                        {"data_id": record_id, "customer_id": customer_id}
                    ).execute()

        # Process specific activities
        if data_dict.get("specific_activities"):
            for activity in data_dict["specific_activities"]:
                # First insert or get the activity
                activity_response = (
                    supabase.table("specific_activities")
                    .select("id")
                    .eq("name", activity)
                    .execute()
                )

                activity_id = None
                if activity_response.data and len(activity_response.data) > 0:
                    activity_id = activity_response.data[0]["id"]
                else:
                    new_activity_response = (
                        supabase.table("specific_activities")
                        .insert({"name": activity})
                        .execute()
                    )
                    if (
                        new_activity_response.data
                        and len(new_activity_response.data) > 0
                    ):
                        activity_id = new_activity_response.data[0]["id"]

                # Link activity to power interruption data
                if activity_id:
                    supabase.table("data_activities").insert(
                        {"data_id": record_id, "activity_id": activity_id}
                    ).execute()

        return {
            "message": "Success: New power interruption record created",
            "processed_data_preview": data_dict,
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
