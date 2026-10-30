\echo Use "CREATE EXTENSION nelua_conduit" to load this file. \quit

-- SECURITY INVOKER is intentional. Callers keep their own table privileges.
CREATE FUNCTION nc_tags() RETURNS json
AS 'MODULE_PATHNAME', 'nc_tags' LANGUAGE C STABLE PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_profile(username text, viewer bigint DEFAULT 0) RETURNS json
AS 'MODULE_PATHNAME', 'nc_profile' LANGUAGE C STABLE STRICT PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_article(slug text, viewer bigint DEFAULT 0) RETURNS json
AS 'MODULE_PATHNAME', 'nc_article' LANGUAGE C STABLE STRICT PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_articles(viewer bigint DEFAULT 0, page_limit integer DEFAULT 20,
                           page_offset integer DEFAULT 0, tag text DEFAULT NULL,
                           author text DEFAULT NULL, favorited text DEFAULT NULL) RETURNS json
AS 'MODULE_PATHNAME', 'nc_articles' LANGUAGE C STABLE PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_feed(viewer bigint, page_limit integer DEFAULT 20,
                       page_offset integer DEFAULT 0) RETURNS json
AS 'MODULE_PATHNAME', 'nc_feed' LANGUAGE C STABLE STRICT PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_comments(slug text, viewer bigint DEFAULT 0) RETURNS json
AS 'MODULE_PATHNAME', 'nc_comments' LANGUAGE C STABLE STRICT PARALLEL RESTRICTED
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_favorite(slug text, viewer bigint, active boolean) RETURNS json
AS 'MODULE_PATHNAME', 'nc_favorite' LANGUAGE C VOLATILE STRICT PARALLEL UNSAFE
SET search_path = pg_catalog, pg_temp;

CREATE FUNCTION nc_follow(username text, viewer bigint, active boolean) RETURNS json
AS 'MODULE_PATHNAME', 'nc_follow' LANGUAGE C VOLATILE STRICT PARALLEL UNSAFE
SET search_path = pg_catalog, pg_temp;
