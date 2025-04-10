import logging
from typing import Any, Dict, List
from datetime import datetime
from dateutil import parser  # Ensure dateutil is installed: pip install python-dateutil

from fastapi import APIRouter, Depends, HTTPException, status
from supabase.client import Client, PostgrestAPIResponse  # Assuming supabase-py types

router = APIRouter()


# --- Helper Function for Get-or-Create Pattern (Keep as is) ---
async def get_or_create_related_item(
    supabase: Client,
    logger: logging.Logger,
    table_name: str,
    item_data: Dict[str, Any],
    match_columns: List[str],
) -> int | None:
    """
    Checks if an item exists based on match_columns, inserts if not, returns the ID.
    (Implementation remains the same as provided in the original code)
    """
    try:
        query = supabase.table(table_name).select("id")
        log_match_str = []
        for col in match_columns:
            value = item_data.get(col)
            if value is None:
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
        # Ensure the mock client (if used) handles this sequence
        check_response: PostgrestAPIResponse = query.execute()

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
            # Ensure the mock client (if used) handles this sequence
            insert_response: PostgrestAPIResponse = (
                supabase.table(table_name).insert(item_data).execute()
            )
            if insert_response.data and len(insert_response.data) > 0:
                new_item_id = insert_response.data[0]["id"]
                logger.debug(
                    f"Successfully inserted item into '{table_name}'. New ID: {new_item_id}"
                )
                return new_item_id
            else:
                # Log the actual response if available and helpful
                error_details = (
                    f"Response Data: {insert_response.data}, Status: {insert_response.status_code}"
                    if hasattr(insert_response, "data")
                    else "No response data."
                )
                logger.error(
                    f"Failed to insert item into '{table_name}'. Data: {item_data}. {error_details}"
                )
                return None
    except Exception as db_exc:
        logger.error(
            f"Database error during get_or_create for table '{table_name}', data {item_data}: {db_exc}",
            exc_info=True,
        )
        return None


