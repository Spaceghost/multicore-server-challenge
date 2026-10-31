import argparse,ctypes as C,json,os,re,statistics,struct,time
from pathlib import Path
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--benchmark',action='store_true');p.add_argument('--explain',action='store_true');p.add_argument('--seconds',type=float,default=1);args=p.parse_args()
baseline={kind:(here/f'family-{kind}.sql').read_text() for kind in range(5,10)}
unified=(here/'unified.sql').read_text()
import ctypes.util
pq=C.CDLL(os.environ.get('LIBPQ') or ctypes.util.find_library('pq'))
for name,restype,types in [
 ('PQconnectdb',C.c_void_p,[C.c_char_p]),('PQstatus',C.c_int,[C.c_void_p]),('PQexec',C.c_void_p,[C.c_void_p,C.c_char_p]),
 ('PQprepare',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_char_p,C.c_int,C.c_void_p]),
 ('PQexecPrepared',C.c_void_p,[C.c_void_p,C.c_char_p,C.c_int,C.POINTER(C.c_char_p),C.c_void_p,C.c_void_p,C.c_int]),
 ('PQsendQueryPrepared',C.c_int,[C.c_void_p,C.c_char_p,C.c_int,C.POINTER(C.c_char_p),C.c_void_p,C.c_void_p,C.c_int]),
 ('PQenterPipelineMode',C.c_int,[C.c_void_p]),('PQexitPipelineMode',C.c_int,[C.c_void_p]),
 ('PQpipelineSync',C.c_int,[C.c_void_p]),('PQgetResult',C.c_void_p,[C.c_void_p]),
 ('PQresultStatus',C.c_int,[C.c_void_p]),('PQntuples',C.c_int,[C.c_void_p]),('PQnfields',C.c_int,[C.c_void_p]),
 ('PQgetlength',C.c_int,[C.c_void_p,C.c_int,C.c_int]),('PQgetisnull',C.c_int,[C.c_void_p,C.c_int,C.c_int]),
 ('PQgetvalue',C.c_void_p,[C.c_void_p,C.c_int,C.c_int]),('PQresultErrorField',C.c_char_p,[C.c_void_p,C.c_int]),
 ('PQerrorMessage',C.c_char_p,[C.c_void_p]),('PQclear',None,[C.c_void_p]),('PQfinish',None,[C.c_void_p])]:
 f=getattr(pq,name);f.restype=restype;f.argtypes=types
conn=pq.PQconnectdb(os.environ['DATABASE_URL'].encode());assert conn and pq.PQstatus(conn)==0
def good(r):
 if not r or pq.PQresultStatus(r) not in (1,2):
  code=pq.PQresultErrorField(r,ord('C')) if r else b'null'
  print('SQLERROR',pq.PQerrorMessage(conn).decode(),flush=True)
  raise RuntimeError('SQL failure '+repr(code))
 return r
def command(q):r=good(pq.PQexec(conn,q.encode()));pq.PQclear(r)
def materialize(r):
 try:return [[None if pq.PQgetisnull(r,i,j) else C.string_at(pq.PQgetvalue(r,i,j),pq.PQgetlength(r,i,j)) for j in range(pq.PQnfields(r))] for i in range(pq.PQntuples(r))]
 finally:pq.PQclear(r)
def textrows(q):return [[x.decode() if x is not None else None for x in row] for row in materialize(good(pq.PQexec(conn,q.encode())))]
def array(values,quoted=False):
 return ('{'+','.join(('"'+str(x).replace('\\','\\\\').replace('"','\\"')+'"') if quoted else str(x) for x in values)+'}').encode()
def params(requests,combined):
 columns=[array([r[i] for r in requests],i==1) for i in range(5)]
 return (C.c_char_p*len(columns if combined else columns[1:]))(*(columns if combined else columns[1:]))
def execute(name,values,combined=False):return good(pq.PQexecPrepared(conn,name.encode(),5 if combined else 4,values,None,None,1))
def separate_results(requests):
 out={}
 for kind in range(5,10):
  indices=[i for i,r in enumerate(requests) if r[0]==kind]
  if not indices:continue
  rows=materialize(execute(f'f{kind}',params([requests[i] for i in indices],False)))
  for row in rows:
   local=struct.unpack('!q',row[-1])[0]-1;global_index=indices[local]
   row[-1]=struct.pack('!q',global_index+1);out.setdefault(global_index,[]).append(row)
 return [row for i in range(len(requests)) for row in out.get(i,[])]
def combined_results(requests):return materialize(execute('unified',params(requests,True),True))
def split(requests):
 assert pq.PQenterPipelineMode(conn)==1
 for kind in range(5,10):
  group=[r for r in requests if r[0]==kind]
  if group:assert pq.PQsendQueryPrepared(conn,f'f{kind}'.encode(),4,params(group,False),None,None,1)==1
 assert pq.PQpipelineSync(conn)==1
 while True:
  result=pq.PQgetResult(conn)
  if not result:
   if pq.PQstatus(conn)!=0:raise RuntimeError("pipeline connection lost")
   continue
  if pq.PQresultStatus(result)==10:pq.PQclear(result);break
  pq.PQclear(good(result))
 assert pq.PQexitPipelineMode(conn)==1
