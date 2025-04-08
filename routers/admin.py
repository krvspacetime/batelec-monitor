import logging  # Add this import
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dateutil import parser
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import (  # Import PostgrestAPIResponse for type hints
    Client,
    PostgrestAPIResponse,
)

from ai.gemini import get_structured_response
from db.supabase import get_supabase, verify_admin_role

# Assuming your AI response model is defined elsewhere, e.g.,
# from ai.models import StructuredResponse

# --- Logger Setup ---
# Get logger for this module
logger = logging.getLogger(__name__)
# Basic config (if not configured globally in your app startup)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- End Logger Setup ---


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
    user: Dict[str, Any] = Depends(verify_admin_role),  # User data from the dependency
    supabase: Client = Depends(get_supabase),
):
    # ... (docstring remains the same) ...
    admin_user_id = user.user.id  # Get admin user ID for logging
    logger.info(
        f"Admin endpoint invoked by user ID: {admin_user_id}. Force flag: {request.force}"
    )

    try:
        # --- 1. Get structured response from AI model ---
        logger.info("Requesting structured response from AI model...")
        structured_response = get_structured_response(
            force=request.force,
            fb_post_text=request.fb_post_text,
            fb_post_images=request.fb_post_images,
        )
        # Assuming structured_response is a Pydantic model
        data_dict = structured_response.model_dump()
        logger.info("Received structured response from AI.")
        # Optional: Log the preview at DEBUG level if needed for detailed tracing
        logger.debug(f"AI Response Data Preview: {data_dict}")

        # --- 2. Check relevance ---
        if not data_dict.get(
            "is_power_interruption_related", False
        ):  # Use .get for safety
            logger.warning(
                "AI determined post is NOT power interruption related. Skipping DB operations."
            )
            return {
                "message": "Not a power interruption related post",
                "processed_data_preview": data_dict,
            }
        logger.info("AI determined post IS power interruption related.")

        # --- 3. Parse date and times ---
        try:
            # Use .get with default values or check existence before parsing
            raw_date = data_dict.get("date")
            raw_start = data_dict.get("start_time")
            raw_end = data_dict.get("end_time")

            if not all([raw_date, raw_start, raw_end]):
                logger.error("Missing date, start_time, or end_time in AI response.")
                raise ValueError("Missing essential date/time fields from AI.")

            logger.debug(f"Raw times received: start='{raw_start}', end='{raw_end}'")

            # --- Preprocessing Step for Time Strings ---
            def clean_time_string(time_str: str) -> str:
                time_str = (
                    str(time_str).strip().upper()
                )  # Ensure string, remove whitespace, uppercase H
                # Check for HHMMH format (e.g., "2000H", "0930H")
                if (
                    len(time_str) == 5
                    and time_str.endswith("H")
                    and time_str[:4].isdigit()
                ):
                    cleaned = f"{time_str[:2]}:{time_str[2:4]}"  # Format as HH:MM
                    logger.debug(f"Cleaned time '{time_str}' to '{cleaned}'")
                    return cleaned
                # Add more cleaning rules here if needed for other formats
                logger.debug(
                    f"Time string '{time_str}' passed through without cleaning (or didn't match HHMMH)."
                )
                return time_str  # Return original if no specific cleaning rule matched

            # --- End Preprocessing ---

            cleaned_start_str = clean_time_string(raw_start)
            cleaned_end_str = clean_time_string(raw_end)

            # Now parse the cleaned strings
            parsed_date = parser.parse(raw_date).date()
            parsed_start_time = parser.parse(
                cleaned_start_str
            ).time()  # Use cleaned string
            parsed_end_time = parser.parse(cleaned_end_str).time()  # Use cleaned string
            full_start_datetime = datetime.combine(parsed_date, parsed_start_time)
            full_end_datetime = datetime.combine(parsed_date, parsed_end_time)
            logger.info(
                f"Parsed date: {parsed_date}, Start: {full_start_datetime}, End: {full_end_datetime}"
            )
        except (parser.ParserError, ValueError, TypeError) as parse_err:
            logger.error(
                f"Error parsing date/time from AI response: {parse_err}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not parse date/time fields: {parse_err}",
            )

        # --- 4. Check for existing record ---
        target_date_str = parsed_date.isoformat()
        logger.info(
            f"Checking for existing power interruption record on date: {target_date_str}"
        )
        try:
            response: PostgrestAPIResponse = (  # Type hint for clarity
                supabase.table("power_interruption_data")
                .select(
                    "id, start_time, end_time, affected_areas(name)"
                )  # Fetch fields needed for comparison
                .eq("date", target_date_str)
                .execute()
            )
            logger.debug(f"Supabase response: {response}.")
        except Exception as db_exc:
            logger.error(
                f"Database error during existence check: {db_exc}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error checking for existing record.",
            )

        # Process existence check result
        if response.data and len(response.data) > 0:
            # Loop through potentially multiple records for the same date (though unlikely based on logic)
            for existing_record in response.data:
                record_id = existing_record["id"]
                logger.info(
                    f"Found existing record(s) for date {target_date_str}. Checking record ID: {record_id} for match."
                )

                # --- Compare Timestamps ---
                # Convert stored ISO strings back to datetime objects for robust comparison
                # Be mindful of potential timezone differences if not stored consistently as UTC
                try:
                    existing_start = (
                        parser.isoparse(existing_record.get("start_time", ""))
                        if existing_record.get("start_time")
                        else None
                    )
                    existing_end = (
                        parser.isoparse(existing_record.get("end_time", ""))
                        if existing_record.get("end_time")
                        else None
                    )
                except ValueError:
                    logger.warning(
                        f"Could not parse existing timestamps for record {record_id}. Treating as mismatch."
                    )
                    existing_start, existing_end = None, None  # Force mismatch

                times_match = (
                    existing_start == full_start_datetime
                    and existing_end == full_end_datetime
                )
                logger.debug(
                    f"Record {record_id} - Times Match: {times_match} (Existing: {existing_start}, {existing_end} | New: {full_start_datetime}, {full_end_datetime})"
                )

                # --- Compare Affected Areas ---
                # Ensure 'affected_areas' from AI and DB are lists before processing
                existing_areas_raw = existing_record.get("affected_areas", [])
                new_areas_raw = data_dict.get("affected_areas", [])

                if not isinstance(existing_areas_raw, list):
                    existing_areas_raw = []
                if not isinstance(new_areas_raw, list):
                    new_areas_raw = []

                existing_areas_set = {
                    area.get("name") for area in existing_areas_raw if area.get("name")
                }
                new_areas_set = {
                    area.get("name") for area in new_areas_raw if area.get("name")
                }

                areas_match = existing_areas_set == new_areas_set
                logger.debug(
                    f"Record {record_id} - Areas Match: {areas_match} (Existing: {existing_areas_set} | New: {new_areas_set})"
                )

                if times_match and areas_match:
                    logger.info(
                        f"Exact match found for record ID {record_id}. No changes needed."
                    )
                    return {
                        "message": "Record already exists in the database with identical details",
                        "existing_record_id": record_id,
                        "processed_data_preview": data_dict,  # Return preview even if exists
                    }
                else:
                    logger.info(
                        f"Record ID {record_id} exists but differs in time or affected areas."
                    )
                    # Continue checking other potential records for the same date, though usually there'd be only one.
            # If loop finishes without exact match, fall through to create new record.
            logger.info(
                "No exact match found among existing records for this date. Proceeding to create new record."
            )
        else:
            logger.info(
                f"No existing record found for date: {target_date_str}. Proceeding to create new record."
            )

        # --- 5. Create new record (Logic starts here if no exact match found) ---
        notice_id = None
        # Wrap notice creation in its own try-except? Optional, depends on desired granularity.
        if data_dict.get("notices"):
            notice_data = data_dict["notices"][0]  # Assuming only one notice per post
            control_no = notice_data.get("control_no")
            date_issued_str = notice_data.get("date_issued")
            logger.info(f"Processing notice found in AI data. ControlNo: {control_no}")

            if not control_no or not date_issued_str:
                logger.warning(
                    "Notice data incomplete (missing control_no or date_issued). Skipping notice creation."
                )
            else:
                try:
                    # --- Insert Notice ---
                    parsed_date_issued = (
                        parser.parse(date_issued_str).date().isoformat()
                    )
                    logger.debug(
                        f"Inserting notice: ControlNo={control_no}, DateIssued={parsed_date_issued}"
                    )
                    notice_response = (
                        supabase.table("power_interruption_notices")
                        .insert(
                            {
                                "control_no": control_no,
                                "date_issued": parsed_date_issued,
                            }
                        )
                        .execute()
                    )

                    if notice_response.data and len(notice_response.data) > 0:
                        notice_id = notice_response.data[0]["id"]
                        logger.info(
                            f"Successfully created notice record with ID: {notice_id}"
                        )

                        # --- Process Notice Personnel (Get-or-Create & Link) ---
                        if notice_data.get("personnel"):
                            logger.debug(
                                f"Processing {len(notice_data['personnel'])} personnel for notice {notice_id}."
                            )
                            for person in notice_data["personnel"]:
                                p_name = person.get("name")
                                p_pos = person.get("position")
                                if p_name and p_pos:
                                    # Check/Insert Personnel
                                    personnel_id = await get_or_create_related_item(
                                        supabase,
                                        logger,
                                        "personnel",
                                        {"name": p_name, "position": p_pos},
                                        ["name", "position"],
                                    )
                                    # Link to Notice
                                    if personnel_id:
                                        logger.debug(
                                            f"Linking Personnel ID {personnel_id} to Notice ID {notice_id}"
                                        )
                                        supabase.table("notice_personnel").insert(
                                            {
                                                "notice_id": notice_id,
                                                "personnel_id": personnel_id,
                                            }
                                        ).execute()  # Consider adding error handling/logging here too
                                else:
                                    logger.warning(
                                        f"Skipping personnel due to missing name or position: {person}"
                                    )

                        # --- Process Notice Customers (Get-or-Create & Link) ---
                        if notice_data.get("affected_customers"):
                            logger.debug(
                                f"Processing {len(notice_data['affected_customers'])} customers for notice {notice_id}."
                            )
                            for cust_name in notice_data["affected_customers"]:
                                if cust_name:
                                    # Check/Insert Customer
                                    customer_id = await get_or_create_related_item(
                                        supabase,
                                        logger,
                                        "affected_customers",
                                        {"name": cust_name},
                                        ["name"],
                                    )
                                    # Link to Notice
                                    if customer_id:
                                        logger.debug(
                                            f"Linking Customer ID {customer_id} to Notice ID {notice_id}"
                                        )
                                        supabase.table("notice_customers").insert(
                                            {
                                                "notice_id": notice_id,
                                                "customer_id": customer_id,
                                            }
                                        ).execute()
                                else:
                                    logger.warning(
                                        "Skipping empty customer name for notice."
                                    )

                        # --- Process Notice Activities (Get-or-Create & Link) ---
                        if notice_data.get("specific_activities"):
                            logger.debug(
                                f"Processing {len(notice_data['specific_activities'])} activities for notice {notice_id}."
                            )
                            for act_name in notice_data["specific_activities"]:
                                if act_name:
                                    # Check/Insert Activity
                                    activity_id = await get_or_create_related_item(
                                        supabase,
                                        logger,
                                        "specific_activities",
                                        {"name": act_name},
                                        ["name"],
                                    )
                                    # Link to Notice
                                    if activity_id:
                                        logger.debug(
                                            f"Linking Activity ID {activity_id} to Notice ID {notice_id}"
                                        )
                                        supabase.table("notice_activities").insert(
                                            {
                                                "notice_id": notice_id,
                                                "activity_id": activity_id,
                                            }
                                        ).execute()
                                else:
                                    logger.warning(
                                        "Skipping empty activity name for notice."
                                    )

                    else:  # Failed notice insert
                        logger.error(
                            f"Failed to insert notice record. Response: {notice_response.data}, Status: {notice_response.status_code}"
                        )
                        # Decide if this is critical - should we stop? Maybe just log and continue without notice_id?
                        # For now, just log it. notice_id remains None.

                except Exception as notice_exc:
                    logger.error(
                        f"Error processing notice section: {notice_exc}", exc_info=True
                    )
                    # Again, decide if critical. notice_id will remain None if exception occurs.

        # --- 6. Create the main power interruption data record ---
        logger.info("Preparing main power interruption data for insertion.")
        new_record_data = {
            "is_power_interruption_related": data_dict.get(
                "is_power_interruption_related", True
            ),  # Should be true if we got here
            "date_created": datetime.utcnow().isoformat(),  # Use UTC
            "reason": data_dict.get("reason"),
            "date": target_date_str,  # Already formatted
            "start_time": full_start_datetime.isoformat(),
            "end_time": full_end_datetime.isoformat(),
            "affected_line": data_dict.get("affected_line"),
            # Add notice_id if it was successfully created
            **({"notice_id": notice_id} if notice_id else {}),
        }
        logger.debug(f"Main record data to insert: {new_record_data}")

        try:
            record_response = (
                supabase.table("power_interruption_data")
                .insert(new_record_data)
                .execute()
            )
            if not record_response.data or len(record_response.data) == 0:
                logger.error(
                    f"Failed to create main power interruption record. Response: {record_response.data}, Status: {record_response.status_code}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create power interruption record in database. Status: {record_response.status_code}",
                )

            record_id = record_response.data[0]["id"]
            logger.info(
                f"Successfully created main power interruption record with ID: {record_id}"
            )
        except Exception as main_rec_exc:
            logger.error(
                f"Database error inserting main record: {main_rec_exc}", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error creating main record.",
            )

        # --- 7. Process & Link Affected Areas and Barangays ---
        if data_dict.get("affected_areas"):
            logger.info(
                f"Processing {len(data_dict['affected_areas'])} affected areas for record ID: {record_id}"
            )
            for area_data in data_dict["affected_areas"]:
                area_name = area_data.get("name")
                if not area_name:
                    logger.warning(f"Skipping area with missing name: {area_data}")
                    continue

                # Get-or-Create Area
                area_id = await get_or_create_related_item(
                    supabase, logger, "affected_areas", {"name": area_name}, ["name"]
                )

                if area_id:
                    # Link Area to Data
                    logger.debug(
                        f"Linking Area ID {area_id} ('{area_name}') to Data ID {record_id}"
                    )
                    supabase.table("data_areas").insert(
                        {"data_id": record_id, "area_id": area_id}
                    ).execute()  # Add error check/log?

                    # Process Barangays for this Area
                    if area_data.get("barangays"):
                        logger.debug(
                            f"Processing {len(area_data['barangays'])} barangays for area ID {area_id} ('{area_name}')."
                        )
                        for bgy_name in area_data["barangays"]:
                            if not bgy_name:
                                logger.warning(
                                    f"Skipping empty barangay name in area '{area_name}'."
                                )
                                continue
                            # Check if barangay exists *for this area*
                            bgy_check = (
                                supabase.table("barangays")
                                .select("id")
                                .eq("name", bgy_name)
                                .eq("area_id", area_id)
                                .execute()
                            )
                            if not bgy_check.data:
                                # Insert new barangay linked to area
                                logger.debug(
                                    f"Inserting new Barangay '{bgy_name}' for Area ID {area_id}"
                                )
                                supabase.table("barangays").insert(
                                    {"name": bgy_name, "area_id": area_id}
                                ).execute()  # Add error check/log?
                            # else: logger.debug(f"Barangay '{bgy_name}' already exists for Area ID {area_id}")
        else:
            logger.info("No affected areas listed in AI data for this record.")

        # --- 8. Link Affected Customers (Top Level) ---
        # Note: Re-evaluate if this is needed if customers are *only* under notices
        if data_dict.get("affected_customers"):
            logger.info(
                f"Linking {len(data_dict['affected_customers'])} top-level affected customers to record ID: {record_id}"
            )
            for cust_name in data_dict["affected_customers"]:
                if not cust_name:
                    continue
                # Get-or-Create Customer (reusing helper)
                customer_id = await get_or_create_related_item(
                    supabase,
                    logger,
                    "affected_customers",
                    {"name": cust_name},
                    ["name"],
                )
                if customer_id:
                    # Link Customer to Data
                    logger.debug(
                        f"Linking Customer ID {customer_id} ('{cust_name}') to Data ID {record_id}"
                    )
                    supabase.table("data_customers").insert(
                        {"data_id": record_id, "customer_id": customer_id}
                    ).execute()  # Add error check/log?

        # --- 9. Link Specific Activities (Top Level) ---
        # Note: Re-evaluate if this is needed if activities are *only* under notices
        if data_dict.get("specific_activities"):
            logger.info(
                f"Linking {len(data_dict['specific_activities'])} top-level specific activities to record ID: {record_id}"
            )
            for act_name in data_dict["specific_activities"]:
                if not act_name:
                    continue
                # Get-or-Create Activity (reusing helper)
                activity_id = await get_or_create_related_item(
                    supabase,
                    logger,
                    "specific_activities",
                    {"name": act_name},
                    ["name"],
                )
                if activity_id:
                    # Link Activity to Data
                    logger.debug(
                        f"Linking Activity ID {activity_id} ('{act_name}') to Data ID {record_id}"
                    )
                    supabase.table("data_activities").insert(
                        {"data_id": record_id, "activity_id": activity_id}
                    ).execute()  # Add error check/log?

        # --- 10. Success Response ---
        logger.info(
            f"Successfully created and linked new power interruption record ID: {record_id}"
        )
        return {
            "message": "Success: New power interruption record created",
            "record_id": record_id,
            "processed_data_preview": data_dict,
        }

    except HTTPException as http_exc:
        # Logged already where raised, re-raise
        raise http_exc
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in the admin endpoint: {e}", exc_info=True
        )
        # traceback.print_exc() # logger.error with exc_info=True does this
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        )