# --- Extracted Core Logic Function ---
async def process_and_create_interruption_record(
    structured_data: Dict[str, Any],  # Use the raw dict after model_dump()
    supabase: Client,
    logger: logging.Logger,
) -> int:
    """
    Parses dates, creates notice (if applicable), creates the main power
    interruption record, links related data, and returns the new record ID.

    Args:
        structured_data: Dictionary containing the AI's processed output.
        supabase: Initialized Supabase client.
        logger: Configured logger instance.

    Returns:
        The integer ID of the newly created main power interruption record.

    Raises:
        HTTPException: If parsing fails or critical database operations fail.
    """
    logger.info("Starting processing and creation of interruption record.")

    # --- 1. Parse date and times (Original Step 3) ---
    try:
        raw_date = structured_data.get("date")
        raw_start = structured_data.get("start_time")
        raw_end = structured_data.get("end_time")

        if not all([raw_date, raw_start, raw_end]):
            logger.error("Missing date, start_time, or end_time in AI response.")
            raise ValueError("Missing essential date/time fields from AI.")

        logger.debug(f"Raw times received: start='{raw_start}', end='{raw_end}'")

        def clean_time_string(time_str: Any) -> str:  # Accept Any, return str
            if time_str is None:
                return ""  # Handle None input
            time_str = str(time_str).strip().upper()
            if len(time_str) == 5 and time_str.endswith("H") and time_str[:4].isdigit():
                cleaned = f"{time_str[:2]}:{time_str[2:4]}"
                logger.debug(f"Cleaned time '{time_str}' to '{cleaned}'")
                return cleaned
            logger.debug(f"Time string '{time_str}' passed through without cleaning.")
            return time_str  # Return potentially unmodified string

        cleaned_start_str = clean_time_string(raw_start)
        cleaned_end_str = clean_time_string(raw_end)

        # Check if cleaned strings are empty after cleaning attempt
        if not cleaned_start_str or not cleaned_end_str:
            raise ValueError(
                "Start or end time resulted in empty string after cleaning."
            )

        parsed_date = parser.parse(str(raw_date)).date()  # Ensure raw_date is string
        parsed_start_time = parser.parse(cleaned_start_str).time()
        parsed_end_time = parser.parse(cleaned_end_str).time()
        full_start_datetime = datetime.combine(parsed_date, parsed_start_time)
        full_end_datetime = datetime.combine(parsed_date, parsed_end_time)
        target_date_str = parsed_date.isoformat()
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

    # --- 2. Create notice and related items (Original Step 5) ---
    notice_id = None
    # Use .get() with default empty list for safety
    notices_list = structured_data.get("notices", [])
    if isinstance(notices_list, list) and notices_list:
        # Process only the first notice if multiple are somehow present
        notice_data = notices_list[0]
        if isinstance(notice_data, dict):  # Ensure the item is a dictionary
            control_no = notice_data.get("control_no")
            date_issued_str = notice_data.get("date_issued")
            logger.info(f"Processing notice found in AI data. ControlNo: {control_no}")

            if not control_no or not date_issued_str:
                logger.warning(
                    "Notice data incomplete (missing control_no or date_issued). Skipping notice creation."
                )
            else:
                try:
                    parsed_date_issued = (
                        parser.parse(str(date_issued_str)).date().isoformat()
                    )
                    logger.debug(
                        f"Inserting notice: ControlNo={control_no}, DateIssued={parsed_date_issued}"
                    )
                    notice_response: PostgrestAPIResponse = (
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

                        # --- Process Notice Personnel ---
                        personnel_list = notice_data.get("personnel", [])
                        if isinstance(personnel_list, list):
                            logger.debug(
                                f"Processing {len(personnel_list)} personnel for notice {notice_id}."
                            )
                            for person in personnel_list:
                                if isinstance(person, dict):
                                    p_name = person.get("name")
                                    p_pos = person.get("position")
                                    if p_name and p_pos:
                                        personnel_id = await get_or_create_related_item(
                                            supabase,
                                            logger,
                                            "personnel",
                                            {"name": p_name, "position": p_pos},
                                            ["name", "position"],
                                        )
                                        if personnel_id:
                                            logger.debug(
                                                f"Linking Personnel ID {personnel_id} to Notice ID {notice_id}"
                                            )
                                            # Add error handling for junction table inserts?
                                            supabase.table("notice_personnel").insert(
                                                {
                                                    "notice_id": notice_id,
                                                    "personnel_id": personnel_id,
                                                }
                                            ).execute()
                                    else:
                                        logger.warning(
                                            f"Skipping personnel due to missing name/pos: {person}"
                                        )
                                else:
                                    logger.warning(
                                        f"Skipping invalid personnel item (not dict): {person}"
                                    )

                        # --- Process Notice Customers ---
                        customers_list = notice_data.get("affected_customers", [])
                        if isinstance(customers_list, list):
                            logger.debug(
                                f"Processing {len(customers_list)} customers for notice {notice_id}."
                            )
                            for cust_item in customers_list:
                                # Assuming customers are dicts like {"name": "Customer Name"} now
                                if isinstance(cust_item, dict):
                                    cust_name = cust_item.get("name")
                                    if cust_name:
                                        customer_id = await get_or_create_related_item(
                                            supabase,
                                            logger,
                                            "affected_customers",
                                            {"name": cust_name},
                                            ["name"],
                                        )
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
                                            f"Skipping customer in notice due to missing name: {cust_item}"
                                        )
                                else:
                                    logger.warning(
                                        f"Skipping invalid customer item (not dict): {cust_item}"
                                    )

                        # --- Process Notice Activities ---
                        activities_list = notice_data.get("specific_activities", [])
                        if isinstance(activities_list, list):
                            logger.debug(
                                f"Processing {len(activities_list)} activities for notice {notice_id}."
                            )
                            for act_item in activities_list:
                                # Assuming activities are dicts like {"name": "Activity Name"}
                                if isinstance(act_item, dict):
                                    act_name = act_item.get("name")
                                    if act_name:
                                        activity_id = await get_or_create_related_item(
                                            supabase,
                                            logger,
                                            "specific_activities",
                                            {"name": act_name},
                                            ["name"],
                                        )
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
                                            f"Skipping activity in notice due to missing name: {act_item}"
                                        )
                                else:
                                    logger.warning(
                                        f"Skipping invalid activity item (not dict): {act_item}"
                                    )

                    else:  # Failed notice insert
                        # Log details if possible from response
                        error_details = (
                            f"Response Data: {notice_response.data}, Status: {notice_response.status_code}"
                            if hasattr(notice_response, "data")
                            else "No response data."
                        )
                        logger.error(f"Failed to insert notice record. {error_details}")
                        # Decide if this is critical. Raising exception prevents main record creation.
                        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create notice record.")

                except Exception as notice_exc:
                    logger.error(
                        f"Error processing notice section: {notice_exc}", exc_info=True
                    )
                    # Decide if critical. Raising prevents main record creation.
                    # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing notice data.")
        else:
            logger.warning(
                "First item in 'notices' list is not a dictionary. Skipping notice processing."
            )
    elif notices_list:  # It exists but isn't a list or is empty
        logger.warning(
            f"Skipping notice processing because 'notices' field is not a non-empty list: {notices_list}"
        )

    # --- 3. Create the main power interruption data record (Original Step 6) ---
    logger.info("Preparing main power interruption data for insertion.")
    new_record_data = {
        "is_power_interruption_related": structured_data.get(
            "is_power_interruption_related", True
        ),
        "date_created": datetime.utcnow().isoformat() + "+00:00",  # Explicit UTC TZ
        "reason": structured_data.get("reason"),
        "date": target_date_str,
        "start_time": full_start_datetime.isoformat(),
        "end_time": full_end_datetime.isoformat(),
        "affected_line": structured_data.get("affected_line"),
        # Add notice_id if it was successfully created
        **({"notice_id": notice_id} if notice_id else {}),
    }
    logger.debug(f"Main record data to insert: {new_record_data}")

    try:
        record_response: PostgrestAPIResponse = (
            supabase.table("power_interruption_data").insert(new_record_data).execute()
        )
        if not record_response.data or len(record_response.data) == 0:
            error_details = (
                f"Response Data: {record_response.data}, Status: {record_response.status_code}"
                if hasattr(record_response, "data")
                else "No response data."
            )
            logger.error(
                f"Failed to create main power interruption record. {error_details}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create power interruption record in database. Status: {getattr(record_response, 'status_code', 'N/A')}",
            )

        record_id = record_response.data[0]["id"]
        logger.info(
            f"Successfully created main power interruption record with ID: {record_id}"
        )
    except Exception as main_rec_exc:
        # Catch potential exceptions from the execute() call itself or attribute errors
        logger.error(
            f"Database error inserting main record: {main_rec_exc}", exc_info=True
        )
        # Re-raise as HTTPException if not already one
        if isinstance(main_rec_exc, HTTPException):
            raise main_rec_exc
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error creating main record.",
            )

    # --- 4. Process & Link Affected Areas and Barangays (Original Step 7) ---
    affected_areas_list = structured_data.get("affected_areas", [])
    if isinstance(affected_areas_list, list) and affected_areas_list:
        logger.info(
            f"Processing {len(affected_areas_list)} affected areas for record ID: {record_id}"
        )
        for area_data in affected_areas_list:
            if not isinstance(area_data, dict):
                logger.warning(
                    f"Skipping invalid area data item (not a dict): {area_data}"
                )
                continue
            area_name = area_data.get("name")
            if not area_name:
                logger.warning(f"Skipping area with missing name: {area_data}")
                continue

            area_id = await get_or_create_related_item(
                supabase, logger, "affected_areas", {"name": area_name}, ["name"]
            )

            if area_id:
                logger.debug(
                    f"Linking Area ID {area_id} ('{area_name}') to Data ID {record_id}"
                )
                try:
                    supabase.table("data_areas").insert(
                        {"data_id": record_id, "area_id": area_id}
                    ).execute()
                except Exception as link_exc:
                    logger.error(
                        f"Failed to link Area ID {area_id} to Data ID {record_id}: {link_exc}",
                        exc_info=True,
                    )
                    # Potentially raise or just log and continue

                # Process Barangays
                barangays_list = area_data.get("barangays", [])
                if isinstance(barangays_list, list) and barangays_list:
                    logger.debug(
                        f"Processing {len(barangays_list)} barangays for area ID {area_id} ('{area_name}')."
                    )
                    for bgy_data_dict in barangays_list:
                        if not isinstance(bgy_data_dict, dict):
                            logger.warning(
                                f"Skipping invalid barangay data (not dict): {bgy_data_dict} in area '{area_name}'"
                            )
                            continue
                        actual_bgy_name = bgy_data_dict.get("name")
                        if not actual_bgy_name or not isinstance(actual_bgy_name, str):
                            logger.warning(
                                f"Skipping barangay with missing/invalid name: {bgy_data_dict} in area '{area_name}'."
                            )
                            continue

                        try:
                            # Check if barangay exists *for this area*
                            bgy_check_response: PostgrestAPIResponse = (
                                supabase.table("barangays")
                                .select("id", count="exact")  # Request count
                                .eq("name", actual_bgy_name)
                                .eq("area_id", area_id)
                                .execute()
                            )
                            # Check count from response if available, otherwise check data list length
                            existing_count = getattr(
                                bgy_check_response,
                                "count",
                                len(bgy_check_response.data or []),
                            )

                            if existing_count == 0:
                                logger.debug(
                                    f"Inserting new Barangay '{actual_bgy_name}' for Area ID {area_id}"
                                )
                                supabase.table("barangays").insert(
                                    {"name": actual_bgy_name, "area_id": area_id}
                                ).execute()  # Add error handling?
                            # else: logger.debug(f"Barangay '{actual_bgy_name}' already exists for Area ID {area_id}")
                        except Exception as bgy_exc:
                            logger.error(
                                f"Failed processing barangay '{actual_bgy_name}' for Area ID {area_id}: {bgy_exc}",
                                exc_info=True,
                            )
                            # Potentially raise or just log and continue
    else:
        logger.info("No affected areas listed or 'affected_areas' is not a list.")

    # --- 5. Link Top-Level Affected Customers (Original Step 8) ---
    # Re-evaluate: Are top-level customers distinct from notice customers? If not, remove this block.
    top_level_customers = structured_data.get("affected_customers", [])
    if isinstance(top_level_customers, list) and top_level_customers:
        logger.info(
            f"Linking {len(top_level_customers)} top-level affected customers to record ID: {record_id}"
        )
        for cust_data_dict in top_level_customers:
            if isinstance(cust_data_dict, dict):
                cust_name = cust_data_dict.get("name")
                if cust_name and isinstance(cust_name, str):
                    customer_id = await get_or_create_related_item(
                        supabase,
                        logger,
                        "affected_customers",
                        {"name": cust_name},
                        ["name"],
                    )
                    if customer_id:
                        logger.debug(
                            f"Linking Customer ID {customer_id} ('{cust_name}') to Data ID {record_id}"
                        )
                        try:
                            supabase.table("data_customers").insert(
                                {"data_id": record_id, "customer_id": customer_id}
                            ).execute()
                        except Exception as link_exc:
                            logger.error(
                                f"Failed to link top-level Customer ID {customer_id} to Data ID {record_id}: {link_exc}",
                                exc_info=True,
                            )
                else:
                    logger.warning(
                        f"Skipping invalid top-level customer data item (missing/invalid name): {cust_data_dict}"
                    )
            else:
                logger.warning(
                    f"Skipping invalid top-level customer data item (not dict): {cust_data_dict}"
                )

    # --- 6. Link Top-Level Specific Activities (Original Step 9) ---
    # Re-evaluate: Are top-level activities distinct from notice activities? If not, remove this block.
    top_level_activities = structured_data.get("specific_activities", [])
    if isinstance(top_level_activities, list) and top_level_activities:
        logger.info(
            f"Linking {len(top_level_activities)} top-level specific activities to record ID: {record_id}"
        )
        for act_data_dict in top_level_activities:
            if isinstance(act_data_dict, dict):
                act_name = act_data_dict.get("name")
                if act_name and isinstance(act_name, str):
                    activity_id = await get_or_create_related_item(
                        supabase,
                        logger,
                        "specific_activities",
                        {"name": act_name},
                        ["name"],
                    )
                    if activity_id:
                        logger.debug(
                            f"Linking Activity ID {activity_id} ('{act_name}') to Data ID {record_id}"
                        )
                        try:
                            supabase.table("data_activities").insert(
                                {"data_id": record_id, "activity_id": activity_id}
                            ).execute()
                        except Exception as link_exc:
                            logger.error(
                                f"Failed to link top-level Activity ID {activity_id} to Data ID {record_id}: {link_exc}",
                                exc_info=True,
                            )
                else:
                    logger.warning(
                        f"Skipping invalid top-level activity data item (missing/invalid name): {act_data_dict}"
                    )
            else:
                logger.warning(
                    f"Skipping invalid top-level activity data item (not dict): {act_data_dict}"
                )

    logger.info(f"Successfully processed and linked data for record ID: {record_id}")
    return record_id  # Return the ID of the main created record
