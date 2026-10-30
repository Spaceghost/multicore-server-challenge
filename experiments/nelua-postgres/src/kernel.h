#ifndef NC_KERNEL_H
#define NC_KERNEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Defined by bridge.h. PostgreSQL owns the writer and its storage. */
typedef struct nc_writer nc_writer;

void nc_json_string(nc_writer *writer, unsigned char *data, size_t length);
void nc_json_int64(nc_writer *writer, int64_t value);
void nc_json_bool(nc_writer *writer, bool value);
void nc_json_null(nc_writer *writer);

typedef struct nc_row nc_row;
void nc_json_profile(nc_writer *writer, nc_row *row, int base);
void nc_json_article(nc_writer *writer, nc_row *row, bool full);
void nc_json_comment(nc_writer *writer, nc_row *row);

#endif
