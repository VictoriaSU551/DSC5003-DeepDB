/* Self-written output bridge. Stock structs and RNG stay in the C generator. */
#ifndef SSB_NATIVE_V2_API_H
#define SSB_NATIVE_V2_API_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint64_t orderkey;
    int linenumber;
    int64_t custkey, partkey, suppkey;
    const char *orderdate, *priority;
    int64_t ship_priority, quantity, extended_price, order_totalprice;
    int64_t discount, revenue, supplycost, tax;
    const char *commitdate, *shipmode;
} v2_fact;
int v2_initialize(const char *scale_argument, const char *distributions);
int64_t v2_total_orders(void);
int v2_generate(int64_t first_order, int64_t orders);
int v2_dump_seeds(const char *path);
int v2_process_fact(const v2_fact *fact);
#ifdef __cplusplus
}
#endif
#endif
