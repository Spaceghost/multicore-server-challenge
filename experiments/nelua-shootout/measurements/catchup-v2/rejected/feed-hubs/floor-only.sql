    WITH incoming AS MATERIALIZED (
      SELECT key,viewer,lim,off,ordinal
        FROM unnest($1::text[],$2::bigint[],$3::bigint[],$4::bigint[])
             WITH ORDINALITY AS r(key,viewer,lim,off,ordinal)
    ), page_keys AS MATERIALIZED (
      SELECT DISTINCT key,lim,off,viewer AS owner FROM incoming
    ), count_keys AS MATERIALIZED (
      SELECT DISTINCT key,owner FROM page_keys
    ), filter_ids AS MATERIALIZED (
      SELECT k.key,k.owner,k.owner AS id,
             ARRAY(SELECT fo.followee_id FROM public.follows fo
                    WHERE fo.follower_id=k.owner) AS fids,
             (SELECT max(LEAST(p.lim::numeric+p.off::numeric,9223372036854775807)::bigint)
                FROM page_keys p WHERE p.key=k.key AND p.owner=k.owner) AS depth
        FROM count_keys k
    ), hub_floors AS MATERIALIZED (
      SELECT h.fid,(SELECT a.id FROM public.articles a WHERE a.author_id=h.fid
                     ORDER BY a.id DESC LIMIT 1 OFFSET h.depth-1) AS floor_id
        FROM (SELECT x.fid,max(u.depth) AS depth
                FROM filter_ids u CROSS JOIN LATERAL unnest(u.fids) x(fid)
               GROUP BY x.fid HAVING count(*)>=2
               ORDER BY count(*) DESC,x.fid LIMIT 32) h
    ), cap_authors AS MATERIALIZED (
      SELECT ARRAY(SELECT h.fid
                     FROM (SELECT fid FROM hub_floors WHERE floor_id IS NOT NULL
                            ORDER BY floor_id DESC,fid
                            LIMIT LEAST(16,(SELECT count(*) FROM filter_ids)/2)) h
                    WHERE EXISTS(SELECT 1 FROM public.articles a WHERE a.author_id=h.fid
                                  ORDER BY a.id DESC LIMIT 1 OFFSET 999)) AS fids
    ), counts AS MATERIALIZED (
      SELECT f.key,f.owner,
             CASE WHEN cardinality(f.fids)=0 THEN 0::bigint
                  WHEN false THEN 1000::bigint
                  ELSE (SELECT count(*) FROM (SELECT 1 FROM public.articles a
                         WHERE a.author_id=ANY(f.fids) LIMIT 1000) capped) END AS n
        FROM filter_ids f
    ), pages AS MATERIALIZED (
      SELECT k.key,k.owner,k.lim,k.off,p.id
        FROM page_keys k JOIN filter_ids f ON f.key=k.key AND f.owner=k.owner
        CROSS JOIN LATERAL (SELECT COALESCE(max(h.floor_id),'-9223372036854775808'::bigint) AS floor_id
                             FROM hub_floors h WHERE h.fid=ANY(f.fids)) floor
        CROSS JOIN LATERAL unnest(ARRAY(SELECT id FROM (SELECT x.id FROM unnest(f.fids) fo(followee_id)
          CROSS JOIN LATERAL (SELECT a2.id FROM public.articles a2
            WHERE a2.author_id=fo.followee_id AND a2.id>=floor.floor_id
            ORDER BY a2.id DESC
            LIMIT LEAST(k.lim::numeric+k.off::numeric,9223372036854775807)::bigint) x
          ORDER BY x.id DESC LIMIT 100 OFFSET k.off) bounded LIMIT k.lim)) p(id)
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
           (a.id IS NOT NULL) AS following,
           c.n,r.ordinal::bigint
      FROM incoming r JOIN counts c ON c.key=r.key AND c.owner=r.viewer      LEFT JOIN pages p ON p.key=r.key AND p.owner=r.viewer        AND p.lim=r.lim AND p.off=r.off
      LEFT JOIN articles a ON a.id=p.id
     ORDER BY r.ordinal,a.id DESC
  