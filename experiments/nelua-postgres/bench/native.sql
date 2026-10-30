\set viewer 0
\set page_limit 10
\set page_offset 0
SELECT public.nc_articles(:viewer::bigint, :page_limit::int, :page_offset::int);
