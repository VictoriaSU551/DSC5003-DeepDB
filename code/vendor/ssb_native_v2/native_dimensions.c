/* Our dimension-only entry preserves the stock -T a P,S,C,D sequence. */
#include <stdio.h>
#include <stdlib.h>
#include "dss.h"
int ssb_original_main(int,char **);
void gen_tbl(int,long,long,long);
extern long scale;
extern seed_t Seed[MAX_STREAM+1];
static void snapshot(FILE *out,int table_id) {
    int i;
    for(i=0;i<=MAX_STREAM;++i)
        fprintf(out,"%d\t%d\t%lld\t%lld\t%lld\t%lld\n",table_id,i,(long long)Seed[i].table,
                (long long)Seed[i].value,(long long)Seed[i].usage,(long long)Seed[i].boundary);
}
int main(int argc,char **argv) {
    char *args[9];FILE *out;
    if(argc!=3||atol(argv[1])<1||atol(argv[1])>500)return 2;
    args[0]="native-v2-dimensions";args[1]="-s";args[2]=argv[1];args[3]="-T";args[4]="p";
    args[5]="-f";args[6]="-b";args[7]=argv[2];args[8]=NULL;
    if(ssb_original_main(8,args))return 3;
    out=fopen("dimension_seeds.tsv","wb");if(!out)return 4;
    snapshot(out,PART);
    gen_tbl(SUPP,1,tdefs[SUPP].base*scale,0);snapshot(out,SUPP);
    gen_tbl(CUST,1,tdefs[CUST].base*scale,0);snapshot(out,CUST);
    gen_tbl(DATE,1,tdefs[DATE].base,0);snapshot(out,DATE);
    if(fclose(out)||fflush(NULL))return 5;return 0;
}
