#!/usr/bin/env python3
"""Exercise the extension in a disposable database using only Python + psql.

DATABASE_URL must name the disposable database created by the test runner.
This script replaces all Conduit rows there. It creates the fixed schema when
absent, but the extension must already be installed by the test runner.
"""

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATABASE_URL = os.environ.get("DATABASE_URL")
CHECKS = 0


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def psql(sql, *, error=None):
    proc = subprocess.run(
        [os.environ.get("PSQL", "psql"), "-X", "-q", "-A", "-t",
         "-v", "ON_ERROR_STOP=1", "-P", "null=null", "-d", DATABASE_URL],
        input="\\set VERBOSITY verbose\nSET standard_conforming_strings=on;\n" + sql,
        text=True, encoding="utf-8", capture_output=True,
        env={**os.environ, "PGCLIENTENCODING": "UTF8"},
    )
    if error:
        if proc.returncode == 0 or error not in proc.stderr:
            raise AssertionError(
                f"Expected SQLSTATE {error}, got exit {proc.returncode}: {proc.stderr}")
        return None
    if proc.returncode:
        raise AssertionError(f"psql failed ({proc.returncode}): {proc.stderr}\nSQL: {sql}")
    return proc.stdout.strip()


def query(sql, *, setup=""):
    output = psql(setup + "\n" + sql)
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def one(expression, *, setup=""):
    values = query("SELECT " + expression + ";", setup=setup)
    if len(values) != 1:
        raise AssertionError(f"Expected one row, got {len(values)}: {expression}")
    return values[0]


def check(label, actual, expected):
    global CHECKS
    if actual != expected:
        raise AssertionError(
            f"{label}\nExpected: {repr(expected)[:2500]}\nActual: {repr(actual)[:2500]}")
    CHECKS += 1
    print(f"ok {CHECKS}: {label}", flush=True)


def expect_error(label, expression, state="22023"):
    psql("SELECT " + expression + ";", error=state)
    check(label, True, True)


def timestamp(column):
    # Independent SQL formatting oracle; MS truncates fractional seconds.
    return "to_char(" + column + " AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"')"


def profile_payload(alias, viewer):
    return f"""jsonb_build_object(
      'username', {alias}.username, 'bio', {alias}.bio, 'image', {alias}.image,
      'following', EXISTS(SELECT 1 FROM public.follows f
                          WHERE f.follower_id={viewer} AND f.followee_id={alias}.id))"""


def article_payload(viewer, full):
    body = ", 'body', a.body" if full else ""
    return f"""jsonb_build_object(
      'slug',a.slug, 'title',a.title, 'description',a.description,
      'createdAt',{timestamp('a.created_at')}, 'updatedAt',{timestamp('a.updated_at')},
      'tagList',ARRAY(SELECT t.name FROM public.tags t
                       JOIN public.article_tags x ON x.tag_id=t.id
                      WHERE x.article_id=a.id ORDER BY t.name),
      'favoritesCount',(SELECT count(*) FROM public.favorites f WHERE f.article_id=a.id),
      'favorited',EXISTS(SELECT 1 FROM public.favorites f
                         WHERE f.article_id=a.id AND f.user_id={viewer}),
      'author',{profile_payload('u',viewer)} {body})"""


def article_oracle(slug, viewer=0, *, setup=""):
    rows = query(f"""SELECT jsonb_build_object('article',{article_payload(viewer,True)})
                       FROM public.articles a JOIN public.users u ON u.id=a.author_id
                      WHERE a.slug={sql_literal(slug)};""", setup=setup)
    return rows[0] if rows else None


def list_oracle(viewer=0, limit=20, offset=0, *, tag=None, author=None,
                favorited=None, feed=False):
    # This deliberately uses a direct WHERE scan, independently of the native
    # implementation's materialized ID pages and feed merge-per-followee plan.
    where = "true"
    if feed:
        where = f"a.author_id IN (SELECT followee_id FROM public.follows WHERE follower_id={viewer})"
    elif tag is not None:
        where = f"""EXISTS(SELECT 1 FROM public.article_tags x JOIN public.tags t ON t.id=x.tag_id
                            WHERE x.article_id=a.id AND t.name={sql_literal(tag)})"""
    elif author is not None:
        where = "u.username=" + sql_literal(author)
    elif favorited is not None:
        where = f"""EXISTS(SELECT 1 FROM public.favorites f JOIN public.users fu ON fu.id=f.user_id
                            WHERE f.article_id=a.id AND fu.username={sql_literal(favorited)})"""
    sql = f"""SELECT jsonb_build_object(
      'articles',(SELECT coalesce(jsonb_agg(payload ORDER BY id DESC),'[]'::jsonb)
                    FROM (SELECT a.id, {article_payload(viewer,False)} AS payload
                            FROM public.articles a JOIN public.users u ON u.id=a.author_id
                           WHERE {where} ORDER BY a.id DESC LIMIT {limit} OFFSET {offset}) page),
      'articlesCount',(SELECT count(*) FROM
                        (SELECT 1 FROM public.articles a JOIN public.users u ON u.id=a.author_id
                          WHERE {where} LIMIT 1000) capped));"""
    return query(sql)[0]


