// Our output adapter. All scientific values come from the original mk_order.
#include "native_api.h"
#include "native_sampling.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include <io.h>
using namespace std;
namespace {
struct C {int city=0,nation=0,region=0;};
struct P {int mfgr=0,category=0,brand=0;};
struct D {int year=0,ym=0,week=0,month=0;};
vector<C> customers(1),suppliers(1); vector<P> parts(1); vector<D> dates(62000);
unordered_map<string,int> ids; vector<string> labels(1,"");
unordered_map<uint64_t,__int128> totals[13];
uint64_t rows=0,kept=0,seed=0;ssb_selection selection;
FILE *sample=nullptr;
int america,asia,europe,usa,uk1,uk5,cat12,cat14,mfgr1,mfgr2,brand2221,dec1997;
array<int,8> brands;
vector<string> split(string text,char separator) {
    if(!text.empty() && text.back()=='\r') text.pop_back();
    vector<string> fields; string field; istringstream in(text);
    while(getline(in,field,separator)) fields.push_back(field);
    return fields;
}
int code(const string &text) {
    auto it=ids.find(text); if(it!=ids.end()) return it->second;
    if(labels.size()>=65536) throw runtime_error("Label dictionary exceeds packed key limit");
    int result=(int)labels.size();labels.push_back(text);ids[text]=result;return result;
}
void load_dimensions(const string &directory) {
    for(string table:{"customer","supplier","part","date"}) {
        ifstream in(directory+"/"+table+".tbl"); if(!in) throw runtime_error("Missing dimension "+table);
        string line; uint64_t expected=1;
        while(getline(in,line)) {
            auto f=split(line,'|');size_t key=stoull(f.at(0));
            if(table!="date" && key!=expected++) throw runtime_error("Dimension key is not contiguous");
            if(table=="customer" || table=="supplier") {
                auto &v=table=="customer"?customers:suppliers;
                v.push_back({code(f.at(3)),code(f.at(4)),code(f.at(5))});
            } else if(table=="part") parts.push_back({code(f.at(2)),code(f.at(3)),code(f.at(4))});
            else {
                if(key<19920101 || key-19920101>=dates.size()) throw runtime_error("Date outside bounded index");
                dates[key-19920101]={stoi(f.at(4)),stoi(f.at(5)),stoi(f.at(11)),code(f.at(6))};
            }
        }
    }
    america=code("AMERICA");asia=code("ASIA");europe=code("EUROPE");usa=code("UNITED STATES");
    uk1=code("UNITED KI1");uk5=code("UNITED KI5");cat12=code("MFGR#12");cat14=code("MFGR#14");
    mfgr1=code("MFGR#1");mfgr2=code("MFGR#2");brand2221=code("MFGR#2221");dec1997=code("Dec1997");
    for(int i=0;i<8;++i) brands[i]=code("MFGR#222"+to_string(i+1));
}
uint64_t key(int a=0,int b=0,int c=0) {return (uint64_t)a|((uint64_t)b<<16)|((uint64_t)c<<32);}
void add(int q,uint64_t group,int64_t amount) {totals[q][group]+=(__int128)amount;}
string decimal(__int128 n) {
    if(n==0) return "0";bool negative=n<0;if(negative)n=-n;string s;
    while(n){s.push_back('0'+(int)(n%10));n/=10;}if(negative)s.push_back('-');reverse(s.begin(),s.end());return s;
}
void durable(FILE *file) {
    if(fflush(file) || _commit(_fileno(file))) throw runtime_error("Output flush/fsync failed");
}
void emit_sample(const v2_fact &f) {
    // Explicitly reproduce the measured LP64 legacy eleven-byte priority.
    if(fprintf(sample,"%llu|%d|%lld|%lld|%lld|%s|%.*s|%lld|%lld|%lld|%lld|%lld|%lld|%lld|%lld|%s|%s\n",
        (unsigned long long)f.orderkey,f.linenumber,(long long)f.custkey,(long long)f.partkey,(long long)f.suppkey,
        f.orderdate,11,f.priority,(long long)f.ship_priority,(long long)f.quantity,(long long)f.extended_price,
        (long long)f.order_totalprice,(long long)f.discount,(long long)f.revenue,(long long)f.supplycost,
        (long long)f.tax,f.commitdate,f.shipmode)<0) throw runtime_error("Sample formatting failed");
}
void consume(const vector<string> &args) {
    if(args.size()!=5) throw runtime_error("Expected first order, order count, chunk directory, seed, probability");
    int64_t first=stoll(args[0]),count=stoll(args[1]);string home=args[2];seed=stoull(args[3]);
    selection=ssb_parse_selection(args[4]);rows=kept=0;for(auto &q:totals)q.clear();
    sample=fopen((home+"/sample.csv").c_str(),"wb");if(!sample)throw runtime_error("Cannot create sample");
    if(v2_generate(first,count))throw runtime_error("Original generation failed");
    durable(sample);if(fclose(sample))throw runtime_error("Sample close failed");sample=nullptr;
    FILE *truth=fopen((home+"/aggregates.tsv").c_str(),"wb");if(!truth)throw runtime_error("Cannot create truth");
    for(int q=0;q<13;++q) {
        map<vector<string>,__int128> sorted;
        for(auto &item:totals[q]) {
            int a=(int)(item.first&65535),b=(int)((item.first>>16)&65535),c=(int)((item.first>>32)&65535);vector<string> fields;
            if(q>=3 && q<=5)fields={to_string(a),labels.at(b)};
            else if(q>=6 && q<=9)fields={labels.at(a),labels.at(b),to_string(c)};
            else if(q==10)fields={to_string(a),labels.at(b)};
            else if(q>=11)fields={to_string(a),labels.at(b),labels.at(c)};
            sorted[fields]=item.second;
        }
        // SQL SUM over an empty relation is represented by no aggregate row.
        for(auto &item:sorted){fprintf(truth,"%d",q);for(auto &f:item.first)fprintf(truth,"\t%s",f.c_str());fprintf(truth,"\t%s\n",decimal(item.second).c_str());}
    }
    durable(truth);fclose(truth);
    if(v2_dump_seeds((home+"/seeds_after.tsv").c_str()))throw runtime_error("Seed receipt failed");
    FILE *stats=fopen((home+"/stats.json").c_str(),"wb");if(!stats)throw runtime_error("Cannot create stats");
    fprintf(stats,"{\"rows\":%llu,\"sample_rows\":%llu,\"unmatched_foreign_keys\":0,\"total_orders\":%lld}\n",
        (unsigned long long)rows,(unsigned long long)kept,(long long)v2_total_orders());durable(stats);fclose(stats);
}
}
extern "C" int v2_process_fact(const v2_fact *row) {
    try {
        const auto &f=*row;
        int64_t day=atoll(f.orderdate)-19920101;
        if(f.custkey<=0||(uint64_t)f.custkey>=customers.size()||f.partkey<=0||(uint64_t)f.partkey>=parts.size()||
           f.suppkey<=0||(uint64_t)f.suppkey>=suppliers.size()||day<0||(uint64_t)day>=dates.size()||!dates[day].year)
            throw runtime_error("Unmatched dimension key");
        if(f.quantity<1||f.quantity>50)throw runtime_error("Quantity outside original RNG range");
        const C &c=customers[f.custkey],&s=suppliers[f.suppkey];const P &p=parts[f.partkey];const D &d=dates[day];
        if(d.year==1993&&f.discount>=1&&f.discount<=3&&f.quantity<25)add(0,0,f.extended_price*f.discount);
        if(d.ym==199401&&f.discount>=4&&f.discount<=6&&f.quantity>=26&&f.quantity<=35)add(1,0,f.extended_price*f.discount);
        if(d.week==6&&d.year==1994&&f.discount>=5&&f.discount<=7&&f.quantity>=26&&f.quantity<=35)add(2,0,f.extended_price*f.discount);
        if(p.category==cat12&&s.region==america)add(3,key(d.year,p.brand),f.revenue);
        if(find(brands.begin(),brands.end(),p.brand)!=brands.end()&&s.region==asia)add(4,key(d.year,p.brand),f.revenue);
        if(p.brand==brand2221&&s.region==europe)add(5,key(d.year,p.brand),f.revenue);
        if(c.region==asia&&s.region==asia&&d.year>=1992&&d.year<=1997)add(6,key(c.nation,s.nation,d.year),f.revenue);
        if(c.nation==usa&&s.nation==usa&&d.year>=1992&&d.year<=1997)add(7,key(c.city,s.city,d.year),f.revenue);
        bool selected=(c.city==uk1||c.city==uk5)&&(s.city==uk1||s.city==uk5);
        if(selected&&d.year>=1992&&d.year<=1997)add(8,key(c.city,s.city,d.year),f.revenue);
        if(selected&&d.month==dec1997)add(9,key(c.city,s.city,d.year),f.revenue);
        bool manufacturer=p.mfgr==mfgr1||p.mfgr==mfgr2;
        if(c.region==america&&s.region==america&&manufacturer)add(10,key(d.year,c.nation),f.revenue-f.supplycost);
        if(c.region==america&&s.region==america&&d.year>=1997&&d.year<=1998&&manufacturer)add(11,key(d.year,s.nation,p.category),f.revenue-f.supplycost);
        if(c.region==america&&s.nation==usa&&d.year>=1997&&d.year<=1998&&p.category==cat14)add(12,key(d.year,s.city,p.brand),f.revenue-f.supplycost);
        if(selection.keep(ssb_mix(seed^ssb_mix(f.orderkey)^ssb_mix((uint64_t)f.linenumber+UINT64_C(0xd1b54a32d192ed03))))){emit_sample(f);++kept;}
        ++rows;return 0;
    } catch(const exception &e){cerr<<e.what()<<endl;return 2;}
}
int main(int argc,char **argv) {
    try {
        if(argc!=4)throw runtime_error("Expected scale, distributions and dimension directory");
        if(v2_initialize(argv[1],argv[2]))throw runtime_error("Original generator initialization failed");
        load_dimensions(argv[3]);cout<<"READY"<<endl;string line;
        while(getline(cin,line)) {if(line=="QUIT")break;consume(split(line,'\t'));cout<<"OK"<<endl;}
        return 0;
    }catch(const exception &e){cerr<<e.what()<<endl;return 2;}
}
