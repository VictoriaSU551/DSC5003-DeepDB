// Audit harness: compile the exact production callback formatter, then bypass
// aggregation only. No giant dimension fixture is needed to audit high keys.
#define main unused_native_callback_main
#define v2_process_fact unused_full_aggregate_callback
#include "native_callback.cpp"
#undef main
#undef v2_process_fact
extern "C" int v2_process_fact(const v2_fact *fact) {
    try {emit_sample(*fact);return 0;}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 2;}
}
namespace {int run_probe(int argc,char **argv) {
    if(argc!=5)return 2;
    sample=fopen("lineorder.tbl","wb");if(!sample)return 3;
    if(v2_initialize(argv[1],argv[2]) || v2_generate(atoll(argv[3]),atoll(argv[4])))return 4;
    durable(sample);if(fclose(sample))return 5;return v2_dump_seeds("seeds_after.tsv");
}}
int main(int argc,char **argv) {return run_probe(argc,argv);}
