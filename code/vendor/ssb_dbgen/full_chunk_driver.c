/* Recovery adapter; upstream source and random generation functions stay intact.
 * Reproduce -T a's DATE/ORDER shared-stream prefix, then use upstream skip-ahead
 * functions for both order streams and line streams before calling gen_tbl.
 */
#include "dss.h"
#ifdef main
#undef main
#endif
int ssb_original_main(int, char **);
void gen_tbl(int, long, long, long);
long sd_order(int, long);
long sd_line(int, long);
int set_files(int, int);
extern long scale;

int main(int argc, char **argv)
{
    long total, per_shard, skipped, count;
    int shards, shard;
    char *primer[9];
    if (argc != 5) return 2;
    shards = atoi(argv[2]); shard = atoi(argv[3]);
    if(shards<1 || shard<1 || shard>shards || atol(argv[1])<1) return 2;
    primer[0]="dbgen-date-primer"; primer[1]="-s"; primer[2]=argv[1];
    primer[3]="-T"; primer[4]="d"; primer[5]="-f";
    primer[6]="-b"; primer[7]=argv[4]; primer[8]=NULL;
    if(ssb_original_main(8,primer)) return 3;
    total=tdefs[LINE].base*scale;
    per_shard=total/shards; skipped=per_shard*(shard-1);
    count=per_shard+(shard==shards?total%shards:0);
    sd_order(0,skipped);
    sd_line(0,skipped);
    table = 1 << LINE;
    if(set_files(LINE,shard)) return 4;
    gen_tbl(LINE,skipped+1,count,0);
    return 0;
}