def combined(requests):pq.PQclear(execute('unified',params(requests,True),True))
def explain(name,requests,combined):
 values=params(requests,combined)
 literals=["'"+value.decode().replace("'","''")+"'" for value in values]
 raw=textrows(f"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON,TIMING OFF) EXECUTE {name}("+','.join(literals)+')')[0][0]
 obj=json.loads(raw)[0]
 def nodes(n):
  yield n
  for x in n.get('Plans',[]):yield from nodes(x)
 rows=list(nodes(obj['Plan']))
 return {'execution_ms':obj['Execution Time'],'planning_ms':obj['Planning Time'],
         'shared_hit_blocks':obj['Plan'].get('Shared Hit Blocks'),
         'rows':obj['Plan']['Actual Rows'],
         'article_enrichment_rows':[(n.get('CTE Name'),n.get('Subplan Name'),n.get('Actual Rows'),n.get('Actual Loops')) for n in rows if n.get('Subplan Name')=='CTE articles'],
         'never_executed':sum(n.get('Actual Loops')==0 for n in rows),
         'actual_total_cost':obj['Plan']['Total Cost']}
try:
 command("SET jit=off; SET max_parallel_workers_per_gather=0; SET statement_timeout='10s'; SET TimeZone='UTC'; SET plan_cache_mode=force_generic_plan; SET enable_memoize=off")
 for kind,q in baseline.items():pq.PQclear(good(pq.PQprepare(conn,f'f{kind}'.encode(),q.encode(),4,None)))
 pq.PQclear(good(pq.PQprepare(conn,b'unified',unified.encode(),5,None)))
 viewers=[int(x[0]) for x in textrows('SELECT DISTINCT follower_id FROM public.follows ORDER BY follower_id LIMIT 32')]
 users=[x[0] for x in textrows('SELECT username FROM public.users ORDER BY id LIMIT 32')]
 tags=[x[0] for x in textrows('SELECT name FROM public.tags ORDER BY id LIMIT 10')]
 empty=int(textrows('SELECT coalesce(max(id),0)+1 FROM public.users')[0][0])
 def mixed(size,shared=False):
  out=[]
  for i in range(size):
   kind=[5,5,5,5,6,7,8,9,9,9][i%10];j=0 if shared else i
   key=tags[j%len(tags)] if kind==6 else users[j%len(users)] if kind in(7,8) else ''
   out.append((kind,key,viewers[j%len(viewers)],10,[0,0,0,10,20][j%5]))
  return out
 cases=[[(5,'',0,10,0),(6,tags[0],viewers[0],10,0),(7,users[0],viewers[0],10,0),(8,users[0],viewers[0],10,0),(9,'',viewers[0],10,0)],
        [(5,'',0,1,0),(6,'absent',viewers[0],100,0),(7,'absent',viewers[0],100,0),(8,'absent',viewers[0],100,0),(9,'',empty,100,0)],
        mixed(32),mixed(128,True),[(kind,(tags[0] if kind==6 else users[0] if kind in(7,8) else ''),viewers[0],100,10000) for kind in range(5,10)]]
 command('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
 for no,requests in enumerate(cases):
  a=separate_results(requests);b=combined_results(requests)
  if a!=b:
   print('MISMATCH',no,len(a),len(b))
   for i,(x,y) in enumerate(zip(a,b)):
    if x!=y:print('FIRST',i,x,y);break
   raise SystemExit(1)
  print('PARITY',no,len(requests),len(a),flush=True)
 command('ROLLBACK')
 for label,requests in [('mixed32',mixed(32)),('shared128',mixed(128,True)),('mixed128',mixed(128))]:
  if args.explain:
   explanation={'unified':explain('unified',requests,True),'families':{}}
   for kind in range(5,10):
    group=[r for r in requests if r[0]==kind]
    if group:explanation['families'][kind]=explain(f'f{kind}',group,False)
   (here/(label+'-explain.json')).write_text(json.dumps(explanation,indent=2))
   print('EXPLAIN',label,json.dumps(explanation),flush=True)
  if args.benchmark:
   for fn in (split,combined):
    for _ in range(3):fn(requests)
   outcomes={'split':[],'combined':[]}
   for name,fn in [('split',split),('combined',combined),('combined',combined),('split',split)]:
    start=time.perf_counter();count=0
    while time.perf_counter()-start<args.seconds:fn(requests);count+=1
    elapsed=time.perf_counter()-start;outcomes[name].append(count/elapsed)
    print('TIMING',label,name,count,elapsed,count/elapsed,flush=True)
   med={name:statistics.median(vals) for name,vals in outcomes.items()}
   print('SUMMARY',label,med,'ratio',med['combined']/med['split'],flush=True)
finally:pq.PQfinish(conn)
