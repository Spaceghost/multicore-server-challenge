/* This file is force-included only while compiling this application's sources.
 * Shared libpq/OpenSSL/libxcrypt and mimalloc itself retain their own allocators.
 * Include libc's declarations before the four supported source-level redirects. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdlib.h>
#include <mimalloc.h>
#define malloc(n) mi_malloc(n)
#define calloc(c,n) mi_calloc(c,n)
#define realloc(p,n) mi_realloc(p,n)
#define free(p) mi_free(p)
