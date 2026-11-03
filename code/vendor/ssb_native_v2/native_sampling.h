// Output-only Bernoulli hash sampling; exact integer cutoff in [0,2^64].
#ifndef SSB_NATIVE_V2_SAMPLING_H
#define SSB_NATIVE_V2_SAMPLING_H
#include <cstdint>
#include <stdexcept>
#include <string>
struct ssb_selection {
    uint64_t cutoff=0;bool all=false;
    bool keep(uint64_t hash) const {return all || hash<cutoff;}
};
inline ssb_selection ssb_parse_selection(const std::string &text) {
    ssb_selection value;
    if(text=="ALL" || text=="1") {value.all=true;return value;}
    if(text=="0") return value;
    if(text.size()<2 || text[0]!='C') throw std::runtime_error("Use C<integer cutoff> or ALL; floating probability is forbidden");
    auto digits=text.substr(1);
    if(digits.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("Invalid integer sampling cutoff");
    size_t end=0;value.cutoff=std::stoull(digits,&end);
    if(end!=digits.size())throw std::runtime_error("Invalid integer sampling cutoff");
    return value;
}
inline uint64_t ssb_mix(uint64_t x) {
    x+=UINT64_C(0x9e3779b97f4a7c15);x=(x^(x>>30))*UINT64_C(0xbf58476d1ce4e5b9);
    x=(x^(x>>27))*UINT64_C(0x94d049bb133111eb);return x^(x>>31);
}
#endif
