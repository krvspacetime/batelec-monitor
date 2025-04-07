-- Function to get all tables in the database
CREATE OR REPLACE FUNCTION get_tables()
RETURNS TABLE (table_name text) AS $$
BEGIN
    RETURN QUERY
    SELECT tablename::text
    FROM pg_catalog.pg_tables
    WHERE schemaname = 'public';
END;
$$ LANGUAGE plpgsql;