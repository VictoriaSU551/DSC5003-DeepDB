// Independent output consumer. No dbgen random streams or generation rules change.
#include <cstdint>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
using namespace std;

vector<string> split(string line, char separator) {
    if (!line.empty() && line.back()=='\r') line.pop_back();
    vector<string> result; string field; istringstream input(line);
    while(getline(input,field,separator)) result.push_back(field);
    return result;
}
struct C {int city=0,nation=0,region=0;};
struct P {int mfgr=0,category=0,brand=0;};
struct D {int year=0,ym=0,week=0,month=0;};
vector<C> customers(1),suppliers(1); vector<P> parts(1); vector<D> dates(1);
unordered_map<string,int> ids; vector<string> labels(1,"");
int code(const string &s) {
    auto it=ids.find(s); if(it!=ids.end()) return it->second;
    int value=(int)labels.size(); ids[s]=value; labels.push_back(s); return value;
}
void load_dimensions(const string &directory) {
    for(string table:{"customer","supplier","part","date"}) {
        ifstream input(directory+"/"+table+".tbl"); if(!input) throw runtime_error("Missing dimension "+table);
        string line;
        while(getline(input,line)) {
            auto f=split(line,'|'); if(f.empty()) continue;
            size_t key=stoull(f[0]);
            if(table=="customer" || table=="supplier") {
                auto &rows=table=="customer"?customers:suppliers;
                if(rows.size()<=key) rows.resize(key+1);
                rows[key]={code(f.at(3)),code(f.at(4)),code(f.at(5))};
            } else if(table=="part") {
                if(parts.size()<=key) parts.resize(key+1);
                parts[key]={code(f.at(2)),code(f.at(3)),code(f.at(4))};
            } else {
                if(dates.size()<=key) dates.resize(key+1);
                dates[key]={stoi(f.at(4)),stoi(f.at(5)),stoi(f.at(11)),code(f.at(6))};
            }
        }
    }
}
uint64_t mix(uint64_t x) {
    x+=UINT64_C(0x9e3779b97f4a7c15);
    x=(x^(x>>30))*UINT64_C(0xbf58476d1ce4e5b9);
    x=(x^(x>>27))*UINT64_C(0x94d049bb133111eb);
    return x^(x>>31);
}
void consume(const vector<string> &command) {
    if(command.size()!=4) throw runtime_error("Expected raw path, output prefix, sample seed, probability");
    ifstream input(command[0]); if(!input) throw runtime_error("Missing raw shard");
    ofstream sample(command[1]+"/sample.csv",ios::binary);
    if(!sample) throw runtime_error("Cannot create sample");
    uint64_t seed=stoull(command[2]),rows=0,kept=0;
    long double probability=stold(command[3]);
    if(probability<0 || probability>1) throw runtime_error("Invalid sampling probability");
    long double threshold=probability*18446744073709551616.0L;
    map<vector<string>,int64_t> aggregates[13];
    int america=code("AMERICA"),asia=code("ASIA"),europe=code("EUROPE"),usa=code("UNITED STATES");
    int uk1=code("UNITED KI1"),uk5=code("UNITED KI5"),cat12=code("MFGR#12"),cat14=code("MFGR#14");
    int mfgr1=code("MFGR#1"),mfgr2=code("MFGR#2"),brand2221=code("MFGR#2221"),dec1997=code("Dec1997");
    vector<int> brands; for(int i=1;i<=8;i++) brands.push_back(code("MFGR#222"+to_string(i)));
    string line;
    while(getline(input,line)) {
        auto f=split(line,'|'); if(f.size()!=17) throw runtime_error("Expected 17 lineorder fields");
        uint64_t order=stoull(f[0]),number=stoull(f[1]);
        size_t ck=stoull(f[2]),pk=stoull(f[3]),sk=stoull(f[4]),dk=stoull(f[5]);
        if(ck==0 || ck>=customers.size() || pk==0 || pk>=parts.size() || sk==0 || sk>=suppliers.size() || dk>=dates.size() || dates[dk].year==0)
            throw runtime_error("Unmatched dimension key");
        const C &c=customers[ck],&s=suppliers[sk]; const P &p=parts[pk]; const D &d=dates[dk];
        int quantity=stoi(f[8]),discount=stoi(f[11]); int64_t extended=stoll(f[9]),revenue=stoll(f[12]),cost=stoll(f[13]);
        string year=to_string(d.year);
        if(d.year==1993 && discount>=1 && discount<=3 && quantity<25) aggregates[0][{}]+=extended*discount;
        if(d.ym==199401 && discount>=4 && discount<=6 && quantity>=26 && quantity<=35) aggregates[1][{}]+=extended*discount;
        if(d.week==6 && d.year==1994 && discount>=5 && discount<=7 && quantity>=26 && quantity<=35) aggregates[2][{}]+=extended*discount;
        if(p.category==cat12 && s.region==america) aggregates[3][{year,labels[p.brand]}]+=revenue;
        if(find(brands.begin(),brands.end(),p.brand)!=brands.end() && s.region==asia) aggregates[4][{year,labels[p.brand]}]+=revenue;
        if(p.brand==brand2221 && s.region==europe) aggregates[5][{year,labels[p.brand]}]+=revenue;
        if(c.region==asia && s.region==asia && d.year>=1992 && d.year<=1997) aggregates[6][{labels[c.nation],labels[s.nation],year}]+=revenue;
        if(c.nation==usa && s.nation==usa && d.year>=1992 && d.year<=1997) aggregates[7][{labels[c.city],labels[s.city],year}]+=revenue;
        bool selected_city=(c.city==uk1 || c.city==uk5) && (s.city==uk1 || s.city==uk5);
        if(selected_city && d.year>=1992 && d.year<=1997) aggregates[8][{labels[c.city],labels[s.city],year}]+=revenue;
        if(selected_city && d.month==dec1997) aggregates[9][{labels[c.city],labels[s.city],year}]+=revenue;
        bool mfgr=p.mfgr==mfgr1 || p.mfgr==mfgr2;
        if(c.region==america && s.region==america && mfgr) aggregates[10][{year,labels[c.nation]}]+=revenue-cost;
        if(c.region==america && s.region==america && d.year>=1997 && d.year<=1998 && mfgr) aggregates[11][{year,labels[s.nation],labels[p.category]}]+=revenue-cost;
        if(c.region==america && s.nation==usa && d.year>=1997 && d.year<=1998 && p.category==cat14) aggregates[12][{year,labels[s.city],labels[p.brand]}]+=revenue-cost;
        uint64_t selection=mix(seed^mix(order)^mix(number+UINT64_C(0xd1b54a32d192ed03)));
        if((long double)selection<threshold) {
            if(!line.empty() && line.back()=='\r') line.pop_back();
            if(!line.empty() && line.back()=='|') line.pop_back();
            sample<<line<<'\n'; ++kept;
        }
        ++rows;
    }
    sample.flush(); if(!sample) throw runtime_error("Sample write failed");
    ofstream truth(command[1]+"/aggregates.tsv",ios::binary);
    for(int q=0;q<13;q++) for(const auto &group:aggregates[q]) {
        truth<<q; for(const string &key:group.first) truth<<'\t'<<key;
        truth<<'\t'<<group.second<<'\n';
    }
    truth.flush(); if(!truth) throw runtime_error("Aggregate write failed");
    ofstream stats(command[1]+"/stats.json");
    stats<<"{\"rows\":"<<rows<<",\"sample_rows\":"<<kept<<",\"unmatched_foreign_keys\":0}\n";
    stats.flush(); if(!stats) throw runtime_error("Stats write failed");
}
int main(int argc,char **argv) {
    try {
        if(argc!=2) throw runtime_error("Expected dimension directory");
        load_dimensions(argv[1]); cout<<"READY"<<endl;
        string line;
        while(getline(cin,line)) {
            if(line=="QUIT") break;
            try {consume(split(line,'\t'));cout<<"OK"<<endl;}
            catch(const exception &e) {cout<<"ERROR\t"<<e.what()<<endl;return 2;}
        }
        return 0;
    } catch(const exception &e) {cerr<<e.what()<<endl;return 1;}
}
