    WITH incoming AS MATERIALIZED (
      SELECT key,viewer,lim,off,ordinal
        FROM unnest($1::text[],$2::bigint[],$3::bigint[],$4::bigint[])
             WITH ORDINALITY AS r(key,viewer,lim,off,ordinal)
    ), page_keys AS MATERIALIZED (
      SELECT DISTINCT key,lim,off,0::bigint AS owner FROM incoming
    ), count_keys AS MATERIALIZED (
      SELECT DISTINCT key,owner FROM page_keys
    ), filter_ids AS MATERIALIZED (
      SELECT k.key,k.owner,(SELECT t.id FROM public.tags t WHERE t.name=k.key) AS id FROM count_keys k
    ), counts AS MATERIALIZED (
      SELECT f.key,f.owner,(SELECT count(*) FROM (SELECT 1 FROM public.article_tags x WHERE x.tag_id=f.id LIMIT 1000) capped) AS n
        FROM filter_ids f
    ), pages AS MATERIALIZED (
      SELECT k.key,k.owner,k.lim,k.off,p.id
        FROM page_keys k JOIN filter_ids f ON f.key=k.key AND f.owner=k.owner
        CROSS JOIN LATERAL (SELECT id FROM (SELECT x.article_id AS id FROM public.article_tags x WHERE x.tag_id=f.id ORDER BY x.article_id DESC LIMIT 100 OFFSET k.off) bounded LIMIT k.lim) p
    ), page_ids AS MATERIALIZED (SELECT DISTINCT id FROM pages),
    articles AS MATERIALIZED (
      SELECT a.id,a.author_id,a.slug,a.title,a.description,a.created_at,a.updated_at,
             ARRAY(SELECT (SELECT t.name FROM public.tags t WHERE t.id=x.tag_id)
                     FROM public.article_tags x WHERE x.article_id=a.id ORDER BY 1) AS tag_list,
             (SELECT count(*) FROM public.favorites f WHERE f.article_id=a.id) AS favorites_count,
             u.username,u.bio,u.image
        FROM page_ids p JOIN public.articles a ON a.id=p.id
        JOIN public.users u ON u.id=a.author_id
    )
    SELECT a.slug,a.title,a.description,a.created_at,a.updated_at,
           a.tag_list,a.favorites_count,
           (r.viewer<>0 AND EXISTS(SELECT 1 FROM public.favorites f
             WHERE f.user_id=r.viewer AND f.article_id=a.id)) AS favorited,
           a.username,a.bio,a.image,
               (r.viewer<>0 AND EXISTS(SELECT 1 FROM public.follows f
      WHERE f.follower_id=r.viewer AND f.followee_id=a.author_id)) AS following,
           c.n,r.ordinal::bigint
      FROM incoming r JOIN counts c ON c.key=r.key AND c.owner=0::bigint      LEFT JOIN pages p ON p.key=r.key AND p.owner=0::bigint        AND p.lim=r.lim AND p.off=r.off
      LEFT JOIN articles a ON a.id=p.id
     ORDER BY r.ordinal,a.id DESC
  