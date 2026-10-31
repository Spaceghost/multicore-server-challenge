/* Benchmark the real HTTP parse -> JWT verification -> request release path.
 * Corpus tokens are independently signed by the Python driver. */
#define _GNU_SOURCE
#include "native.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct auth_case {
    char wire[8192];
    size_t length;
    int64_t expected;
} auth_case;

static auth_case cases[128];
static size_t case_count;

static uint64_t clock_ns(clockid_t clock)
{
    struct timespec now;
    if (clock_gettime(clock,&now)!=0) abort();
    return (uint64_t)now.tv_sec*1000000000U+(uint64_t)now.tv_nsec;
}

static uint64_t run(unsigned long iterations)
{
    uint64_t checksum=0;
    for (unsigned long i=0;i<iterations;++i) {
        auth_case *entry=&cases[(i*17)%case_count];
        nc_request *request=nc_request_create(entry->wire,entry->length);
        if (!request) abort();
        int64_t actual=nc_auth(request);
        if (actual!=entry->expected) abort();
        checksum+=(uint64_t)(actual+1);
        nc_request_free(request);
    }
    return checksum;
}

int main(int argc,char **argv)
{
    if (argc!=3) return 2;
    FILE *corpus=fopen(argv[1],"r");
    if (!corpus) return 2;
    char line[4096];
    while (fgets(line,sizeof(line),corpus)) {
        if (case_count==128) return 2;
        char *token=strchr(line,'\t');
        if (!token) return 2;
        *token++=0;
        token[strcspn(token,"\r\n")]=0;
        auth_case *entry=&cases[case_count++];
        entry->expected=strtoll(line,NULL,10);
        int length=snprintf(entry->wire,sizeof(entry->wire),
            "GET /api/articles?limit=20&offset=0 HTTP/1.1\r\n"
            "Host: localhost\r\nConnection: keep-alive\r\n%s%s%s"
            "Content-Length: 0\r\n\r\n",
            strcmp(token,"-")?"Authorization: Token ":"",
            strcmp(token,"-")?token:"",strcmp(token,"-")?"\r\n":"");
        if (length<0 || (size_t)length>=sizeof(entry->wire)) return 2;
        entry->length=(size_t)length;
    }
    fclose(corpus);
    unsigned long iterations=strtoul(argv[2],NULL,10);
    if (!case_count || !iterations) return 2;
    (void)run(2048);
    uint64_t wall=clock_ns(CLOCK_MONOTONIC);
    uint64_t cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID);
    uint64_t checksum=run(iterations);
    cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID)-cpu;
    wall=clock_ns(CLOCK_MONOTONIC)-wall;
    printf("{\"iterations\":%lu,\"cpu_ns\":%.2f,\"wall_ns\":%.2f,\"checksum\":%" PRIu64 "}\n",
        iterations,(double)cpu/iterations,(double)wall/iterations,checksum);
    return 0;
}