def native_list(viewer=0, limit=20, offset=0, *, tag=None, author=None, favorited=None):
    args = [viewer, limit, offset, tag, author, favorited]
    return one("public.nc_articles(" + ",".join(map(sql_literal,args)) + ")")


def comments_oracle(slug, viewer=0):
    sql = f"""SELECT jsonb_build_object('comments',coalesce(jsonb_agg(payload ORDER BY created_at DESC,id DESC),'[]'::jsonb))
      FROM (SELECT c.id,c.created_at,jsonb_build_object(
             'id',c.id,'body',c.body,'createdAt',{timestamp('c.created_at')},
             'updatedAt',{timestamp('c.updated_at')},'author',{profile_payload('u',viewer)}) payload
              FROM public.comments c JOIN public.users u ON u.id=c.author_id
              JOIN public.articles a ON a.id=c.article_id WHERE a.slug={sql_literal(slug)}
             ORDER BY c.created_at DESC,c.id DESC LIMIT 100) page;"""
    return query(sql)[0]


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL must name the disposable extension test database")
    if one("to_json(current_database())").startswith("nc_test_") is False:
        raise SystemExit("Fixture reset refused: database name must start with nc_test_. Use tests/run.sh.")
    if one("to_json(to_regclass('public.users')::text)") is None:
        psql((ROOT / "schema.sql").read_text())
    psql((HERE / "fixture.sql").read_text())

    tags = one("json_build_object('tags',ARRAY(SELECT name FROM public.tags ORDER BY name))")
    check("sorted tags, UTF-8 and every allowed ASCII control", one("public.nc_tags()"), tags)
    check("schema-qualified lookup resists temporary-table search_path", one("public.nc_tags()", setup="""
      CREATE TEMP TABLE tags(name text); INSERT INTO tags VALUES('hijacked');
      SET search_path=pg_temp,public;"""), tags)

    for username, viewer in [("alice",0),("alice",1),("reader",0),("quo'te\\雪",1)]:
        expected = query(f"SELECT jsonb_build_object('profile',{profile_payload('u',viewer)}) FROM public.users u WHERE username={sql_literal(username)};")[0]
        check(f"profile {username!r}, viewer={viewer}",
              one(f"public.nc_profile({sql_literal(username)},{viewer})"), expected)
    check("unknown profile", one("public.nc_profile('absent')"), None)

    for slug, viewer in [("article-1",0),("article-1",1),("article-1104",1),("article-1105",2)]:
        check(f"article detail {slug}, viewer={viewer}",
              one(f"public.nc_article({sql_literal(slug)},{viewer})"), article_oracle(slug,viewer))
    check("unknown article", one("public.nc_article('absent')"), None)
    check("malicious-looking slug remains a value", one("public.nc_article('x''); DROP TABLE public.users; --')"), None)
    setup = "SET TimeZone='Pacific/Kiritimati'; SET DateStyle='SQL, DMY';"
    check("UTC millisecond timestamps ignore TimeZone and DateStyle",
          one("public.nc_article('article-1104',1)",setup=setup), article_oracle("article-1104",1))

    cases = [
        ({}, "default global page"),
        ({"viewer":1,"limit":1}, "minimum page size"),
        ({"viewer":1,"limit":100,"offset":7}, "maximum page size and offset"),
        ({"viewer":1,"tag":"alpha"}, "tag count capped at 1000"),
        ({"viewer":1,"tag":"secondary","limit":7,"offset":9}, "tag pagination"),
        ({"viewer":1,"author":"alice"}, "author count capped at 1000"),
        ({"viewer":1,"author":"bob"}, "short author page"),
        ({"viewer":1,"favorited":"alice"}, "favorite count capped at 1000"),
        ({"viewer":1,"favorited":"reader"}, "favorite lookup uses named user"),
        ({"tag":"absent"}, "unknown tag returns empty page"),
        ({"author":"absent"}, "unknown author returns empty page"),
        ({"favorited":"absent"}, "unknown favorite user returns empty page"),
        ({"tag":"alpha","author":"absent","favorited":"absent"}, "tag filter has first precedence"),
        ({"author":"bob","favorited":"absent"}, "author filter has second precedence"),
        ({"tag":"","author":"alice"}, "empty tag remains an explicit filter"),
        ({"tag":"x'); DROP TABLE public.users; --"}, "filter SQL injection stays data"),
        ({"offset":2147483647}, "large legal offset gives empty page"),
    ]
    for args,label in cases:
        check(label,native_list(**args),list_oracle(**args))
    check("SQL defaults match explicit defaults",one("public.nc_articles()"),native_list())
    for viewer,limit,offset in [(1,20,0),(1,9,17),(2,20,0),(1,100,2147483647)]:
        check(f"merged feed viewer={viewer}, limit={limit}, offset={offset}",
              one(f"public.nc_feed({viewer},{limit},{offset})"),
              list_oracle(viewer,limit,offset,feed=True))
    for expression in ["public.nc_articles(0,0,0)","public.nc_articles(0,-1,0)",
                       "public.nc_articles(0,101,0)","public.nc_articles(0,20,-1)",
                       "public.nc_feed(1,0,0)","public.nc_feed(1,101,0)","public.nc_feed(1,20,-1)"]:
        expect_error("invalid page arguments: "+expression,expression)

    check("newest 100 comments, ties by id, escaped body and following",
          one("public.nc_comments('article-1',1)"),comments_oracle("article-1",1))
    check("existing article without comments",one("public.nc_comments('article-2')"),{"comments":[]})
    check("comments of absent article",one("public.nc_comments('absent')"),None)

    # Reuse retained plans in one backend while rows change between calls.
    changed = query("""BEGIN;
      SELECT public.nc_article('article-2');
      UPDATE public.articles SET title='changed within transaction' WHERE id=2;
      SELECT public.nc_article('article-2');
      ROLLBACK; SELECT public.nc_article('article-2');""")
    check("prepared plans do not cache article data",changed[1]["article"]["title"],"changed within transaction")
    check("rollback restores data after retained-plan reuse",changed[2],changed[0])

    for active in [True,True,False,False]:
        result=one(f"public.nc_favorite('article-7',1,{sql_literal(active)})")
        check(f"favorite active={active}: write visible in returned article",result["article"]["favorited"],active)
        check("favorite response equals ordinary SQL after commit",result,article_oracle("article-7",1))
    rolled=query("""BEGIN; SELECT public.nc_favorite('article-7',1,true);
      SELECT to_json(EXISTS(SELECT 1 FROM public.favorites WHERE user_id=1 AND article_id=7));
      ROLLBACK; SELECT to_json(EXISTS(SELECT 1 FROM public.favorites WHERE user_id=1 AND article_id=7));""")
    check("favorite visible inside caller transaction",rolled[1],True)
    check("favorite obeys caller rollback",rolled[2],False)

    for active in [False,False,True,True]:
        result=one(f"public.nc_follow('bob',1,{sql_literal(active)})")
        expected=query(f"SELECT jsonb_build_object('profile',{profile_payload('u',1)}) FROM public.users u WHERE username='bob';")[0]
        check(f"follow active={active}: idempotency and fresh visibility",result,expected)
    rolled=query("""BEGIN; SELECT public.nc_follow('bob',1,false);
      ROLLBACK; SELECT public.nc_profile('bob',1);""")
    check("follow obeys caller rollback",rolled[1]["profile"]["following"],True)
    check("favorite absent article",one("public.nc_favorite('absent',1,true)"),None)
    check("follow absent user",one("public.nc_follow('absent',1,true)"),None)
    for expression in ["public.nc_favorite('article-7',0,true)","public.nc_favorite('article-7',-1,true)",
                       "public.nc_follow('bob',0,true)","public.nc_follow('bob',-1,false)"]:
        expect_error("reject invalid write viewer: "+expression,expression)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:one("public.nc_favorite('article-9',1,true)"),range(4)))
    check("concurrent idempotent favorites return visible write",all(r["article"]["favorited"] for r in results),True)
    check("concurrent idempotent favorites create exactly one row",
          one("to_json((SELECT count(*) FROM public.favorites WHERE user_id=1 AND article_id=9))"),1)

    check("all extension functions retain invoker privileges",one("""to_json(NOT EXISTS(
      SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE n.nspname='public' AND p.proname LIKE 'nc_%' AND p.prosecdef))"""),True)
    if one("to_json((SELECT rolsuper FROM pg_roles WHERE rolname=current_user))"):
        role="nc_test_"+str(os.getpid())
        psql(f"CREATE ROLE {role}; GRANT USAGE ON SCHEMA public TO {role};")
        try:
            psql(f"SET ROLE {role}; SELECT public.nc_tags();",error="42501")
            check("invoker without table SELECT is denied",True,True)
        finally:
            psql(f"REVOKE ALL ON SCHEMA public FROM {role}; DROP ROLE {role};")
    else:
        print("skip: role permission probe requires superuser; invoker metadata verified",flush=True)

    print(f"PASS: {CHECKS} integration checks",flush=True)


if __name__ == "__main__":
    try:
        main()
    except (AssertionError,subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}",file=sys.stderr)
        sys.exit(1)
