/* Self-written adapter: pristine seeds, nonnegative skip, original gen_tbl. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dss.h"
#include "dsstypes.h"
#include "native_api.h"
int ssb_original_main(int, char **);
void gen_tbl(int, long, long, long);
long sd_order(int, long);
long sd_line(int, long);
int pr_line(order_t *, int);
extern seed_t Seed[MAX_STREAM + 1];
extern long scale;
static seed_t pristine[MAX_STREAM + 1];
static int initialized;

static int no_date_output(void *row, int mode) { return 0; }

static int fact_output(order_t *order, int mode)
{
    long i;
    for (i=0; i<order->lines; ++i) {
        const lineorder_t *line=&order->lineorders[i];
        v2_fact view;
        view.orderkey=(uint64_t)*line->okey;
        view.linenumber=line->linenumber;
        view.custkey=line->custkey; view.partkey=line->partkey; view.suppkey=line->suppkey;
        view.orderdate=line->orderdate; view.priority=line->opriority;
        view.ship_priority=line->ship_priority; view.quantity=line->quantity;
        view.extended_price=line->extended_price; view.order_totalprice=line->order_totalprice;
        view.discount=line->discount; view.revenue=line->revenue; view.supplycost=line->supp_cost;
        view.tax=line->tax; view.commitdate=line->commit_date; view.shipmode=line->shipmode;
        if(v2_process_fact(&view)) { fprintf(stderr,"Native callback rejected a fact\n"); exit(2); }
    }
    return 0;
}

int v2_initialize(const char *scale_argument, const char *distributions)
{
    char *arguments[10];
    if(initialized) return 2;
    memcpy(pristine,Seed,sizeof(pristine));
    tdefs[DATE].loader[0]=(int (*)())no_date_output;
    arguments[0]="native-v2-init"; arguments[1]="-s"; arguments[2]=(char *)scale_argument;
    arguments[3]="-T"; arguments[4]="d"; arguments[5]="-f";
    arguments[6]="-b"; arguments[7]=(char *)distributions; arguments[8]="-q"; arguments[9]=NULL;
    if(ssb_original_main(9,arguments)) return 3;
    /* DATE aliases ORDER. Restore the exact initial structs, rather than
       asking NthElement for a negative count or changing any random stream. */
    memcpy(Seed,pristine,sizeof(pristine));
    table=1<<LINE;
    tdefs[LINE].loader[0]=(int (*)())fact_output;
    initialized=1;
    return 0;
}

int64_t v2_total_orders(void) { return (int64_t)tdefs[LINE].base*(int64_t)scale; }

#ifdef V2_DIRECT_SEED_REFERENCE
static uint64_t modular_power(uint64_t exponent)
{
    uint64_t value=1,base=16807;
    while(exponent) {
        if(exponent&1) value=value*base%2147483647;
        exponent>>=1; base=base*base%2147483647;
    }
    return value;
}
#endif

int v2_generate(int64_t first_order,int64_t orders)
{
    long skipped;
    if(!initialized || first_order<1 || orders<1 || first_order-1+orders>v2_total_orders()) return 2;
    memcpy(Seed,pristine,sizeof(pristine));
    skipped=(long)(first_order-1);
#ifdef V2_DIRECT_SEED_REFERENCE
    {
        int i;
        /* Independent LP64 oracle: mathematical per-stream stride. Valid
           SSBM ORDER streams use one call/order, LINE streams use seven. */
        for(i=0;i<=MAX_STREAM;++i)
            if(Seed[i].table==ORDER || Seed[i].table==LINE) {
                uint64_t calls=(uint64_t)skipped*(uint64_t)Seed[i].boundary;
                Seed[i].value=(long)((uint64_t)pristine[i].value*modular_power(calls)%2147483647);
            }
    }
#else
    sd_order(0,skipped); sd_line(0,skipped);
#endif
#ifdef V2_STOCK_PRINTER_REFERENCE
    tdefs[LINE].loader[0]=(int (*)())pr_line;
#endif
    gen_tbl(LINE,(long)first_order,(long)orders,0);
    if(fflush(NULL)) return 3;
    return 0;
}

int v2_dump_seeds(const char *path)
{
    int i; FILE *out=fopen(path,"wb");
    if(!out) return 2;
    for(i=0;i<=MAX_STREAM;++i)
        fprintf(out,"%d\t%lld\t%lld\t%lld\t%lld\n",i,(long long)Seed[i].table,
                (long long)Seed[i].value,(long long)Seed[i].usage,(long long)Seed[i].boundary);
    return fclose(out)?3:0;
}

#ifdef V2_STOCK_PRINTER_REFERENCE
int v2_process_fact(const v2_fact *fact) { return 0; }
int main(int argc,char **argv)
{
    int result;
    if(argc!=5) return 2;
    if(v2_initialize(argv[1],argv[2])) return 3;
    result=v2_generate(atoll(argv[3]),atoll(argv[4]));
    if(result) return result;
    return v2_dump_seeds("seeds_after.tsv");
}
#endif
