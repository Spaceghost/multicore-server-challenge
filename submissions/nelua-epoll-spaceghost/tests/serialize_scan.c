/* Independent scalar oracle plus ASan boundaries for the Nelua word scanner. */
#include "native.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static unsigned long long state=0xd827ec109aULL;
static unsigned random_byte(void)
{
    state^=state<<13; state^=state>>7; state^=state<<17;
    return (unsigned)(state&255);
}
static size_t reference(char *out,const unsigned char *in,size_t n)
{
    static const char hex[]="0123456789abcdef";
    size_t w=0; out[w++]='"';
    for (size_t i=0;i<n;++i) {
        unsigned c=in[i];
        if (c<32) {
            memcpy(out+w,"\\u00",4); w+=4;
            out[w++]=hex[c/16]; out[w++]=hex[c%16];
        } else {
            if (c=='"' || c=='\\') out[w++]='\\';
            out[w++]=(char)c;
        }
    }
    out[w++]='"'; return w;
}
static void check(const unsigned char *data,size_t n)
{
    static const char wire[]="GET /api/tags HTTP/1.1\r\nHost: test\r\n\r\n";
    nc_request *r=nc_request_create(wire,sizeof(wire)-1);
    assert(r);
    char *want=malloc(6*n+2); assert(want);
    size_t expected=reference(want,data,n), length;
    nc_json_string(nc_begin(r,200),(unsigned char *)data,n);
    const char *body=nc_response_data(r,&length);
    assert(nc_status(r)==200 && length==expected && !memcmp(body,want,length));
    free(want); nc_request_free(r);
}
int main(int argc,char **argv)
{
    if (argc>1) {
        unsigned loops=(unsigned)strtoul(argv[1],NULL,10);
        static const char wire[]="GET /api/tags HTTP/1.1\r\nHost: test\r\n\r\n";
        nc_request *r=nc_request_create(wire,sizeof(wire)-1); assert(r);
        unsigned char text[4096];
        for (unsigned kind=0;kind<3;++kind) {
            memset(text,'x',sizeof(text));
            if (kind==1) for (unsigned i=0;i<sizeof(text);i+=43) text[i]='\n';
            if (kind==2) for (unsigned i=0;i+2<sizeof(text);i+=3) {
                text[i]=0xe9; text[i+1]=0x9b; text[i+2]=0xaa;
            }
            struct timespec begin,end;
            clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&begin);
            for (unsigned i=0;i<loops;++i) nc_json_string(nc_begin(r,200),text,sizeof(text));
            clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&end);
            double elapsed=(double)(end.tv_sec-begin.tv_sec)+(double)(end.tv_nsec-begin.tv_nsec)/1e9;
            printf("BENCH kind=%u loops=%u cpu_seconds=%.6f MiB_per_second=%.2f\n",
                   kind,loops,elapsed,(double)loops*sizeof(text)/1048576/elapsed);
        }
        nc_request_free(r); return 0;
    }
    /* Every byte at every position across several word/tail boundaries. */
    unsigned char input[72];
    for (unsigned n=0;n<sizeof(input);++n) {
        for (unsigned pos=0;pos<n;++pos) for (unsigned c=0;c<256;++c) {
            memset(input,'x',n); input[pos]=(unsigned char)c;
            check(input,n);
        }
    }
    /* malloc's exact trailing ASan boundary catches any final-word overread;
     * prefix offsets exercise each possible input alignment. */
    for (unsigned n=0;n<2048;n+=7) for (unsigned alignment=0;alignment<8;++alignment) {
        unsigned char *allocation=malloc(n+alignment+1); assert(allocation);
        unsigned char *data=allocation+alignment+1;
        for (unsigned i=0;i<n;++i) data[i]=(unsigned char)random_byte();
        check(data,n); free(allocation);
    }
    puts("PASS: all 256 byte values at every position, tails, unaligned ranges and exact allocation boundaries");
    return 0;
}
