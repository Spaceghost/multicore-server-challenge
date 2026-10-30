/* Native libpq bridge: business queries and rendering live in Nelua. */
#include "native.h"
#include <libpq-fe.h>
#include <arpa/inet.h>
#include <endian.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

struct nc_db { PGconn *connection; bool prepared[128]; };

nc_db *nc_db_open(const char *url)
{
    nc_db *db = calloc(1,sizeof(*db));
    if (!db) return NULL;
    /* Avoid TLS CPU on loopback, preserving an explicit URL TLS policy. */
    char *parse_error=NULL;
    PQconninfoOption *options=PQconninfoParse(url,&parse_error);
    bool local=false, explicit_tls=false;
    if (!options) { PQfreemem(parse_error); free(db); return NULL; }
    for (PQconninfoOption *p=options;p->keyword;++p) {
        if (!strcmp(p->keyword,"host") && p->val)
            local=!strcmp(p->val,"127.0.0.1") || !strcmp(p->val,"::1") ||
                  !strcmp(p->val,"localhost") || p->val[0]=='/';
        if (!strcmp(p->keyword,"sslmode") && p->val) explicit_tls=true;
    }
    PQconninfoFree(options);
    const char *keys[] = {"dbname","application_name","connect_timeout","sslmode",NULL};
    const char *values[] = {url,"nelua-conduit","5",local&&!explicit_tls?"disable":NULL,NULL};
    db->connection = PQconnectdbParams(keys,values,1);
    if (PQstatus(db->connection) != CONNECTION_OK) {
        fprintf(stderr,"database connection failed\n");
        nc_db_close(db); return NULL;
    }
    PGresult *r = PQexec(db->connection,
        "SET jit=off; SET max_parallel_workers_per_gather=0; "
        "SET statement_timeout='10s'; SET TimeZone='UTC'; "
        "SET plan_cache_mode=force_generic_plan; SET enable_memoize=off");
    bool good = r && PQresultStatus(r)==PGRES_COMMAND_OK;
    PQclear(r);
    if (!good) { nc_db_close(db); return NULL; }
    return db;
}
void nc_db_close(nc_db *db)
{
    if (db) { if (db->connection) PQfinish(db->connection); free(db); }
}
nc_result *nc_db_query(nc_db *db,int id,const char *sql,int count,const char *const *parameters)
{
    if (!db || id<0 || id>=128 || count<0 || count>16) return NULL;
    char name[16];
    snprintf(name,sizeof(name),"n%d",id);
    if (!db->prepared[id]) {
        PGresult *r = PQprepare(db->connection,name,sql,count,NULL);
        if (!r || PQresultStatus(r)!=PGRES_COMMAND_OK) return r;
        PQclear(r); db->prepared[id]=true;
    }
    PGresult *r = PQexecPrepared(db->connection,name,count,parameters,NULL,NULL,1);
    if (r && PQresultStatus(r)==PGRES_FATAL_ERROR) {
        const char *state=PQresultErrorField(r,PG_DIAG_SQLSTATE);
        /* SQLSTATE only: never log input, tokens, passwords or SQL parameters. */
        if (!state || strcmp(state,"23505"))
            fprintf(stderr,"query %d failed (SQLSTATE %s)\n",id,state?state:"unknown");
    }
    return r;
}
bool nc_tx(nc_db *db,const char *command)
{
    PGresult *r=PQexec(db->connection,command);
    bool good=nc_db_ok(r); PQclear(r); return good;
}
bool nc_db_ok(nc_result *r)
{
    return r && (PQresultStatus(r)==PGRES_TUPLES_OK || PQresultStatus(r)==PGRES_COMMAND_OK);
}
bool nc_db_unique(nc_result *r)
{
    const char *s=r?PQresultErrorField(r,PG_DIAG_SQLSTATE):NULL;
    return s && strcmp(s,"23505")==0;
}
void nc_result_free(nc_result *r) { PQclear(r); }
int nc_rows(nc_result *r) { return r?PQntuples(r):0; }
bool nc_null(nc_result *r,int row,int col) { return !r || PQgetisnull(r,row,col); }
const char *nc_value(nc_result *r,int row,int col)
{ return nc_null(r,row,col)?NULL:PQgetvalue(r,row,col); }
size_t nc_value_length(nc_result *r,int row,int col)
{ return nc_null(r,row,col)?0:(size_t)PQgetlength(r,row,col); }
int64_t nc_integer(nc_result *r,int row,int col)
{
    if (nc_null(r,row,col)) return 0;
    const void *p=PQgetvalue(r,row,col);
    if (PQgetlength(r,row,col)==8) { uint64_t x; memcpy(&x,p,8); return (int64_t)be64toh(x); }
    if (PQgetlength(r,row,col)==4) { uint32_t x; memcpy(&x,p,4); return (int32_t)ntohl(x); }
    if (PQgetlength(r,row,col)==2) { uint16_t x; memcpy(&x,p,2); return (int16_t)ntohs(x); }
    return 0;
}
bool nc_boolean(nc_result *r,int row,int col)
{ return !nc_null(r,row,col) && PQgetvalue(r,row,col)[0]!=0; }
void nc_timestamp(nc_buffer *b,nc_result *r,int row,int col)
{
    int64_t usec=nc_integer(r,row,col);
    int64_t seconds=usec/1000000, fraction=usec%1000000;
    if (fraction<0) { fraction+=1000000; --seconds; }
    time_t epoch=(time_t)(seconds+946684800LL);
    struct tm tm; char out[40];
    if (!gmtime_r(&epoch,&tm) || tm.tm_year< -1899 || tm.tm_year>8099) {
        nc_write(b,"null"); return;
    }
    int length=snprintf(out,sizeof(out),"\"%04d-%02d-%02dT%02d:%02d:%02d.%03dZ\"",
        tm.tm_year+1900,tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec,(int)(fraction/1000));
    nc_write_n(b,out,(size_t)length);
}
static uint32_t get32(const unsigned char *p)
{ uint32_t v; memcpy(&v,p,4); return ntohl(v); }
void nc_text_array(nc_buffer *b,nc_result *r,int row,int col)
{
    nc_putc(b,'[');
    if (!nc_null(r,row,col)) {
        const unsigned char *p=(const unsigned char*)PQgetvalue(r,row,col);
        size_t length=(size_t)PQgetlength(r,row,col), pos=12;
        if (length>=12) {
            uint32_t dimensions=get32(p);
            if (dimensions==1 && length>=20) {
                uint32_t count=get32(p+12); pos=20;
                for (uint32_t i=0;i<count && pos+4<=length;++i) {
                    int32_t n=(int32_t)get32(p+pos); pos+=4;
                    if (i) nc_putc(b,',');
                    if (n<0) nc_write(b,"null");
                    else if ((size_t)n<=length-pos) {
                        nc_json_string(b,(unsigned char*)(p+pos),(size_t)n); pos+=(size_t)n;
                    } else break;
                }
            }
        }
    }
    nc_putc(b,']');
}
