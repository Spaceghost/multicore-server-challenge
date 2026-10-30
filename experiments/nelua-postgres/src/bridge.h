#ifndef NC_BRIDGE_H
#define NC_BRIDGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* These are PostgreSQL-owned values, never Nelua heap objects. */
typedef struct nc_writer nc_writer;
typedef struct nc_row nc_row;

void nc_write(nc_writer *writer, const char *data, size_t length);
void nc_putc(nc_writer *writer, char value);
bool nc_isnull(nc_row *row, int column);
unsigned char *nc_text_data(nc_row *row, int column);
size_t nc_text_length(nc_row *row, int column);
int64_t nc_int64(nc_row *row, int column);
bool nc_bool(nc_row *row, int column);
void nc_timestamp(nc_writer *writer, nc_row *row, int column);
void nc_text_array(nc_writer *writer, nc_row *row, int column);

#endif
