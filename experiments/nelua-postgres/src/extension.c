/* PostgreSQL ABI, binary Datum access, and memory contexts. JSON is Nelua. */
#include "postgres.h"
#include "fmgr.h"
#include "miscadmin.h"
#include "executor/spi.h"
#include "lib/stringinfo.h"
#include "mb/pg_wchar.h"
#include "utils/array.h"
#include "utils/builtins.h"
#include "utils/date.h"
#include "utils/memutils.h"
#include "utils/timestamp.h"
#include "catalog/pg_type_d.h"

#include "bridge.h"
#include "kernel.h"
#include "queries.h"

PG_MODULE_MAGIC;

struct nc_writer { StringInfoData buffer; };
struct nc_row {
    Datum values[13];
    bool nulls[13];
    text *texts[13];
};

typedef struct nc_query {
    const char *sql;
    int nargs;
    Oid types[4];
    SPIPlanPtr plan;
} nc_query;

#define QUERY(name, count, ...) \
    static nc_query name##_plan = {name, count, {__VA_ARGS__}, NULL}
QUERY(q_tags, 0, 0);
QUERY(q_profile, 2, INT8OID, TEXTOID);
QUERY(q_article, 2, INT8OID, TEXTOID);
QUERY(q_article_by_id, 2, INT8OID, INT8OID);
QUERY(q_list_all, 3, INT8OID, INT4OID, INT4OID);
QUERY(q_list_tag, 4, INT8OID, INT4OID, INT4OID, TEXTOID);
QUERY(q_list_author, 4, INT8OID, INT4OID, INT4OID, TEXTOID);
QUERY(q_list_favorited, 4, INT8OID, INT4OID, INT4OID, TEXTOID);
QUERY(q_list_feed, 3, INT8OID, INT4OID, INT4OID);
QUERY(q_count_all, 0, 0);
QUERY(q_count_tag, 1, TEXTOID);
QUERY(q_count_author, 1, TEXTOID);
QUERY(q_count_favorited, 1, TEXTOID);
QUERY(q_count_feed, 1, INT8OID);
QUERY(q_comments, 2, INT8OID, TEXTOID);
QUERY(q_article_id, 1, TEXTOID);
QUERY(q_favorite_insert, 2, INT8OID, INT8OID);
QUERY(q_favorite_delete, 2, INT8OID, INT8OID);
QUERY(q_user_profile, 1, TEXTOID);
QUERY(q_follow_insert, 2, INT8OID, INT8OID);
QUERY(q_follow_delete, 2, INT8OID, INT8OID);
#undef QUERY

void
nc_write(nc_writer *writer, const char *data, size_t length)
{
    StringInfo buffer = &writer->buffer;
    if (length > MaxAllocSize)
        ereport(ERROR, (errcode(ERRCODE_PROGRAM_LIMIT_EXCEEDED),
                        errmsg("JSON output is too large")));
    /* Inline the common append path across the Nelua/C boundary under LTO. */
    if (length >= (size_t) (buffer->maxlen - buffer->len))
        enlargeStringInfo(buffer, (int) length);
    memcpy(buffer->data + buffer->len, data, length);
    buffer->len += (int) length;
    buffer->data[buffer->len] = '\0';
}

void
nc_putc(nc_writer *writer, char value)
{
    appendStringInfoCharMacro(&writer->buffer, value);
}

bool nc_isnull(nc_row *row, int column) { return row->nulls[column]; }
int64_t nc_int64(nc_row *row, int column) { return DatumGetInt64(row->values[column]); }
bool nc_bool(nc_row *row, int column) { return DatumGetBool(row->values[column]); }

static text *
nc_gettext(nc_row *row, int column)
{
    if (row->texts[column] == NULL)
        row->texts[column] = DatumGetTextPP(row->values[column]);
    return row->texts[column];
}

unsigned char *
nc_text_data(nc_row *row, int column)
{
    return (unsigned char *) VARDATA_ANY(nc_gettext(row, column));
}

size_t
nc_text_length(nc_row *row, int column)
{
    return VARSIZE_ANY_EXHDR(nc_gettext(row, column));
}

