#ifndef NELUA_CONDUIT_QUERIES_H
#define NELUA_CONDUIT_QUERIES_H

/*
 * Fixed Conduit schema, PostgreSQL 18. These statements never create objects.
 * Names are schema-qualified so a caller's search_path cannot replace tables.
 * All input values use SPI parameters; none is interpolated into SQL.
 *
 * Article output, using 1-based SPI column numbers:
 *   full: slug, title, description, body, created_at, updated_at, tag_list,
 *         favorites_count, favorited, username, bio, image, following
 *   list: the same columns with body omitted.
 * Dates remain timestamptz, tags remain text[], counts remain bigint, and flags
 * remain boolean. Serialization belongs to Nelua, not the SQL executor.
 */

#define CONDUIT_ARTICLE_COLUMNS(body_column) \
    "a.slug, a.title, a.description, " body_column \
    "a.created_at, a.updated_at, " \
    "ARRAY(SELECT t.name FROM public.article_tags at " \
    "      JOIN public.tags t ON t.id = at.tag_id " \
    "      WHERE at.article_id = a.id ORDER BY t.name) AS tag_list, " \
    "(SELECT count(*) FROM public.favorites f " \
    " WHERE f.article_id = a.id) AS favorites_count, " \
    "EXISTS(SELECT 1 FROM public.favorites f " \
    "       WHERE f.article_id = a.id AND f.user_id = $1) AS favorited, " \
    "u.username, u.bio, u.image, " \
    "EXISTS(SELECT 1 FROM public.follows fo " \
    "       WHERE fo.follower_id = $1 AND fo.followee_id = a.author_id) AS following "

#define CONDUIT_FULL_SELECT \
    "SELECT " CONDUIT_ARTICLE_COLUMNS("a.body, ") \
    "FROM public.articles a JOIN public.users u ON u.id = a.author_id "

/* MATERIALIZED bounds the expensive per-article enrichment to the page. */
#define CONDUIT_PAGE_SELECT \
    "SELECT " CONDUIT_ARTICLE_COLUMNS("") \
    "FROM page p JOIN public.articles a ON a.id = p.id " \
    "JOIN public.users u ON u.id = a.author_id ORDER BY a.id DESC"

/* No parameters. Output: name text. */
static const char q_tags[] =
    "SELECT name FROM public.tags ORDER BY name";

/* Parameters: $1 viewer bigint, $2 username text. */
/* Output: username text, bio text?, image text?, following boolean. */
static const char q_profile[] =
    "SELECT u.username, u.bio, u.image, "
    "EXISTS(SELECT 1 FROM public.follows fo "
    "       WHERE fo.follower_id = $1 AND fo.followee_id = u.id) AS following "
    "FROM public.users u WHERE u.username = $2";

/* Parameters: $1 viewer bigint, $2 slug text / article id bigint. */
static const char q_article[] =
    CONDUIT_FULL_SELECT "WHERE a.slug = $2";

static const char q_article_by_id[] =
    CONDUIT_FULL_SELECT "WHERE a.id = $2";

/*
 * Page parameters: $1 viewer bigint, $2 limit int, $3 offset int.
 * Filtered pages additionally take $4 filter text. Only one filter applies;
 * the caller selects tag, then author, then favorited, in that precedence.
 * Primary/covering indexes produce newest IDs before enrichment.
 */
static const char q_list_all[] =
    "WITH page AS MATERIALIZED ("
    "SELECT a.id FROM public.articles a "
    "ORDER BY a.id DESC LIMIT $2 OFFSET $3) "
    CONDUIT_PAGE_SELECT;

static const char q_list_tag[] =
    "WITH page AS MATERIALIZED ("
    "SELECT at.article_id AS id FROM public.article_tags at "
    "WHERE at.tag_id = (SELECT t.id FROM public.tags t WHERE t.name = $4) "
    "ORDER BY at.article_id DESC LIMIT $2 OFFSET $3) "
    CONDUIT_PAGE_SELECT;

static const char q_list_author[] =
    "WITH page AS MATERIALIZED ("
    "SELECT a.id FROM public.articles a "
    "WHERE a.author_id = (SELECT u.id FROM public.users u WHERE u.username = $4) "
    "ORDER BY a.id DESC LIMIT $2 OFFSET $3) "
    CONDUIT_PAGE_SELECT;

static const char q_list_favorited[] =
    "WITH page AS MATERIALIZED ("
    "SELECT f.article_id AS id FROM public.favorites f "
    "WHERE f.user_id = (SELECT u.id FROM public.users u WHERE u.username = $4) "
    "ORDER BY f.article_id DESC LIMIT $2 OFFSET $3) "
    CONDUIT_PAGE_SELECT;

