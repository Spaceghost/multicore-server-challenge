WITH incoming AS MATERIALIZED (
  SELECT kind,key,viewer,lim,off,ordinal
  FROM unnest($1::int[],$2::text[],$3::bigint[],$4::bigint[],$5::bigint[])
       WITH ORDINALITY AS r(kind,key,viewer,lim,off,ordinal)
), page_keys AS MATERIALIZED (
  SELECT DISTINCT kind,key,lim,off,CASE WHEN kind=9 THEN viewer ELSE 0::bigint END AS owner
  FROM incoming
), count_keys AS MATERIALIZED (
  SELECT DISTINCT kind,key,owner FROM page_keys
), filter_ids AS MATERIALIZED (
  SELECT k.kind,k.key,k.owner,
         CASE WHEN k.kind=6 THEN (SELECT t.id::bigint FROM public.tags t WHERE t.name=k.key)
              WHEN k.kind IN (7,8) THEN (SELECT u.id FROM public.users u WHERE u.username=k.key)
              WHEN k.kind=9 THEN k.owner ELSE 0::bigint END AS id
  FROM count_keys k
), counts AS MATERIALIZED (
  SELECT f.kind,f.key,f.owner,
         CASE f.kind
         WHEN 5 THEN (SELECT count(*) FROM (SELECT 1 FROM public.articles LIMIT 1000) capped)
         WHEN 6 THEN (SELECT count(*) FROM (SELECT 1 FROM public.article_tags x WHERE x.tag_id=f.id LIMIT 1000) capped)
         WHEN 7 THEN (SELECT count(*) FROM (SELECT 1 FROM public.articles a WHERE a.author_id=f.id LIMIT 1000) capped)
         WHEN 8 THEN (SELECT count(*) FROM (SELECT 1 FROM public.favorites x WHERE x.user_id=f.id LIMIT 1000) capped)
         WHEN 9 THEN (SELECT count(*) FROM (SELECT 1 FROM public.articles a WHERE a.author_id IN
                          (SELECT fo.followee_id FROM public.follows fo WHERE fo.follower_id=f.owner)
                        LIMIT 1000) capped)
         END AS n
  FROM filter_ids f
), pages AS MATERIALIZED (
  SELECT k.kind,k.key,k.owner,k.lim,k.off,p.id
  FROM page_keys k JOIN filter_ids f
    ON f.kind=k.kind AND f.key=k.key AND f.owner=k.owner
  CROSS JOIN LATERAL (
    SELECT id FROM (
      SELECT id FROM (
      (SELECT a.id FROM public.articles a WHERE k.kind=5
       ORDER BY a.id DESC LIMIT 100 OFFSET k.off)
      UNION ALL
      (SELECT x.article_id AS id FROM public.article_tags x WHERE k.kind=6 AND x.tag_id=f.id
       ORDER BY x.article_id DESC LIMIT 100 OFFSET k.off)
      UNION ALL
      (SELECT a.id FROM public.articles a WHERE k.kind=7 AND a.author_id=f.id
       ORDER BY a.id DESC LIMIT 100 OFFSET k.off)
      UNION ALL
      (SELECT x.article_id AS id FROM public.favorites x WHERE k.kind=8 AND x.user_id=f.id
       ORDER BY x.article_id DESC LIMIT 100 OFFSET k.off)
      UNION ALL
      (SELECT x.id FROM public.follows fo CROSS JOIN LATERAL (
         SELECT a2.id FROM public.articles a2 WHERE a2.author_id=fo.followee_id
         ORDER BY a2.id DESC
         LIMIT LEAST(k.lim::numeric+k.off::numeric,9223372036854775807)::bigint
       ) x WHERE k.kind=9 AND fo.follower_id=k.owner
       ORDER BY x.id DESC LIMIT 100 OFFSET k.off)
      ) merged ORDER BY id DESC LIMIT 100
    ) bounded LIMIT k.lim
  ) p
), page_ids AS MATERIALIZED (
  SELECT DISTINCT id FROM pages
), articles AS MATERIALIZED (
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
       CASE WHEN r.kind=9 THEN a.id IS NOT NULL
            ELSE r.viewer<>0 AND EXISTS(SELECT 1 FROM public.follows f
               WHERE f.follower_id=r.viewer AND f.followee_id=a.author_id) END AS following,
       c.n,r.ordinal::bigint
FROM incoming r JOIN counts c
  ON c.kind=r.kind AND c.key=r.key AND c.owner=CASE WHEN r.kind=9 THEN r.viewer ELSE 0::bigint END
LEFT JOIN pages p
  ON p.kind=r.kind AND p.key=r.key AND p.owner=CASE WHEN r.kind=9 THEN r.viewer ELSE 0::bigint END
 AND p.lim=r.lim AND p.off=r.off
LEFT JOIN articles a ON a.id=p.id
ORDER BY r.ordinal,a.id DESC
