import argparse,ctypes as C,json,os,random,statistics,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--benchmark',action='store_true');p.add_argument('--seconds',type=float,default=1);p.add_argument('--measure-delay',type=float,default=0);args=p.parse_args()
here=Path(__file__).resolve().parent;root=here.parent
queries={name:(here/(name+'.sql')).read_text() for name in ('baseline','candidate','floor-only')}
pq=C.CDLL(str(root/'pg18/lib/libpq.so'))
for name,restype,types in [
 ('PQconnectdb',C.c_void_p,[C.c_char_p]),('PQstatus',C.c_int,[C.c_void_p]),('PQexec',C.c_void_p,[C.c_void_p,C.c_char_p]),
 ('PQprepare',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_char_p,C.c_int,C.c_void_p]),
 ('PQexecPrepared',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_int,C.POINTER(C.c_char_p),C.c_void_p,C.c_void_p,C.c_int]),
 ('PQresultStatus',C.c_int,[C.c_void_p]),('PQntuples',C.c_int,[C.c_void_p]),('PQnfields',C.c_int,[C.c_void_p]),
 ('PQgetlength',C.c_int,[C.c_void_p,C.c_int,C.c_int]),('PQgetisnull',C.c_int,[C.c_void_p,C.c_int,C.c_int]),
 ('PQgetvalue',C.c_void_p,[C.c_void_p,C.c_int,C.c_int]),('PQerrorMessage',C.c_char_p,[C.c_void_p]),
 ('PQclear',None,[C.c_void_p]),('PQfinish',None,[C.c_void_p])]:
 f=getattr(pq,name);f.restype=restype;f.argtypes=types
conn=pq.PQconnectdb(os.environ['DATABASE_URL'].encode());assert conn and pq.PQstatus(conn)==0
def good(r):
 if not r or pq.PQresultStatus(r) not in (1,2):raise RuntimeError(pq.PQerrorMessage(conn).decode())
 return r
def command(q):r=good(pq.PQexec(conn,q.encode()));pq.PQclear(r)
def materialize(r):
 try:return [[None if pq.PQgetisnull(r,i,j) else C.string_at(pq.PQgetvalue(r,i,j),pq.PQgetlength(r,i,j)) for j in range(pq.PQnfields(r))] for i in range(pq.PQntuples(r))]
 finally:pq.PQclear(r)
def textrows(q):return [[x.decode() if x is not None else None for x in row] for row in materialize(good(pq.PQexec(conn,q.encode())))]
def params(viewers,limits=10,offsets=0):
 ar=lambda x:('{'+','.join(map(str,x))+'}').encode()
 n=len(viewers)
 return (C.c_char_p*4)(ar(['""']*n),ar(viewers),ar(limits if isinstance(limits,list) else [limits]*n),ar(offsets if isinstance(offsets,list) else [offsets]*n))
def execute(name,values):return good(pq.PQexecPrepared(conn,name.encode(),4,values,None,None,1))
def explain(name,values,label):
 raw=textrows('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON,TIMING OFF) EXECUTE "'+name+'"('+','.join("'"+x.decode().replace("'","''")+"'" for x in values)+')')[0][0]
 obj=json.loads(raw)[0];(here/(label+'-'+name+'-plan.json')).write_text(json.dumps(obj,indent=2))
 def nodes(n):
  yield n
  for x in n.get('Plans',[]):yield from nodes(x)
 ns=list(nodes(obj['Plan']))
 return {'execution_ms':obj['Execution Time'],'planning_ms':obj['Planning Time'],'hits':obj['Plan'].get('Shared Hit Blocks'),
 'read':obj['Plan'].get('Shared Read Blocks'),'rows':obj['Plan']['Actual Rows'],
 'article_index_rows':sum(x.get('Actual Rows',0)*x.get('Actual Loops',0) for x in ns if x.get('Index Name')=='articles_author_idx'),
 'article_index_loops':sum(x.get('Actual Loops',0) for x in ns if x.get('Index Name')=='articles_author_idx')}
try:
 command("SET jit=off;SET max_parallel_workers_per_gather=0;SET statement_timeout='10s';SET TimeZone='UTC';SET plan_cache_mode=force_generic_plan;SET enable_memoize=off")
 for name,q in queries.items():pq.PQclear(good(pq.PQprepare(conn,name.encode(),q.encode(),4,None)))
 viewers=[int(x[0]) for x in textrows('SELECT DISTINCT follower_id FROM public.follows ORDER BY follower_id LIMIT 256')]
 empty=int(textrows('SELECT max(id)+1 FROM public.users')[0][0]);rng=random.Random(27)
 cases=[('one',params(viewers[:1])),('eight',params(viewers[:8])),('32',params(viewers[:32])),
 ('128',params(viewers[:128])),('empty',params([empty])),('mixed-empty',params([empty]+viewers[:31])),
 ('varying',params(viewers[:32],[(i%10)+1 for i in range(32)],[i%5*10 for i in range(32)])),
 ('same-viewer-pages',params([viewers[0]]*10,[1,5,10,20,50,100,1,10,20,100],[0,0,0,0,0,0,1,20,10000,9223372036854775807])),
 ('largeoffset',params(viewers[:8],100,100000000)),
 ('random128',params(rng.choices(viewers,k=128),[rng.choice([1,10,20,100]) for _ in range(128)],[rng.choice([0,10,20,40,100]) for _ in range(128)]))]
 (here/'inputs.json').write_text(json.dumps({label:[value.decode() for value in values] for label,values in cases},indent=2))
 command('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
 for label,values in cases:
  expected=materialize(execute('baseline',values))
  for name in ('candidate','floor-only'):
   got=materialize(execute(name,values));assert got==expected,(label,name,len(got),len(expected))
  print('PARITY',label,len(expected),flush=True)
 command('ROLLBACK')
 for label,values in cases:
  if label not in ('one','eight','32','128','varying','random128'):continue
  for name in queries:print('EXPLAIN',label,name,json.dumps(explain(name,values,label)),flush=True)
 if args.benchmark:
  if args.measure_delay:
   print('WAITING_FOR_CPU_WINDOW',args.measure_delay,flush=True);time.sleep(args.measure_delay)
  for label,values in cases:
   if label not in ('eight','32','128','varying'):continue
   for name in queries:
    for _ in range(3):pq.PQclear(execute(name,values))
   records={name:[] for name in queries}
   for name in ('baseline','candidate','floor-only','floor-only','candidate','baseline'):
    begin=time.perf_counter();count=0
    while time.perf_counter()-begin<args.seconds:pq.PQclear(execute(name,values));count+=1
    elapsed=time.perf_counter()-begin;records[name].append(count/elapsed)
    print('TIMING',label,name,count/elapsed,flush=True)
   median={name:statistics.median(x) for name,x in records.items()}
   print('SUMMARY',label,json.dumps(median),'ratio',median['candidate']/median['baseline'],'floor_ratio',median['floor-only']/median['baseline'],flush=True)
finally:pq.PQfinish(conn)