void
nc_timestamp(nc_writer *writer, nc_row *row, int column)
{
    TimestampTz value = DatumGetTimestampTz(row->values[column]);
    struct pg_tm tm;
    fsec_t fraction;
    char formatted[32];
    int length;

    /* A NULL timezone argument decodes the absolute timestamp as UTC. */
    if (TIMESTAMP_NOT_FINITE(value) ||
        timestamp2tm(value, NULL, &tm, &fraction, NULL, NULL) != 0 ||
        tm.tm_year < 1 || tm.tm_year > 9999)
        ereport(ERROR, (errcode(ERRCODE_DATETIME_VALUE_OUT_OF_RANGE),
                        errmsg("timestamp cannot be represented as RFC 3339")));
    length = snprintf(formatted, sizeof(formatted),
                      "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ",
                      tm.tm_year, tm.tm_mon, tm.tm_mday,
                      tm.tm_hour, tm.tm_min, tm.tm_sec, (int) fraction / 1000);
    nc_json_string(writer, (unsigned char *) formatted, length);
}

void
nc_text_array(nc_writer *writer, nc_row *row, int column)
{
    ArrayType *array = DatumGetArrayTypeP(row->values[column]);
    ArrayIterator iterator = array_create_iterator(array, 0, NULL);
    Datum value;
    bool isnull;
    bool first = true;

    nc_putc(writer, '[');
    while (array_iterate(iterator, &value, &isnull)) {
        text *item;
        if (!first) nc_putc(writer, ',');
        first = false;
        if (isnull) {
            nc_json_null(writer);
            continue;
        }
        item = DatumGetTextPP(value);
        nc_json_string(writer, (unsigned char *) VARDATA_ANY(item),
                       VARSIZE_ANY_EXHDR(item));
        if ((Pointer) item != DatumGetPointer(value)) pfree(item);
    }
    array_free_iterator(iterator);
    if ((Pointer) array != DatumGetPointer(row->values[column])) pfree(array);
    nc_putc(writer, ']');
}

static void
nc_loadrow(nc_row *row, SPITupleTable *table, uint64 index)
{
    memset(row, 0, sizeof(*row));
    Assert(table->tupdesc->natts <= 13);
    heap_deform_tuple(table->vals[index], table->tupdesc, row->values, row->nulls);
}

static void
nc_freerow(nc_row *row)
{
    int i;
    for (i = 0; i < 13; ++i)
        if (row->texts[i] && (Pointer) row->texts[i] != DatumGetPointer(row->values[i]))
            pfree(row->texts[i]);
}

static void
nc_begin(nc_writer *writer)
{
    if (GetDatabaseEncoding() != PG_UTF8)
        ereport(ERROR, (errcode(ERRCODE_FEATURE_NOT_SUPPORTED),
                        errmsg("nelua_conduit requires a UTF8 database")));
    if (SPI_connect() != SPI_OK_CONNECT)
        elog(ERROR, "cannot connect to SPI");
    initStringInfo(&writer->buffer);
}

static text *
nc_end(nc_writer *writer)
{
    text *result = SPI_palloc(VARHDRSZ + writer->buffer.len);
    SET_VARSIZE(result, VARHDRSZ + writer->buffer.len);
    memcpy(VARDATA(result), writer->buffer.data, writer->buffer.len);
    SPI_finish();
    return result;
}

static SPITupleTable *
nc_exec(nc_query *query, Datum *values, bool readonly)
{
    int status;
    if (!query->plan) {
        SPIPlanPtr plan = SPI_prepare(query->sql, query->nargs, query->types);
        if (!plan || SPI_keepplan(plan) != 0)
            elog(ERROR, "cannot prepare Nelua Conduit query");
        query->plan = plan;
    }
    status = SPI_execute_plan(query->plan, values, NULL, readonly, 0);
    if (status < 0)
        elog(ERROR, "Nelua Conduit query failed: %s", SPI_result_code_string(status));
    return SPI_tuptable;
}

static void
nc_viewer(int64 viewer, bool required)
{
    if (viewer < 0 || (required && viewer == 0))
        ereport(ERROR, (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                        errmsg("viewer must be %s", required ? "positive" : "nonnegative")));
}

static void
nc_pagination(int32 limit, int32 offset)
{
    if (limit < 1 || limit > 100 || offset < 0)
        ereport(ERROR, (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                        errmsg("limit must be 1..100 and offset must be nonnegative")));
}

