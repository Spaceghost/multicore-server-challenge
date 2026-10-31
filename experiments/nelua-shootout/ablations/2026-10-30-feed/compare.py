import argparse,ctypes as C,json,os,re,statistics,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--benchmark',action='store_true');p.add_argument('--seconds',type=float,default=1);args=p.parse_args()
here=Path(__file__).resolve().parent
baseline=(here/'baseline.sql').read_text()
candidate=(here/'candidate.sql').read_text()
import ctypes.util
pq=C.CDLL(os.environ.get('LIBPQ') or ctypes.util.find_library('pq'))
for name,restype,types in [
 ('PQconnectdb',C.c_void_p,[C.c_char_p]),('PQstatus',C.c_int,[C.c_void_p]),
 ('PQexec',C.c_void_p,[C.c_void_p,C.c_char_p]),('PQprepare',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_char_p,C.c_int,C.c_void_p]),
 ('PQexecPrepared',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_int,C.POINTER(C.c_char_p),C.c_void_p,C.c_void_p,C.c_int]),
 ('PQresultStatus',C.c_int,[C.c_void_p]),('PQntuples',C.c_int,[C.c_void_p]),('PQnfields',C.c_int,[C.c_void_p]),
 ('PQgetlength',C.c_int,[C.c_void_p,C.c_int,C.c_int]),('PQgetisnull',C.c_int,[C.c_void_p,C.c_int,C.c_int]),
 ('PQgetvalue',C.c_void_p,[C.c_void_p,C.c_int,C.c_int]),('PQresultErrorField',C.c_char_p,[C.c_void_p,C.c_int]),
 ('PQclear',None,[C.c_void_p]),('PQfinish',None,[C.c_void_p])]:
 f=getattr(pq,name);f.restype=restype;f.argtypes=types
conn=pq.PQconnectdb(os.environ['DATABASE_URL'].encode());assert conn and pq.PQstatus(conn)==0
def good(r):
 if not r or pq.PQresultStatus(r) not in (1,2):
  code=pq.PQresultErrorField(r,ord('C')) if r else b'null'
  raise RuntimeError('SQL failure '+repr(code))
 return r
def command(q):
 r=good(pq.PQexec(conn,q.encode()));pq.PQclear(r)
def scalarrows(q):
 r=good(pq.PQexec(conn,q.encode()))
 try:return [C.string_at(pq.PQgetvalue(r,i,0),pq.PQgetlength(r,i,0)).decode() for i in range(pq.PQntuples(r))]
 finally:pq.PQclear(r)
def parameters(viewers,limit=10,offset=0):
 ar=lambda values:('{'+','.join(map(str,values))+'}').encode()
 return (C.c_char_p*4)(ar(['""']*len(viewers)),ar(viewers),ar([limit]*len(viewers)),ar([offset]*len(viewers)))
def query(name,values):return good(pq.PQexecPrepared(conn,name.encode(),4,values,None,None,1))
def materialize(r):
 try:return [[None if pq.PQgetisnull(r,i,j) else C.string_at(pq.PQgetvalue(r,i,j),pq.PQgetlength(r,i,j)) for j in range(pq.PQnfields(r))] for i in range(pq.PQntuples(r))]
 finally:pq.PQclear(r)
try:
 command("SET jit=off; SET max_parallel_workers_per_gather=0; SET statement_timeout='10s'; SET TimeZone='UTC'; SET plan_cache_mode=force_generic_plan; SET enable_memoize=off")
 for name,q in [('baseline',baseline),('candidate',candidate)]:
  pq.PQclear(good(pq.PQprepare(conn,name.encode(),q.encode(),4,None)))
 viewers=list(map(int,scalarrows('SELECT DISTINCT follower_id FROM public.follows ORDER BY follower_id LIMIT 32')))
 empty=int(scalarrows('SELECT coalesce(max(id),0)+1 FROM public.users')[0])
 command('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
 for ids,limit,offset in [(viewers[:1],1,0),(viewers[:8],10,0),(viewers[:8],100,20),([empty],20,0),([empty]+viewers[:7],10,20),(viewers[:8],10,10000)]:
  values=parameters(ids,limit,offset)
  a=materialize(query('baseline',values));b=materialize(query('candidate',values));assert a==b,(len(a),len(b))
  print('PARITY',len(ids),limit,offset,len(a),flush=True)
 command('ROLLBACK')
 if args.benchmark:
  for batch in [32,128]:
   ids=(viewers*((batch+len(viewers)-1)//len(viewers)))[:batch];values=parameters(ids)
   for name in ['baseline','candidate']:
    for _ in range(5):pq.PQclear(query(name,values))
   outcomes={'baseline':[],'candidate':[]}
   for name in ['baseline','candidate','candidate','baseline']:
    start=time.perf_counter();count=0
    while time.perf_counter()-start<args.seconds:
     pq.PQclear(query(name,values));count+=1
    elapsed=time.perf_counter()-start
    outcomes[name].append(count/elapsed)
    print('TIMING',batch,name,count,elapsed,count/elapsed,flush=True)
   med={name:statistics.median(vals) for name,vals in outcomes.items()}
   print('SUMMARY',batch,med,'ratio',med['candidate']/med['baseline'],flush=True)
finally:pq.PQfinish(conn)
