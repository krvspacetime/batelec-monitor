from typing import Any, Dict, List

from supabase import Client


def init_tables():
    """
    This function is a placeholder for SQLite database initialization.
    For Supabase, table initialization is handled through the CSV templates.
    """
    pass


def get_or_create_record(
    supabase: Client, table: str, search_criteria: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Get a record from Supabase if it exists, or create it if it doesn't.

    Args:
        supabase: Supabase client instance
        table: Table name to search in
        search_criteria: Dictionary of column-value pairs to search for

    Returns:
        Dict[str, Any]: The found or created record
    """
    # Build the query
    query = supabase.table(table).select("*")

    # Add search criteria
    for column, value in search_criteria.items():
        query = query.eq(column, value)

    # Execute the query
    response = query.execute()

    # Check if record exists
    if response.data and len(response.data) > 0:
        return response.data[0]

    # Create new record
    create_response = supabase.table(table).insert(search_criteria).execute()

    if create_response.data and len(create_response.data) > 0:
        return create_response.data[0]

    raise Exception(f"Failed to get or create record in {table}")


def link_many_to_many(
    supabase: Client,
    junction_table: str,
    primary_id: int,
    foreign_ids: List[int],
    primary_column: str,
    foreign_column: str,
) -> None:
    """
    Create many-to-many relationships in a junction table.

    Args:
        supabase: Supabase client instance
        junction_table: Name of the junction table
        primary_id: ID of the primary record
        foreign_ids: List of foreign record IDs to link
        primary_column: Name of the column for the primary ID
        foreign_column: Name of the column for the foreign IDs
    """
    for foreign_id in foreign_ids:
        # Create the relationship record
        supabase.table(junction_table).insert(
            {primary_column: primary_id, foreign_column: foreign_id}
        ).execute()