#define LITERAL(writer, str) nc_write(writer, str, sizeof(str) - 1)

PG_FUNCTION_INFO_V1(nc_tags);
Datum
nc_tags(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    nc_row row;
    SPITupleTable *table;
    uint64 i, count;
    nc_begin(&writer);
    table = nc_exec(&q_tags_plan, NULL, true);
    count = SPI_processed;
    LITERAL(&writer, "{\"tags\":[");
    for (i = 0; i < count; ++i) {
        CHECK_FOR_INTERRUPTS();
        if (i) nc_putc(&writer, ',');
        nc_loadrow(&row, table, i);
        nc_json_string(&writer, nc_text_data(&row, 0), nc_text_length(&row, 0));
        nc_freerow(&row);
    }
    LITERAL(&writer, "]}");
    PG_RETURN_TEXT_P(nc_end(&writer));
}

static bool
nc_one(nc_writer *writer, nc_query *query, Datum *values, bool article, bool readonly)
{
    nc_row row;
    SPITupleTable *table = nc_exec(query, values, readonly);
    if (SPI_processed == 0) return false;
    nc_loadrow(&row, table, 0);
    if (article) {
        LITERAL(writer, "{\"article\":");
        nc_json_article(writer, &row, true);
    } else {
        LITERAL(writer, "{\"profile\":");
        nc_json_profile(writer, &row, 0);
    }
    nc_putc(writer, '}');
    nc_freerow(&row);
    return true;
}

PG_FUNCTION_INFO_V1(nc_profile);
Datum
nc_profile(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    Datum values[2] = {PG_GETARG_DATUM(1), PG_GETARG_DATUM(0)};
    nc_viewer(PG_GETARG_INT64(1), false);
    nc_begin(&writer);
    if (!nc_one(&writer, &q_profile_plan, values, false, true)) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    PG_RETURN_TEXT_P(nc_end(&writer));
}

PG_FUNCTION_INFO_V1(nc_article);
Datum
nc_article(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    Datum values[2] = {PG_GETARG_DATUM(1), PG_GETARG_DATUM(0)};
    nc_viewer(PG_GETARG_INT64(1), false);
    nc_begin(&writer);
    if (!nc_one(&writer, &q_article_plan, values, true, true)) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    PG_RETURN_TEXT_P(nc_end(&writer));
}

static text *
nc_page(nc_query *page, nc_query *count_query, Datum *values, Datum *count_values)
{
    nc_writer writer;
    nc_row row;
    SPITupleTable *table;
    uint64 i, count;
    nc_begin(&writer);
    table = nc_exec(page, values, true);
    count = SPI_processed;
    LITERAL(&writer, "{\"articles\":[");
    for (i = 0; i < count; ++i) {
        CHECK_FOR_INTERRUPTS();
        if (i) nc_putc(&writer, ',');
        nc_loadrow(&row, table, i);
        nc_json_article(&writer, &row, false);
        nc_freerow(&row);
    }
    SPI_freetuptable(table);
    table = nc_exec(count_query, count_values, true);
    nc_loadrow(&row, table, 0);
    LITERAL(&writer, "],\"articlesCount\":");
    nc_json_int64(&writer, nc_int64(&row, 0));
    nc_putc(&writer, '}');
    return nc_end(&writer);
}

/* NULL filters mean absent; empty strings are real filter values. */
PG_FUNCTION_INFO_V1(nc_articles);
Datum
nc_articles(PG_FUNCTION_ARGS)
{
    Datum values[4];
    nc_query *page = &q_list_all_plan;
    nc_query *count = &q_count_all_plan;
    Datum *count_values = NULL;
    int filter;
    if (PG_ARGISNULL(0) || PG_ARGISNULL(1) || PG_ARGISNULL(2))
        ereport(ERROR, (errcode(ERRCODE_NULL_VALUE_NOT_ALLOWED),
                        errmsg("viewer, limit, and offset cannot be NULL")));
    nc_viewer(PG_GETARG_INT64(0), false);
    nc_pagination(PG_GETARG_INT32(1), PG_GETARG_INT32(2));
    values[0] = PG_GETARG_DATUM(0);
    values[1] = PG_GETARG_DATUM(1);
    values[2] = PG_GETARG_DATUM(2);
    for (filter = 3; filter < 6; ++filter) {
        if (!PG_ARGISNULL(filter)) {
            values[3] = PG_GETARG_DATUM(filter);
            count_values = &values[3];
            if (filter == 3) { page = &q_list_tag_plan; count = &q_count_tag_plan; }
            else if (filter == 4) { page = &q_list_author_plan; count = &q_count_author_plan; }
            else { page = &q_list_favorited_plan; count = &q_count_favorited_plan; }
            break;
        }
    }
    PG_RETURN_TEXT_P(nc_page(page, count, values, count_values));
}

