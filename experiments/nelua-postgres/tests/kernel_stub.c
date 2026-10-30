/* Test-only PostgreSQL boundary: the generated Nelua object is unchanged. */
#include "bridge.h"
#include "kernel.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

#define NC_TEST_BUFFER_SIZE 65536
#define NC_TEST_COLUMNS 16
struct nc_writer {
    char data[NC_TEST_BUFFER_SIZE];
    size_t length;
};
struct nc_test_cell {
    unsigned char *text;
    size_t length;
    int64_t integer;
    bool boolean;
    bool is_null;
};
struct nc_row {
    struct nc_test_cell columns[NC_TEST_COLUMNS];
};

void nc_write(nc_writer *writer, const char *data, size_t length)
{
    assert(writer->length + length < NC_TEST_BUFFER_SIZE);
    memcpy(writer->data + writer->length, data, length);
    writer->length += length;
    writer->data[writer->length] = '\0';
}
void nc_putc(nc_writer *writer, char value) { nc_write(writer, &value, 1); }
static struct nc_test_cell *cell(nc_row *row, int column)
{
    assert(column >= 0 && column < NC_TEST_COLUMNS);
    return &row->columns[column];
}
bool nc_isnull(nc_row *row, int column) { return cell(row, column)->is_null; }
unsigned char *nc_text_data(nc_row *row, int column) { return cell(row, column)->text; }
size_t nc_text_length(nc_row *row, int column) { return cell(row, column)->length; }
int64_t nc_int64(nc_row *row, int column) { return cell(row, column)->integer; }
bool nc_bool(nc_row *row, int column) { return cell(row, column)->boolean; }
/* Timestamp/array wire representations here are fixtures. PostgreSQL glue is
 * tested by integration tests; these stubs isolate Nelua field layout/order. */
void nc_timestamp(nc_writer *writer, nc_row *row, int column)
{
    nc_write(writer, (char *)cell(row, column)->text, cell(row, column)->length);
}
void nc_text_array(nc_writer *writer, nc_row *row, int column)
{
    nc_write(writer, (char *)cell(row, column)->text, cell(row, column)->length);
}

#ifdef NC_TEST_MAIN
static void check_integer(int64_t value)
{
    nc_writer writer = {{0}, 0};
    char expected[64];
    snprintf(expected, sizeof(expected), "%lld", (long long)value);
    nc_json_int64(&writer, value);
    assert(strcmp(writer.data, expected) == 0);
}
int main(void)
{
    const int64_t edges[] = {INT64_MIN, INT64_MIN + 1, -10, -1, 0, 1,
                             9, 10, INT64_MAX - 1, INT64_MAX};
    for (size_t i = 0; i < sizeof(edges)/sizeof(edges[0]); ++i)
        check_integer(edges[i]);
    uint64_t seed = 17;
    for (unsigned int i = 0; i < 100000; ++i) {
        seed = seed * UINT64_C(6364136223846793005) + 1;
        check_integer((int64_t)seed);
    }
    unsigned char bytes[256];
    for (unsigned int i = 0; i < 256; ++i) bytes[i] = (unsigned char)i;
    nc_writer writer = {{0}, 0};
    nc_json_string(&writer, bytes, sizeof(bytes));
    nc_json_string(&writer, NULL, 0);
    return 0;
}
#endif