/*
 * Fetch at most limit+offset IDs per followed author, merge newest IDs, then
 * enrich only the final page. bigint addition avoids int offset overflow.
 */
static const char q_list_feed[] =
    "WITH page AS MATERIALIZED ("
    "SELECT x.id FROM public.follows fo CROSS JOIN LATERAL ("
    "SELECT a2.id FROM public.articles a2 WHERE a2.author_id = fo.followee_id "
    "ORDER BY a2.id DESC LIMIT ($2::bigint + $3::bigint)) x "
    "WHERE fo.follower_id = $1 "
    "ORDER BY x.id DESC LIMIT $2 OFFSET $3) "
    CONDUIT_PAGE_SELECT;

/* Counts deliberately stop after 1,000 source rows, per SPEC.md. */
/* No parameters. Output: count bigint. */
static const char q_count_all[] =
    "SELECT count(*) FROM (SELECT 1 FROM public.articles LIMIT 1000) s";

/* Filter-count parameters: $1 filter text. Output: count bigint. */
static const char q_count_tag[] =
    "SELECT count(*) FROM (SELECT 1 FROM public.article_tags at "
    "WHERE at.tag_id = (SELECT t.id FROM public.tags t WHERE t.name = $1) "
    "LIMIT 1000) s";

static const char q_count_author[] =
    "SELECT count(*) FROM (SELECT 1 FROM public.articles a "
    "WHERE a.author_id = (SELECT u.id FROM public.users u WHERE u.username = $1) "
    "LIMIT 1000) s";

static const char q_count_favorited[] =
    "SELECT count(*) FROM (SELECT 1 FROM public.favorites f "
    "WHERE f.user_id = (SELECT u.id FROM public.users u WHERE u.username = $1) "
    "LIMIT 1000) s";

/* Parameter: $1 viewer bigint. Output: count bigint. */
static const char q_count_feed[] =
    "SELECT count(*) FROM (SELECT 1 FROM public.articles a "
    "WHERE a.author_id IN (SELECT fo.followee_id FROM public.follows fo "
    "                      WHERE fo.follower_id = $1) "
    "LIMIT 1000) s";

/*
 * Parameters: $1 viewer bigint, $2 slug text. Output: id bigint, body text,
 * created_at timestamptz, updated_at timestamptz, username text, bio text?,
 * image text?, following boolean. Caller checks q_article_id first so a
 * nonexistent article produces 404 rather than an empty comments array.
 */
static const char q_comments[] =
    "WITH page AS MATERIALIZED ("
    "SELECT c.id, c.body, c.created_at, c.updated_at, c.author_id "
    "FROM public.comments c "
    "WHERE c.article_id = (SELECT a.id FROM public.articles a WHERE a.slug = $2) "
    "ORDER BY c.created_at DESC, c.id DESC LIMIT 100) "
    "SELECT c.id, c.body, c.created_at, c.updated_at, u.username, u.bio, u.image, "
    "EXISTS(SELECT 1 FROM public.follows fo "
    "       WHERE fo.follower_id = $1 AND fo.followee_id = c.author_id) AS following "
    "FROM page c JOIN public.users u ON u.id = c.author_id "
    "ORDER BY c.created_at DESC, c.id DESC";

/* Parameter: $1 slug text. Output: id bigint. */
static const char q_article_id[] =
    "SELECT id FROM public.articles WHERE slug = $1";

/* Parameters: $1 viewer bigint, $2 article id bigint. No returned rows. */
static const char q_favorite_insert[] =
    "INSERT INTO public.favorites (user_id, article_id) VALUES ($1, $2) "
    "ON CONFLICT DO NOTHING";

static const char q_favorite_delete[] =
    "DELETE FROM public.favorites WHERE user_id = $1 AND article_id = $2";

/* Parameter: $1 username text. Output: id bigint, username, bio?, image?. */
static const char q_user_profile[] =
    "SELECT id, username, bio, image FROM public.users WHERE username = $1";

/* Parameters: $1 viewer bigint, $2 followee id bigint. No returned rows. */
static const char q_follow_insert[] =
    "INSERT INTO public.follows (follower_id, followee_id) VALUES ($1, $2) "
    "ON CONFLICT DO NOTHING";

static const char q_follow_delete[] =
    "DELETE FROM public.follows WHERE follower_id = $1 AND followee_id = $2";

#undef CONDUIT_PAGE_SELECT
#undef CONDUIT_FULL_SELECT
#undef CONDUIT_ARTICLE_COLUMNS

#endif /* NELUA_CONDUIT_QUERIES_H */