PG_FUNCTION_INFO_V1(nc_feed);
Datum
nc_feed(PG_FUNCTION_ARGS)
{
    Datum values[3] = {PG_GETARG_DATUM(0), PG_GETARG_DATUM(1), PG_GETARG_DATUM(2)};
    nc_viewer(PG_GETARG_INT64(0), true);
    nc_pagination(PG_GETARG_INT32(1), PG_GETARG_INT32(2));
    PG_RETURN_TEXT_P(nc_page(&q_list_feed_plan, &q_count_feed_plan, values, values));
}

PG_FUNCTION_INFO_V1(nc_comments);
Datum
nc_comments(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    nc_row row;
    Datum slug = PG_GETARG_DATUM(0);
    Datum values[2] = {PG_GETARG_DATUM(1), slug};
    SPITupleTable *table;
    uint64 i, count;
    nc_viewer(PG_GETARG_INT64(1), false);
    nc_begin(&writer);
    table = nc_exec(&q_article_id_plan, &slug, true);
    if (SPI_processed == 0) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    SPI_freetuptable(table);
    table = nc_exec(&q_comments_plan, values, true);
    count = SPI_processed;
    LITERAL(&writer, "{\"comments\":[");
    for (i = 0; i < count; ++i) {
        CHECK_FOR_INTERRUPTS();
        if (i) nc_putc(&writer, ',');
        nc_loadrow(&row, table, i);
        nc_json_comment(&writer, &row);
        nc_freerow(&row);
    }
    LITERAL(&writer, "]}");
    PG_RETURN_TEXT_P(nc_end(&writer));
}

PG_FUNCTION_INFO_V1(nc_favorite);
Datum
nc_favorite(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    nc_row row;
    Datum slug = PG_GETARG_DATUM(0);
    Datum values[2] = {PG_GETARG_DATUM(1), 0};
    SPITupleTable *table;
    nc_viewer(PG_GETARG_INT64(1), true);
    nc_begin(&writer);
    /* VOLATILE writes use fresh command snapshots, including their readback. */
    table = nc_exec(&q_article_id_plan, &slug, false);
    if (SPI_processed == 0) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    nc_loadrow(&row, table, 0);
    values[1] = row.values[0];
    SPI_freetuptable(table);
    nc_exec(PG_GETARG_BOOL(2) ? &q_favorite_insert_plan : &q_favorite_delete_plan, values, false);
    if (!nc_one(&writer, &q_article_by_id_plan, values, true, false)) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    PG_RETURN_TEXT_P(nc_end(&writer));
}

PG_FUNCTION_INFO_V1(nc_follow);
Datum
nc_follow(PG_FUNCTION_ARGS)
{
    nc_writer writer;
    nc_row row;
    Datum username = PG_GETARG_DATUM(0);
    Datum values[2] = {PG_GETARG_DATUM(1), 0};
    Datum readback[2] = {PG_GETARG_DATUM(1), username};
    SPITupleTable *table;
    nc_viewer(PG_GETARG_INT64(1), true);
    nc_begin(&writer);
    table = nc_exec(&q_user_profile_plan, &username, false);
    if (SPI_processed == 0) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    nc_loadrow(&row, table, 0);
    values[1] = row.values[0];
    SPI_freetuptable(table);
    nc_exec(PG_GETARG_BOOL(2) ? &q_follow_insert_plan : &q_follow_delete_plan, values, false);
    if (!nc_one(&writer, &q_profile_plan, readback, false, false)) {
        SPI_finish();
        PG_RETURN_NULL();
    }
    PG_RETURN_TEXT_P(nc_end(&writer));
}
