/* Output adapter only: retain stock -T a's part, supplier, customer, date
 * sequence without generating the fact table. In particular gen_city shares
 * PART stream 0 and supplier phone generation advances C_PHNE_SD upstream.
 * No row construction, seed value, stream behavior or scaling formula changes.
 */
#include "dss.h"
#ifdef main
#undef main
#endif
int ssb_original_main(int, char **);
void gen_tbl(int, long, long, long);
extern long scale;

int main(int argc, char **argv)
{
    char *primer[9];
    if(argc != 3 || atol(argv[1]) < 1 || atol(argv[1]) > 500) return 2;
    primer[0]="dbgen-dimension-group"; primer[1]="-s"; primer[2]=argv[1];
    primer[3]="-T"; primer[4]="p"; primer[5]="-f";
    primer[6]="-b"; primer[7]=argv[2]; primer[8]=NULL;
    if(ssb_original_main(8,primer)) return 3;
    gen_tbl(SUPP,1,tdefs[SUPP].base*scale,0);
    gen_tbl(CUST,1,tdefs[CUST].base*scale,0);
    gen_tbl(DATE,1,tdefs[DATE].base,0);
    return 0;
}
