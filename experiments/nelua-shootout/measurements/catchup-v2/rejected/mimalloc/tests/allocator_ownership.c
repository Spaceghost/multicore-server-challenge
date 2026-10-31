/* Light ownership smoke: parse on one thread, allocate responses on another,
 * free after the allocating worker has exited. Shared libraries keep libc. */
#define _GNU_SOURCE
#include "native.h"
#include <assert.h>
#include <libpq-fe.h>
#include <mimalloc.h>
#include <openssl/crypto.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

static nc_request *requests[128];

static void *worker(void *argument)
{
    size_t lane=(size_t)argument;
    for (size_t i=lane;i<128;i+=8) {
        nc_request *request=requests[i];
        assert(nc_auth(request)==42);
        char *token=nc_issue_token(request,42);
        assert(token && mi_is_in_heap_region(token));
        nc_buffer *buffer=nc_begin(request,200);
        for (unsigned j=0;j<1000;++j) nc_write(buffer,"{\"article\":\"bounded response text\"}");
        size_t length=0;
        const char *response=nc_response_data(request,&length);
        assert(length==35000 && mi_is_in_heap_region(response));
    }
    return NULL;
}

int main(void)
{
    assert(setenv("JWT_SECRET","allocator-ownership-smoke",1)==0);
    void *crypto=OPENSSL_malloc(1000);
    assert(crypto && !mi_is_in_heap_region(crypto));
    OPENSSL_free(crypto);
    char *error=NULL;
    PQconninfoOption *options=PQconninfoParse("host=127.0.0.1 dbname=test",&error);
    assert(options && !error && !mi_is_in_heap_region(options));
    PQconninfoFree(options);
    static const char empty[]="GET /api/tags HTTP/1.1\r\nHost: test\r\n\r\n";
    nc_request *issuer=nc_request_create(empty,sizeof(empty)-1);
    assert(issuer && mi_is_in_heap_region(issuer));
    char *token=nc_issue_token(issuer,42);
    assert(token);
    char wire[1024];
    int length=snprintf(wire,sizeof(wire),
        "GET /api/user HTTP/1.1\r\nHost: test\r\nAuthorization: Token %s\r\n\r\n",token);
    assert(length>0 && (size_t)length<sizeof(wire));
    for (size_t i=0;i<128;++i) {
        requests[i]=nc_request_create(wire,(size_t)length);
        assert(requests[i] && mi_is_in_heap_region(requests[i]));
    }
    pthread_t threads[8];
    for (size_t i=0;i<8;++i) assert(pthread_create(&threads[i],NULL,worker,(void *)i)==0);
    for (size_t i=0;i<8;++i) assert(pthread_join(threads[i],NULL)==0);
    for (size_t i=0;i<128;++i) nc_request_free(requests[i]);
    nc_request_free(issuer);
    mi_collect(true);
    puts("PASS: app-owned requests/responses use mimalloc, foreign library heaps stay separate, cross-thread free after worker exit");
    return 0;
}
