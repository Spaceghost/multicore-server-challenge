import json,re
from pathlib import Path
root=Path('/workspace/scratch/7de47ba8b27a')
here=Path(__file__).resolve().parent
source=(root/'multicore-server-challenge/submissions/nelua-epoll-spaceghost/build/app.c').read_text()
strings=[]
for m in re.finditer(r'static char \w+\[\d+\] = ("(?:[^"\\]|\\.)*");',source):
 try:strings.append(json.loads(m[1]))
 except ValueError:pass
baseline=[q for q in strings if 'WITH incoming AS MATERIALIZED' in q and 'viewer AS owner' in q and 'AS following' in q]
assert len(baseline)==1
baseline=baseline[0]
(here/'baseline.sql').write_text(baseline)
start=baseline.index('    ), filter_ids AS MATERIALIZED (')
end=baseline.index('    ), page_ids AS MATERIALIZED (',start)
replacement='''    ), filter_ids AS MATERIALIZED (
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
                  WHEN f.fids && (SELECT fids FROM cap_authors) THEN 1000::bigint
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
'''
candidate=baseline[:start]+replacement+baseline[end:]
(here/'candidate.sql').write_text(candidate)
# A separate floor-only ablation attributes count proof vs range-bound savings.
floor_only=candidate.replace('WHEN f.fids && (SELECT fids FROM cap_authors) THEN 1000::bigint','WHEN false THEN 1000::bigint')
(here/'floor-only.sql').write_text(floor_only)
print('Generated',len(candidate.splitlines()),'line candidate from actual baseline')