# --- Helper Function for Get-or-Create Pattern ---
async def get_or_create_related_item(
    supabase: Client,
    logger: logging.Logger,
    table_name: str,
    item_data: Dict[str, Any],
    match_columns: List[str],
) -> int | None:
    """
    Checks if an item exists based on match_columns, inserts if not, returns the ID.
    """
    try:
        # Build query dynamically based on match_columns
        query = supabase.table(table_name).select("id")
        log_match_str = []
        for col in match_columns:
            value = item_data.get(col)
            if value is None:  # Cannot match on None usually
                logger.warning(
                    f"Missing value for match column '{col}' in table '{table_name}'. Cannot get/create item: {item_data}"
                )
                return None
            query = query.eq(col, value)
            log_match_str.append(f"{col}='{value}'")
        match_str = " AND ".join(log_match_str)

        logger.debug(
            f"Checking table '{table_name}' for existing item where {match_str}"
        )
        check_response = query.execute()

        if check_response.data and len(check_response.data) > 0:
            item_id = check_response.data[0]["id"]
            logger.debug(
                f"Found existing item in '{table_name}' with ID: {item_id} for {match_str}"
            )
            return item_id
        else:
            logger.debug(
                f"Item not found in '{table_name}' where {match_str}. Inserting new item."
            )
            logger.debug(f"Data for insert: {item_data}")
            insert_response = supabase.table(table_name).insert(item_data).execute()
            if insert_response.data and len(insert_response.data) > 0:
                new_item_id = insert_response.data[0]["id"]
                logger.debug(
                    f"Successfully inserted item into '{table_name}'. New ID: {new_item_id}"
                )
                return new_item_id
            else:
                logger.error(
                    f"Failed to insert item into '{table_name}'. Data: {item_data}. Response: {insert_response.data}, Status: {insert_response.status_code}"
                )
                return None
    except Exception as db_exc:
        logger.error(
            f"Database error during get_or_create for table '{table_name}', data {item_data}: {db_exc}",
            exc_info=True,
        )
        return None  # Indicate failure
