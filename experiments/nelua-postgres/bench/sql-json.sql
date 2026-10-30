\set viewer 0
\set page_limit 10
\set page_offset 0
-- The same bounded page and 1,000-row count as nc_articles. PostgreSQL's JSON
-- text builders provide the serialization baseline, without a jsonb round trip.
WITH page AS MATERIALIZED (
    SELECT a.id FROM public.articles a
    ORDER BY a.id DESC LIMIT :page_limit::int OFFSET :page_offset::int
)
SELECT json_build_object(
    'articles', COALESCE((
        SELECT json_agg(article ORDER BY id DESC)
        FROM (
            SELECT a.id, json_build_object(
                'slug', a.slug,
                'title', a.title,
                'description', a.description,
                -- Avoid pgbench variable references in timestamp format strings.
                'createdAt', to_char(a.created_at AT TIME ZONE 'UTC',
                                     'YYYY-MM-DD"T"HH24' || chr(58) || 'MI' || chr(58) || 'SS.MS"Z"'),
                'updatedAt', to_char(a.updated_at AT TIME ZONE 'UTC',
                                     'YYYY-MM-DD"T"HH24' || chr(58) || 'MI' || chr(58) || 'SS.MS"Z"'),
                'tagList', ARRAY(
                    SELECT t.name FROM public.article_tags at
                    JOIN public.tags t ON t.id = at.tag_id
                    WHERE at.article_id = a.id ORDER BY t.name
                ),
                'favoritesCount', (
                    SELECT count(*) FROM public.favorites f WHERE f.article_id = a.id
                ),
                'favorited', EXISTS(
                    SELECT 1 FROM public.favorites f
                    WHERE f.article_id = a.id AND f.user_id = :viewer::bigint
                ),
                'author', json_build_object(
                    'username', u.username,
                    'bio', u.bio,
                    'image', u.image,
                    'following', EXISTS(
                        SELECT 1 FROM public.follows fo
                        WHERE fo.follower_id = :viewer::bigint
                          AND fo.followee_id = a.author_id
                    )
                )
            ) AS article
            FROM page p JOIN public.articles a ON a.id = p.id
            JOIN public.users u ON u.id = a.author_id
        ) enriched
    ), '[]'::json),
    'articlesCount', (
        SELECT count(*) FROM (SELECT 1 FROM public.articles LIMIT 1000) capped
    )
);
