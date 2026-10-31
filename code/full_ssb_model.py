"""Bounded SSB preparation, independently compared with the original routine.

No dataset generation or SF500 training is performed by the default command.
"""
import argparse
import ast
from contextlib import contextmanager
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import re
import sqlite3
import subprocess
import time

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/full/ssb/models'
ORIGINAL=ROOT/'code/data_preparation/prepare_single_tables.py'
MAX_DISTINCT=10000
SQL_PATH=ROOT/'code/benchmarks/ssb/sql/aqp_queries.sql'
QUERY_NAMES=['S1.1','S1.2','S1.3','S2.1','S2.2','S2.3','S3.1','S3.2','S3.3','S3.4','S4.1','S4.2','S4.3']

# Independent consumer of the RETAINED fact sample. It does not invoke dbgen,
# sample new rows, change random streams, or modify the frozen native consumer.
CI_CPP=r'''
#include <cstdint>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
using namespace std;
vector<string> fields(string s,size_t n){
 if(!s.empty()&&s.back()=='\r')s.pop_back(); vector<string> v;size_t p=0;
 for(;;){size_t e=s.find('|',p);if(e==string::npos){v.push_back(s.substr(p));break;}v.push_back(s.substr(p,e-p));p=e+1;}
 if(v.size()==n+1&&v.back().empty())v.pop_back();if(v.size()!=n)throw runtime_error("Invalid raw field count");return v;
}
struct Number{bool has=false;int64_t value=0;};
Number number(const string&s){if(s.empty())return {};size_t p;int64_t x=stoll(s,&p);if(p!=s.size())throw runtime_error("Noninteger numeric field");return {true,x};}
string decimal(__int128 x){if(x==0)return "0";bool negative=x<0;if(negative)x=-x;string s;while(x){s.push_back('0'+x%10);x/=10;}if(negative)s.push_back('-');reverse(s.begin(),s.end());return s;}
unordered_map<string,uint16_t> codes;vector<string> labels(1,"\\N");
uint16_t code(const string&s){if(s.empty())return 0;if(s=="\\N"||s.find('\t')!=string::npos)throw runtime_error("Reserved categorical delimiter");auto i=codes.find(s);if(i!=codes.end())return i->second;if(labels.size()>=65535)throw runtime_error("Categorical budget exceeded");uint16_t x=labels.size();codes[s]=x;labels.push_back(s);return x;}
struct Customer{uint16_t city=0,nation=0,region=0;};
struct Part{uint16_t mfgr=0,category=0,brand=0;};
struct Date{Number year,ym,week;uint16_t month=0;};
vector<Customer> customers(1),suppliers(1);vector<Part> parts(1);unordered_map<int64_t,Date> dates;
void load_customer(const string&path,uint64_t expected,vector<Customer>&out,size_t width){
 out.reserve(expected+1);ifstream input(path);if(!input)throw runtime_error("Missing dimension");string line;
 while(getline(input,line)){auto f=fields(line,width);Number key=number(f[0]);if(!key.has||key.value!=(int64_t)out.size())throw runtime_error("Dimension PK not unique dense 1..N");out.push_back({code(f[3]),code(f[4]),code(f[5])});}
 if(out.size()!=expected+1)throw runtime_error("Dimension row count mismatch");
}
void load_part(const string&path,uint64_t expected){
 parts.reserve(expected+1);ifstream input(path);if(!input)throw runtime_error("Missing part");string line;
 while(getline(input,line)){auto f=fields(line,9);Number key=number(f[0]);if(!key.has||key.value!=(int64_t)parts.size())throw runtime_error("Part PK not unique dense");parts.push_back({code(f[2]),code(f[3]),code(f[4])});}
 if(parts.size()!=expected+1)throw runtime_error("Part row count mismatch");
}
void load_date(const string&path,uint64_t expected){
 ifstream input(path);if(!input)throw runtime_error("Missing date");string line;
 while(getline(input,line)){auto f=fields(line,17);Number key=number(f[0]);if(!key.has||key.value<=0||dates.count(key.value))throw runtime_error("Date PK duplicate/NULL");dates[key.value]={number(f[4]),number(f[5]),number(f[11]),code(f[6])};}
 if(dates.size()!=expected)throw runtime_error("Date row count mismatch");
}
struct Moment{uint64_t count=0,filtered=0,a=0,b=0;__int128 total=0,squares=0;
 void add(__int128 x,bool present=true,bool first=false,bool second=false){++filtered;if(first)++a;if(second)++b;if(!present)return;if(x>1000000000000LL||x<-1000000000000LL)throw runtime_error("Value outside proven 128bit moment bound");++count;total+=x;squares+=x*x;}
};
int main(int argc,char**argv){try{
 if(argc!=12)throw runtime_error("Expected four dimensions, fact sample, TSV output and five exact row counts");
 load_customer(argv[1],stoull(argv[7]),customers,8);load_customer(argv[2],stoull(argv[8]),suppliers,7);load_part(argv[3],stoull(argv[9]));load_date(argv[4],stoull(argv[10]));
 map<vector<string>,Moment> aggregates[13];for(int i=0;i<3;i++)aggregates[i][{}];
 int america=code("AMERICA"),asia=code("ASIA"),europe=code("EUROPE"),usa=code("UNITED STATES"),uk1=code("UNITED KI1"),uk5=code("UNITED KI5"),cat12=code("MFGR#12"),cat14=code("MFGR#14"),mfgr1=code("MFGR#1"),mfgr2=code("MFGR#2"),brand2221=code("MFGR#2221"),dec1997=code("Dec1997");
 vector<int> brands;for(int i=1;i<=8;i++)brands.push_back(code("MFGR#222"+to_string(i)));
 ifstream input(argv[5]);if(!input)throw runtime_error("Missing retained fact sample");string line;uint64_t rows=0;
 while(getline(input,line)){
  auto f=fields(line,17);Number ck=number(f[2]),pk=number(f[3]),sk=number(f[4]),dk=number(f[5]);
  bool hc=ck.has&&ck.value>0&&(uint64_t)ck.value<customers.size(),hp=pk.has&&pk.value>0&&(uint64_t)pk.value<parts.size(),hs=sk.has&&sk.value>0&&(uint64_t)sk.value<suppliers.size(),hd=dk.has&&dates.count(dk.value);
  Customer c=hc?customers[ck.value]:Customer{},s=hs?suppliers[sk.value]:Customer{};Part p=hp?parts[pk.value]:Part{};Date d=hd?dates.at(dk.value):Date{};
  Number quantity=number(f[8]),extended=number(f[9]),discount=number(f[11]),revenue=number(f[12]),cost=number(f[13]);
  string year=d.year.has?to_string(d.year.value):"\\N";bool year_range=d.year.has&&d.year.value>=1992&&d.year.value<=1997;
  __int128 product=(__int128)extended.value*discount.value,profit=(__int128)(revenue.has?revenue.value:0)-(cost.has?cost.value:0);
  if(hd&&d.year.has&&d.year.value==1993&&discount.has&&discount.value>=1&&discount.value<=3&&quantity.has&&quantity.value<25)aggregates[0][{}].add(product,extended.has);
  if(hd&&d.ym.has&&d.ym.value==199401&&discount.has&&discount.value>=4&&discount.value<=6&&quantity.has&&quantity.value>=26&&quantity.value<=35)aggregates[1][{}].add(product,extended.has);
  if(hd&&d.week.has&&d.week.value==6&&d.year.has&&d.year.value==1994&&discount.has&&discount.value>=5&&discount.value<=7&&quantity.has&&quantity.value>=26&&quantity.value<=35)aggregates[2][{}].add(product,extended.has);
  if(hd&&hp&&hs&&p.category==cat12&&s.region==america)aggregates[3][{year,labels[p.brand]}].add(revenue.value,revenue.has);
  if(hd&&hp&&hs&&find(brands.begin(),brands.end(),p.brand)!=brands.end()&&s.region==asia)aggregates[4][{year,labels[p.brand]}].add(revenue.value,revenue.has);
  if(hd&&hp&&hs&&p.brand==brand2221&&s.region==europe)aggregates[5][{year,labels[p.brand]}].add(revenue.value,revenue.has);
  if(hd&&hc&&hs&&c.region==asia&&s.region==asia&&year_range)aggregates[6][{labels[c.nation],labels[s.nation],year}].add(revenue.value,revenue.has);
  if(hd&&hc&&hs&&c.nation==usa&&s.nation==usa&&year_range)aggregates[7][{labels[c.city],labels[s.city],year}].add(revenue.value,revenue.has);
  bool city=(c.city==uk1||c.city==uk5)&&(s.city==uk1||s.city==uk5);
  if(hd&&hc&&hs&&city&&year_range)aggregates[8][{labels[c.city],labels[s.city],year}].add(revenue.value,revenue.has);
  if(hd&&hc&&hs&&city&&d.month==dec1997)aggregates[9][{labels[c.city],labels[s.city],year}].add(revenue.value,revenue.has);
  bool mfgr=p.mfgr==mfgr1||p.mfgr==mfgr2;
  if(hd&&hc&&hs&&hp&&c.region==america&&s.region==america&&mfgr)aggregates[10][{year,labels[c.nation]}].add(profit,true,revenue.has,cost.has);
  if(hd&&hc&&hs&&hp&&c.region==america&&s.region==america&&d.year.has&&d.year.value>=1997&&d.year.value<=1998&&mfgr)aggregates[11][{year,labels[s.nation],labels[p.category]}].add(profit,true,revenue.has,cost.has);
  if(hd&&hc&&hs&&hp&&c.region==america&&s.nation==usa&&d.year.has&&d.year.value>=1997&&d.year.value<=1998&&p.category==cat14)aggregates[12][{year,labels[s.city],labels[p.brand]}].add(profit,true,revenue.has,cost.has);
  ++rows;if(rows>20000000)throw runtime_error("Retained sample exceeds proven moment bound");
 }
 if(rows!=stoull(argv[11]))throw runtime_error("Retained sample row count mismatch");ofstream out(argv[6]);if(!out)throw runtime_error("Cannot create moments output");
 for(int q=0;q<13;q++)for(const auto&item:aggregates[q]){out<<q;for(const string&key:item.first)out<<'\t'<<key;const Moment&m=item.second;out<<'\t'<<m.count<<'\t'<<m.filtered<<'\t'<<decimal(m.total)<<'\t'<<decimal(m.squares)<<'\t'<<m.a<<'\t'<<m.b<<'\n';}
 out.flush();if(!out)throw runtime_error("Moment write failed");cout<<"rows="<<rows<<"\n";return 0;
 }catch(const exception&e){cerr<<e.what()<<"\n";return 1;}}
'''


def preparation_code_sha256(source=None):
    """Bind preparation semantics without invalidating it for later model code."""
    names={'digest','atomic_json','atomic_pickle','preparation_code_sha256','raw_chunks','canonical','profile_table',
           'converted_value','key_index','lookup','relationship_counts','table_metadata','write_table',
           'preparation_binding','prepare_bounded'}
    selected=[];found=set()
    for node in ast.parse(source if source is not None else Path(__file__).read_text(encoding='utf-8')).body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
            selected.append(ast.dump(node,include_attributes=False));found.add(node.name)
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MAX_DISTINCT' for t in node.targets):
            selected.append(ast.dump(node,include_attributes=False))
    if found!=names:raise ValueError('Preparation dependency function missing')
    return hashlib.sha256('\n'.join(selected).encode()).hexdigest()


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def atomic_pickle(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    with temporary.open('wb') as stream:
        pickle.dump(value,stream,protocol=4);stream.flush();os.fsync(stream.fileno())
    os.replace(str(temporary),str(path))


def raw_chunks(table,chunk_rows,attributes=None):
    selected=attributes or [x for x in table.attributes if x not in table.irrelevant_attributes]
    positions=[table.attributes.index(x) for x in selected]
    for frame in pd.read_csv(table.csv_file_location,header=None,sep='|',usecols=positions,
                             escapechar='\\',encoding='utf-8',quotechar='"',dtype=str,chunksize=chunk_rows):
        frame.columns=[table.table_name+'.'+table.attributes[i] for i in sorted(positions)]
        yield frame


def canonical(value):
    return None if pd.isna(value) else str(value)


def profile_table(table,work,chunk_rows):
    work.mkdir(parents=True,exist_ok=True)
    columns=[table.table_name+'.'+x for x in table.attributes if x not in table.irrelevant_attributes]
    states={name:{'numeric':True,'integer':True,'nonnull':0,'nulls':0,'int_sum':0,'max_abs':0.,
                  'distinct':[],'seen':set(),'sequential':True} for name in columns}
    fd_pairs={(attribute,child):[] for attribute in columns for child in table.children_fd_attributes(attribute)}
    fd_seen={key:set() for key in fd_pairs}
    rows=0
    for frame in raw_chunks(table,chunk_rows):
        for column,state in states.items():
            series=frame[column];state['nulls']+=int(series.isna().sum())
            state['nonnull']+=int(series.notna().sum())
            if len(state['distinct'])<=MAX_DISTINCT:
                for value in pd.unique(series):
                    value=canonical(value)
                    if value not in state['seen']:
                        state['seen'].add(value);state['distinct'].append(value)
                        if len(state['distinct'])>MAX_DISTINCT:break
            if state['numeric']:
                try:
                    converted=pd.to_numeric(series,errors='raise')
                    if converted.dtype.kind not in 'iuf':raise ValueError('Non-real numeric type')
                    valid=converted.dropna()
                    if len(valid):state['max_abs']=max(state['max_abs'],float(valid.abs().max()))
                    integer=converted.dtype.kind in 'iu'
                    if integer:state['int_sum']+=int(converted.sum())
                    state['integer']=state['integer'] and integer
                    state['sequential']=state['sequential'] and bool(np.array_equal(converted.values,np.arange(rows+1,rows+len(frame)+1)))
                except (ValueError,TypeError):
                    state['numeric']=False;state['sequential']=False
        for pair,values in fd_pairs.items():
            for a,b in frame[list(pair)].drop_duplicates().values:
                item=(canonical(a),canonical(b))
                if item not in fd_seen[pair]:
                    fd_seen[pair].add(item);values.append(item)
                    if len(values)>100000:raise ValueError('FD domain exceeds bounded preparation budget')
        rows+=len(frame)
    for column,state in states.items():
        state.pop('seen')
        state['dtype']='int64' if state['numeric'] and state['integer'] else 'float64' if state['numeric'] else 'object'
        if state['numeric'] and state['nonnull']:
            if state['integer']:
                if state['max_abs']*rows>=2**53:raise ValueError('Integer reduction outside proven exact range')
                state['mean']=state['int_sum']/state['nonnull']
            else:
                path=work/(column.replace('.','_')+'.bin')
                with path.open('wb') as output:
                    attr=column.split('.',1)[1]
                    for frame in raw_chunks(table,chunk_rows,[attr]):
                        values=pd.to_numeric(frame[column],errors='raise').astype('float64').values
                        if np.isinf(values).any():raise ValueError('Infinite values unsupported')
                        output.write(values.tobytes())
                values=np.memmap(str(path),mode='r',dtype='float64',shape=(rows,))
                state['mean']=float(pd.Series(values,copy=False).mean())
        elif state['numeric']:state['mean']=None
    return {'rows':rows,'columns':states,'fd_pairs':fd_pairs}


def converted_value(raw,state):
    if raw is None:return np.nan
    if state['dtype']=='int64':return int(raw)
    if state['dtype']=='float64':return float(raw)
    return raw


def key_index(profile,column):
    state=profile['columns'][column]
    if state['dtype']!='int64' or state['nulls']:raise ValueError('Incoming PK must be non-null int64')
    if state['sequential']:return {'dense':True,'size':profile['rows']}
    if len(state['distinct'])>MAX_DISTINCT:raise ValueError('Non-dense PK exceeds bounded sparse index')
    keys=np.asarray([int(x) for x in state['distinct']],dtype='int64')
    if len(keys)!=profile['rows'] or not np.all(np.diff(keys)>0):
        raise ValueError('Incoming PK must be unique and sorted for the proven SSB domain')
    return {'dense':False,'size':len(keys),'keys':keys}


def lookup(index,values):
    array=np.asarray(values,dtype='float64');nonnull=~np.isnan(array)
    safe=np.where(nonnull,array,0.)
    if index['dense']:
        valid=nonnull & (safe>=1) & (safe<=index['size']) & (safe==np.floor(safe))
        positions=np.where(valid,safe-1,0).astype('int64')
    else:
        positions=np.searchsorted(index['keys'],safe)
        valid=nonnull & (positions<index['size'])
        positions=np.minimum(positions,index['size']-1)
        valid &= index['keys'][positions]==safe
    return positions,valid


def relationship_counts(schema,profiles,work,chunk_rows):
    result={}
    checkpoint=work/'relationship_counts.json'
    if checkpoint.exists():
        for identifier,item in json.loads(checkpoint.read_text()).items():
            for field in ['counts','matched']:
                if digest(work/item[field]['path'])!=item[field]['sha256']:raise ValueError('FK count checkpoint checksum changed')
            index=item['index']
            if not index['dense']:index['keys']=np.asarray(index['keys'],dtype='int64')
            result[identifier]={'index':index,'counts':np.load(str(work/item['counts']['path']),mmap_mode='r'),
                                'matched':np.load(str(work/item['matched']['path']),mmap_mode='r')}
        return result
    allocated=0
    for relationship in schema.relationships:
        table=schema.table_dictionary[relationship.end]
        if len(table.primary_key)!=1 or relationship.end_attr!=table.primary_key[0]:
            raise ValueError('Original preparation requires single-column incoming primary key')
        index=key_index(profiles[relationship.end],relationship.end+'.'+relationship.end_attr)
        allocated+=index['size']*9
        if allocated>384*1024*1024:raise ValueError('FK count arrays exceed bounded memory budget')
        stem=relationship.end+'_'+relationship.start_attr
        counts=np.lib.format.open_memmap(str(work/(stem+'_counts.npy')),mode='w+',dtype='int64',shape=(index['size'],));counts[:]=0
        matched=np.lib.format.open_memmap(str(work/(stem+'_matched.npy')),mode='w+',dtype='bool',shape=(index['size'],));matched[:]=False
        result[relationship.identifier]={'index':index,'counts':counts,'matched':matched}
    for table in schema.tables:
        outgoing=[r for r in schema.relationships if r.start==table.table_name]
        if not outgoing:continue
        attributes=list(dict.fromkeys([table.primary_key[0]]+[r.start_attr for r in outgoing]))
        for frame in raw_chunks(table,chunk_rows,attributes):
            primary=pd.to_numeric(frame[table.table_name+'.'+table.primary_key[0]],errors='raise')
            for relationship in outgoing:
                values=pd.to_numeric(frame[table.table_name+'.'+relationship.start_attr],errors='raise')
                item=result[relationship.identifier];positions,valid=lookup(item['index'],values)
                if bool((values.notna().values & ~valid).any()):raise ValueError('Foreign key references absent parent')
                np.add.at(item['counts'],positions[valid],1)
                item['matched'][positions[valid & primary.notna().values]]=True
    for item in result.values():item['counts'].flush();item['matched'].flush()
    manifest={}
    for identifier,item in result.items():
        index=dict(item['index'])
        if not index['dense']:index['keys']=index['keys'].tolist()
        manifest[identifier]={'index':index}
        for field in ['counts','matched']:
            path=Path(item[field].filename)
            manifest[identifier][field]={'path':path.name,'sha256':digest(path)}
    atomic_json(checkpoint,manifest)
    return result


def table_metadata(table,profile,path,relationships,count_info,work,chunk_rows):
    name=table.table_name
    relevant=[x for x in table.attributes if x not in table.irrelevant_attributes]
    meta={'hdf_path':str(path),'incoming_relationship_means':{},'fd_dict':{},
          'categorical_columns_dict':{},'null_values_column':[]}
    for attribute in list(relevant):
        full=name+'.'+attribute;children=table.children_fd_attributes(full)
        if not children:continue
        for child in children:
            reverse={};seen=set()
            for a,b in profile['fd_pairs'][(full,child)]:
                a=converted_value(a,profile['columns'][full]);b=converted_value(b,profile['columns'][child])
                marker=(canonical(a),canonical(b))
                if marker in seen:continue
                seen.add(marker);reverse.setdefault(a,[]).append(b)
            meta['fd_dict'].setdefault(full,{})[child]=reverse
        relevant.remove(attribute)
    incoming=[r for r in relationships if r.end==name]
    multiplier_arrays={}
    for relationship in incoming:
        item=count_info[relationship.identifier];neighbor_rate=relationship._neighbor_rate
        arrays={}
        for attribute in [relationship.multiplier_attribute_name,relationship.multiplier_attribute_name_nn]:
            values=np.lib.format.open_memmap(str(work/(name+'_'+attribute.replace('.','_')+'.npy')),
                                           mode='w+',dtype='float64',shape=(profile['rows'],))
            arrays[attribute]=values
        offset=0
        for frame in raw_chunks(table,chunk_rows,[relationship.end_attr]):
            positions,valid=lookup(item['index'],pd.to_numeric(frame[name+'.'+relationship.end_attr]))
            if not valid.all():raise ValueError('Parent PK lookup failed')
            values=item['counts'][positions]*1/neighbor_rate
            arrays[relationship.multiplier_attribute_name][offset:offset+len(frame)]=values
            arrays[relationship.multiplier_attribute_name_nn][offset:offset+len(frame)]=np.where(values==0,1,values)
            offset+=len(frame)
        for attribute,values in arrays.items():
            values.flush();multiplier_arrays[name+'.'+attribute]=values
            relevant.append(attribute)
        meta['incoming_relationship_means'][relationship.identifier]=float(pd.Series(arrays[relationship.multiplier_attribute_name_nn],copy=False).mean())
    for relationship in relationships:
        if relationship.start==name:
            full=name+'.'+relationship.start_attr
            meta[relationship.identifier]={'fk_attribute_name':full,'length':profile['columns'][full]['nulls']*1/table.sample_rate,'path':None}
    kept=[]
    for attribute in relevant:
        full=name+'.'+attribute
        if full in multiplier_arrays:
            values=multiplier_arrays[full];sentinel=float(pd.Series(values,copy=False).mean())+.0001
            if np.any(values==sentinel):raise ValueError('NULL sentinel collides with multiplier')
        else:
            state=profile['columns'][full]
            if not state['nonnull']:continue
            if state['dtype']=='object':
                if len(state['distinct'])>MAX_DISTINCT:continue
                distinct=np.asarray([converted_value(x,state) for x in state['distinct']],dtype=object)
                mapping=dict(zip(distinct,range(1,len(distinct)+1)));mapping[np.nan]=0
                meta['categorical_columns_dict'][full]=mapping;sentinel=0
            else:sentinel=state['mean']+.0001
        kept.append(attribute);meta['null_values_column'].append(sentinel)
    meta['relevant_attributes']=kept;meta['relevant_attributes_full']=[name+'.'+x for x in kept]
    meta['length']=profile['rows']*1/table.sample_rate
    return meta,multiplier_arrays


def write_table(table,profile,meta,multipliers,relationships,count_info,chunk_rows):
    name=table.table_name;offset=0;null_counts={}
    sentinels=dict(zip(meta['relevant_attributes_full'],meta['null_values_column']))
    incoming=[r for r in relationships if r.end==name]
    for raw in raw_chunks(table,chunk_rows):
        columns={}
        for full in meta['relevant_attributes_full']:
            if full in multipliers:series=pd.Series(np.asarray(multipliers[full][offset:offset+len(raw)]),index=raw.index)
            else:
                state=profile['columns'][full]
                if state['dtype']=='object':
                    series=raw[full].map(meta['categorical_columns_dict'][full].get).fillna(0)
                else:
                    series=pd.to_numeric(raw[full],errors='raise').astype(state['dtype'])
                    if bool((series==sentinels[full]).any()):raise ValueError('NULL sentinel collides with numeric value')
                    series=series.fillna(sentinels[full])
            columns[full]=series
        frame=pd.DataFrame(columns,index=raw.index)
        if incoming:
            full=name+'.'+incoming[0].end_attr
            frame.index=pd.Index(pd.to_numeric(raw[full]).values);frame.index.name=None
        if frame.isna().any().any():raise ValueError('Encoded table still contains NULL')
        frame.to_hdf(meta['hdf_path'],key='df',format='table',append=True,index=False)
        for relationship in incoming:
            item=count_info[relationship.identifier]
            positions,valid=lookup(item['index'],pd.to_numeric(raw[name+'.'+relationship.end_attr]))
            null_mask=~item['matched'][positions]
            if not null_mask.any():continue
            path=meta['hdf_path']+relationship.start+relationship.start_attr+'.hdf'
            null_frame=frame.loc[null_mask].copy()
            # Original null-tuple extraction calls set_index again, preserving
            # the PK column name even though the main HDF index name is None.
            null_frame.index.name=name+'.'+relationship.end_attr
            null_frame.to_hdf(path,key='df',format='table',append=True,index=False)
            null_counts[relationship.identifier]=null_counts.get(relationship.identifier,0)+int(null_mask.sum())
        offset+=len(raw)
    for relationship in incoming:
        count=null_counts.get(relationship.identifier,0)
        if count:meta[relationship.identifier]={'length':count*1/table.sample_rate,
                   'path':meta['hdf_path']+relationship.start+relationship.start_attr+'.hdf'}


def preparation_binding(schema,chunk_rows):
    return {'preparation_code_sha256':preparation_code_sha256(),'original_sha256':digest(ORIGINAL),'chunk_rows':chunk_rows,
            'runtime_versions':{'numpy':np.__version__,'pandas':pd.__version__},
            'tables':{t.table_name:{'source_sha256':digest(t.csv_file_location),'sample_rate':t.sample_rate,
                                   'attributes':t.attributes,'irrelevant':t.irrelevant_attributes,'fds':[list(fd) for fd in t.fd_list],
                                   'primary_key':t.primary_key,'table_size':t.table_size} for t in schema.tables},
            'relationships':[r.identifier for r in schema.relationships]}


def prepare_bounded(schema,path,chunk_rows=100000):
    if type(chunk_rows) is not int or not 1<=chunk_rows<=500000:raise ValueError('Invalid bounded chunk budget')
    path=Path(path);path.mkdir(parents=True,exist_ok=True);work=path/'work';work.mkdir(exist_ok=True)
    binding=preparation_binding(schema,chunk_rows);bound=path/'binding.json';seal=path/'seal.json'
    if bound.exists() and json.loads(bound.read_text())!=binding:raise ValueError('Preparation input/source binding changed')
    if seal.exists():
        for relative,sha in json.loads(seal.read_text())['files_sha256'].items():
            if digest(path/relative)!=sha:raise ValueError('Prepared file checksum changed')
        with (path/'meta_data.pkl').open('rb') as stream:return pickle.load(stream)
    atomic_json(bound,binding)
    profiles={}
    for table in schema.tables:
        cache=work/(table.table_name+'_profile.pkl')
        if cache.exists():
            with cache.open('rb') as stream:profiles[table.table_name]=pickle.load(stream)
        else:
            profiles[table.table_name]=profile_table(table,work,chunk_rows);atomic_pickle(cache,profiles[table.table_name])
        if profiles[table.table_name]['rows']>=20000000:
            raise ValueError('Proven SSB preparation domain requires fewer than original 20M stored rows per table')
    # Shallow temporary relationship attributes are local metadata only; no
    # original code is patched. Remove them before returning to the caller.
    for relationship in schema.relationships:
        relationship._neighbor_rate=schema.table_dictionary[relationship.start].sample_rate
    try:
        counts=relationship_counts(schema,profiles,work,chunk_rows)
        metadata={}
        for table in schema.tables:
            receipt=work/(table.table_name+'_done.pkl')
            if receipt.exists():
                with receipt.open('rb') as stream:completed=pickle.load(stream)
                for name,sha in completed['files_sha256'].items():
                    if digest(path/name)!=sha:raise ValueError('Completed table checksum changed')
                metadata[table.table_name]=completed['metadata']
                continue
            meta,multipliers=table_metadata(table,profiles[table.table_name],path/(table.table_name+'.hdf'),schema.relationships,counts,work,chunk_rows)
            if Path(meta['hdf_path']).exists():raise ValueError('Uncommitted HDF exists; use a new output directory')
            write_table(table,profiles[table.table_name],meta,multipliers,schema.relationships,counts,chunk_rows)
            files=[Path(meta['hdf_path'])]+[Path(x['path']) for x in meta.values() if isinstance(x,dict) and x.get('path')]
            atomic_pickle(receipt,{'metadata':meta,'files_sha256':{x.name:digest(x) for x in files}})
            metadata[table.table_name]=meta
        atomic_pickle(path/'meta_data.pkl',metadata)
        files=list(path.glob('*.hdf'))+[path/'meta_data.pkl',bound]
        atomic_json(seal,{'files_sha256':{x.name:digest(x) for x in files}})
        if preparation_binding(schema,chunk_rows)!=binding:raise ValueError('Inputs changed during bounded preparation')
        return metadata
    finally:
        for relationship in schema.relationships:del relationship._neighbor_rate


def normalized(value):
    if isinstance(value,dict):return {normalized(k):normalized(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalized(x) for x in value]
    if isinstance(value,np.generic):return normalized(value.item())
    if isinstance(value,float) and math.isnan(value):return '<NaN>'
    if isinstance(value,str) and (value.endswith('.hdf') or value.endswith('.pkl')):return Path(value).name
    return value


def compare_prepared(reference,bounded):
    if normalized(reference)!=normalized(bounded):
        for table in reference:
            for key in reference[table]:
                if normalized(reference[table][key])!=normalized(bounded[table].get(key)):
                    raise AssertionError('Prepared metadata mismatch: '+table+' '+key+' '+repr(normalized(reference[table][key]))+' != '+repr(normalized(bounded[table].get(key))))
        raise AssertionError('Prepared metadata table/key mismatch')
    null_files=0;rows={}
    for table in reference:
        first,second=reference[table],bounded[table]
        expected=pd.read_hdf(first['hdf_path'],'df');actual=pd.read_hdf(second['hdf_path'],'df')
        pd.testing.assert_frame_equal(actual,expected,check_exact=True,check_dtype=True)
        rows[table]=len(actual)
        for key,value in first.items():
            if isinstance(value,dict) and value.get('path'):
                pd.testing.assert_frame_equal(pd.read_hdf(bounded[table][key]['path'],'df'),pd.read_hdf(value['path'],'df'),check_exact=True,check_dtype=True)
                null_files+=1
    return {'status':'PASS','tables':len(reference),'rows':rows,'null_tuple_files':null_files,
            'metadata_exact':True,'all_frame_values_and_dtypes_exact':True}


def sf2_inputs():
    from schemas.ssb.schema import gen_500gb_ssb_schema
    gate_path=ROOT/'output/full/ssb/paper/sf2_gate_v2/gate.json'
    gate=json.loads(gate_path.read_text())
    if gate['status']!='PASS' or not gate['checks']['all_dimensions_match_stock']:
        raise ValueError('Existing SF2 byte gate must be PASS')
    directory=ROOT/'data/ssb/sf2_gate_v2'
    schema=gen_500gb_ssb_schema(str(directory/'dimensions/{}.tbl'))
    inputs={'gate_sha256':digest(gate_path),'original_preparation_sha256':digest(ORIGINAL),'files':{}}
    for table in schema.tables:
        if table.table_name=='lineorder':
            table.csv_file_location=str(directory/'lineorder_sampled.csv');table.table_size=gate['fact_rows']
            table.sample_rate=.003333;expected=gate['sample_sha256']
        else:
            source='date' if table.table_name=='dwdate' else table.table_name
            table.csv_file_location=str(directory/'dimensions'/(source+'.tbl'))
            table.table_size=gate['dimensions'][source]['rows'];expected=gate['dimensions'][source]['sha256']
        actual=digest(table.csv_file_location)
        if actual!=expected:raise ValueError('SF2 input checksum changed: '+table.table_name)
        inputs['files'][table.table_name]={'path':table.csv_file_location,'sha256':actual,'table_size':table.table_size,'sample_rate':table.sample_rate}
    return schema,inputs


def windows_peak_working_set():
    if os.name!='nt':return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(x,ctypes.c_size_t) for x in
            ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    get_process=ctypes.windll.kernel32.GetCurrentProcess;get_process.restype=wintypes.HANDLE
    read=ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not read(get_process(),ctypes.byref(counters),counters.cb):raise ctypes.WinError()
    return counters.PeakWorkingSetSize


def run_sf2_gate():
    from data_preparation.prepare_single_tables import prepare_all_tables
    start=time.perf_counter();schema,inputs=sf2_inputs()
    input_id=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    reference_dir=OUTPUT/('sf2_original_'+input_id);reference_dir.mkdir(parents=True,exist_ok=True)
    reference_seal=reference_dir/'seal.json';reference_seconds=None
    if reference_seal.exists():
        for name,sha in json.loads(reference_seal.read_text())['files_sha256'].items():
            if digest(reference_dir/name)!=sha:raise ValueError('Original golden output checksum changed')
        with (reference_dir/'meta_data.pkl').open('rb') as stream:reference=pickle.load(stream)
    else:
        before=time.perf_counter()
        reference=prepare_all_tables(schema,str(reference_dir),csv_seperator='|')
        reference_seconds=time.perf_counter()-before
        files=list(reference_dir.glob('*.hdf'))+[reference_dir/'meta_data.pkl']
        atomic_json(reference_seal,{'inputs':inputs,'seconds':reference_seconds,
                    'files_sha256':{x.name:digest(x) for x in files}})
    code_id=preparation_code_sha256()[:16]
    bounded_dir=OUTPUT/('sf2_bounded_'+input_id+'_'+code_id)
    before=time.perf_counter();bounded=prepare_bounded(schema,bounded_dir,chunk_rows=50000)
    bounded_seconds=time.perf_counter()-before
    comparison=compare_prepared(reference,bounded)
    report={'status':'PASS','stage':'SEALED_SF2_BOUNDED_PREPARATION_GOLDEN_ONLY','sf500_training_started':False,
            'inputs':inputs,'implementation_sha256':digest(__file__),'reference_directory':str(reference_dir),
            'bounded_directory':str(bounded_dir),'comparison':comparison,'chunk_rows':50000,
            'reference_seconds_this_invocation':reference_seconds,'bounded_seconds_this_invocation':bounded_seconds,
            'wall_seconds':time.perf_counter()-start,'process_peak_working_set_bytes':windows_peak_working_set(),
            'input_and_original_bytes_unchanged':sf2_inputs()[1]==inputs,
            'disk_bytes_reference':sum(x.stat().st_size for x in reference_dir.rglob('*') if x.is_file()),
            'disk_bytes_bounded':sum(x.stat().st_size for x in bounded_dir.rglob('*') if x.is_file()),
            'scope':'Exact equality of original metadata, all HDF values/dtypes/index/column order, and null-tuple HDFs; only directory prefixes normalized'}
    atomic_json(OUTPUT/('sf2_preparation_gate_'+code_id+'.json'),report)
    atomic_json(OUTPUT/'sf2_preparation_gate_latest.json',report)
    return report


def component_code_hash(names,constants=()):
    nodes=[];found=set()
    for node in ast.parse(Path(__file__).read_text(encoding='utf-8')).body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names:
            nodes.append(ast.dump(node,include_attributes=False));found.add(node.name)
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets):
            nodes.append(ast.dump(node,include_attributes=False))
    if found!=set(names):raise ValueError('Stage dependency function/class missing')
    return hashlib.sha256('\n'.join(nodes).encode()).hexdigest()


def ssb_query_spec(sql):
    value=sql.strip().rstrip(';')
    value=re.split(r'\s+order\s+by\s+',value,flags=re.I)[0]
    grouped=re.split(r'\s+group\s+by\s+',value,flags=re.I)
    groups=[x.strip().lower() for x in grouped[1].split(',')] if len(grouped)==2 else []
    select,rest=re.split(r'\s+from\s+',grouped[0][7:],maxsplit=1,flags=re.I)
    tables,where=re.split(r'\s+where\s+',rest,maxsplit=1,flags=re.I)
    aggregate=select.split(',')[-1].strip()
    difference=re.fullmatch(r'sum\((\w+)\)\s*-\s*sum\((\w+)\)',aggregate,re.I)
    if difference:
        components=[x.lower() for x in difference.groups()]
        expression='COALESCE('+components[0]+',0)-COALESCE('+components[1]+',0)';kind='DIFF'
    else:
        match=re.fullmatch(r'sum\(([\w*]+)\)',aggregate,re.I)
        if not match:raise ValueError('Unsupported released SSB aggregate')
        expression=match.group(1).lower();components=[];kind='SUM'
    if expression not in ['lo_extendedprice*lo_discount','lo_revenue','COALESCE(lo_revenue,0)-COALESCE(lo_supplycost,0)']:
        raise ValueError('SSB expression is outside the sealed query protocol')
    return {'groups':groups,'tables':tables,'where':where,'expression':expression,'kind':kind,'components':components}


class ExactMoments:
    def __init__(self):self.count,self.total,self.square=0,0,0
    def step(self,value):
        if value is None:return
        if not isinstance(value,int):raise ValueError('SQLite aggregate expression lost exact integer type')
        self.count+=1;self.total+=value;self.square+=value*value
    def finalize(self):return json.dumps([self.count,self.total,self.square])


def moment_source_binding(schema):
    return {'files':{t.table_name:{'sha256':digest(t.csv_file_location),'rows':t.table_size,'attributes':t.attributes,
                                  'primary_key':t.primary_key} for t in schema.tables},'sql_sha256':digest(SQL_PATH),
            'code':component_code_hash(['moment_source_binding','ssb_query_spec','ExactMoments','compile_ci',
                    'sample_moments_sqlite','sample_moments_native','normalized_moments'],['CI_CPP'])}


def normalized_moments(queries):
    return [{'kind':q['kind'],'groups':sorted(q['groups'],key=lambda g:repr(g['key']))} for q in queries]


def sample_moments_sqlite(schema,database):
    """Independent exact SQL golden; deliberately unavailable for huge inputs."""
    if any(Path(t.csv_file_location).stat().st_size>128*1024*1024 for t in schema.tables):
        raise ValueError('SQLite oracle is restricted to the small-scale gate')
    database=Path(database);database.parent.mkdir(parents=True,exist_ok=True)
    cache=Path(str(database)+'.moments.json');seal=Path(str(database)+'.seal.json');binding=moment_source_binding(schema)
    if cache.exists() and seal.exists():
        entry=json.loads(seal.read_text())
        if entry['binding']!=binding or digest(cache)!=entry['sha256'] or digest(database)!=entry['database_sha256']:
            raise ValueError('SQLite moment golden binding/checksum changed')
        return json.loads(cache.read_text())
    connection=sqlite3.connect(str(database));connection.execute('PRAGMA cache_size=-32768')
    connection.create_aggregate('exact_moments',1,ExactMoments)
    text={'lineorder':{'lo_orderpriority','lo_shipmode'},'dwdate':{'d_date','d_dayofweek','d_month','d_yearmonth','d_sellingseason'},
          'customer':set(),'supplier':set(),'part':set()}
    explicit={'customer':{'c_custkey'},'supplier':{'s_suppkey'},'part':{'p_partkey','p_size'}}
    try:
        for table in schema.tables:
            numeric=explicit.get(table.table_name,set(table.attributes)-text[table.table_name])
            connection.execute('DROP TABLE IF EXISTS '+table.table_name)
            ddl=[]
            for attribute in table.attributes:
                column=attribute+(' INTEGER' if attribute in numeric else ' TEXT')
                if table.table_name!='lineorder' and attribute in table.primary_key:column+=' PRIMARY KEY NOT NULL'
                ddl.append(column)
            connection.execute('CREATE TABLE '+table.table_name+'('+','.join(ddl)+')')
            statement='INSERT INTO '+table.table_name+' VALUES ('+','.join('?' for _ in table.attributes)+')';pending=[]
            with Path(table.csv_file_location).open(newline='') as stream:
                for row in csv.reader(stream,delimiter='|',escapechar='\\'):
                    if len(row)==len(table.attributes)+1 and row[-1]=='':row.pop()
                    if len(row)!=len(table.attributes):raise ValueError('Raw SSB field count mismatch')
                    values=[None if value=='' else int(value) if attribute in numeric else value for attribute,value in zip(table.attributes,row)]
                    if table.table_name!='lineorder' and any(values[table.attributes.index(pk)] is None for pk in table.primary_key):
                        raise ValueError('Dimension PK cannot be NULL')
                    pending.append(values)
                    if len(pending)>=5000:connection.executemany(statement,pending);pending=[]
            if pending:connection.executemany(statement,pending)
        connection.commit();queries=[]
        for sql in SQL_PATH.read_text().splitlines():
            spec=ssb_query_spec(sql);projection=spec['groups']+['exact_moments('+spec['expression']+')','COUNT(*)']
            projection+=['COUNT('+x+')' for x in spec['components']]
            statement='SELECT '+','.join(projection)+' FROM '+spec['tables']+' WHERE '+spec['where']
            if spec['groups']:statement+=' GROUP BY '+','.join(spec['groups'])
            groups=[]
            for row in connection.execute(statement):
                width=len(spec['groups']);count,total,square=json.loads(row[width]) if row[width] is not None else [0,0,0]
                groups.append({'key':list(row[:width]),'count':count,'filter_count':row[width+1],
                               'sum_integer':total,'square_sum_integer':square,'scale':1,
                               'component_non_null_counts':list(row[width+2:])})
            queries.append({'sql':sql,'kind':spec['kind'],'groups':groups})
        if len(queries)!=13:raise ValueError('Exactly13 SSB queries required')
    finally:connection.close()
    atomic_json(cache,queries);atomic_json(seal,{'binding':binding,'sha256':digest(cache),'database_sha256':digest(database)})
    return queries


def compile_ci():
    native=OUTPUT/'native';native.mkdir(parents=True,exist_ok=True)
    source_sha=hashlib.sha256(CI_CPP.encode()).hexdigest();stem='ci_'+source_sha[:16]
    source=native/(stem+'.cpp');target=native/(stem+'.exe');seal=native/(stem+'.json')
    compiler=ROOT/'.runtime/w64devkit/bin/g++.exe'
    binding={'source_sha256':source_sha,'compiler_sha256':digest(compiler),'flags':['-std=c++17','-O2','-static-libgcc','-static-libstdc++']}
    if seal.exists():
        record=json.loads(seal.read_text())
        if record['binding']!=binding or digest(source)!=source_sha or digest(target)!=record['executable_sha256']:
            raise ValueError('Native CI compiler/source/executable binding changed')
        return target,record
    source.write_bytes(CI_CPP.encode('utf-8'))
    environment=dict(os.environ,PATH=str(compiler.parent)+os.pathsep+os.environ.get('PATH',''),OMP_NUM_THREADS='1')
    start=time.perf_counter();result=subprocess.run([str(compiler)]+binding['flags']+[str(source),'-o',str(target)],
                            cwd=str(ROOT),env=environment,capture_output=True,text=True,errors='replace',timeout=120)
    atomic_json(native/(stem+'_build.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'seconds':time.perf_counter()-start})
    if result.returncode:raise RuntimeError('Native retained-sample moment compile failed: '+result.stderr)
    record={'binding':binding,'executable_sha256':digest(target)};atomic_json(seal,record)
    return target,record


def sample_moments_native(schema,sample_rows,work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    binding=moment_source_binding(schema);binding['sample_rows']=sample_rows
    cache=work/'moments.json';seal=work/'seal.json';raw=work/'moments.tsv'
    if cache.exists() and seal.exists():
        entry=json.loads(seal.read_text())
        if entry['binding']!=binding or digest(cache)!=entry['sha256'] or digest(raw)!=entry['tsv_sha256']:
            raise ValueError('Native sample moments binding/checksum changed')
        return json.loads(cache.read_text())
    executable,build=compile_ci();tables=schema.table_dictionary
    arguments=[executable]+[tables[t].csv_file_location for t in ['customer','supplier','part','dwdate','lineorder']]+[raw]
    arguments+=[tables[t].table_size for t in ['customer','supplier','part','dwdate']]+[sample_rows]
    start=time.perf_counter();result=subprocess.run(list(map(str,arguments)),capture_output=True,text=True,errors='replace',timeout=1800)
    elapsed=time.perf_counter()-start
    atomic_json(work/'process.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'seconds':elapsed})
    if result.returncode:raise RuntimeError('Native sample moments failed: '+result.stderr)
    queries=[{'sql':sql,'kind':ssb_query_spec(sql)['kind'],'groups':[]} for sql in SQL_PATH.read_text().splitlines()]
    with raw.open() as stream:
        for line in stream:
            values=line.rstrip('\n').split('\t');index=int(values[0]);spec=ssb_query_spec(queries[index]['sql'])
            keys=[None if key=='\\N' else int(key) if name=='d_year' else key for name,key in zip(spec['groups'],values[1:-6])]
            if len(values)!=1+len(spec['groups'])+6:raise ValueError('Native moment group field mismatch')
            count,filtered,total,square,a,b=map(int,values[-6:])
            queries[index]['groups'].append({'key':keys,'count':count,'filter_count':filtered,'sum_integer':total,
                            'square_sum_integer':square,'scale':1,'component_non_null_counts':[a,b] if spec['kind']=='DIFF' else []})
    report={'status':'PASS','queries':queries,'sample_rows':sample_rows,'native_seconds':elapsed,'build':build,
            'arithmetic':'Signed128 integer sums/squares; sample<=20M and |aggregate row value|<=1e12; duplicate facts retained, NULL aggregate/COUNT(*)/component counts separate'}
    atomic_json(cache,report);atomic_json(seal,{'binding':binding,'sha256':digest(cache),'tsv_sha256':digest(raw)})
    return report


@contextmanager
def single_thread_rdc():
    import rspn.learning.rspn_learning as learning
    original=learning.getIndependentRDCGroups_py
    def bounded(*args,**kwargs):
        kwargs['n_jobs']=1
        return original(*args,**kwargs)
    learning.getIndependentRDCGroups_py=bounded
    try:yield
    finally:learning.getIndependentRDCGroups_py=original


def model_stage_binding(prepared_dir,sample_cap,seed):
    from full_common import algorithm_seal
    import scipy,sklearn
    return {'prepared_seal_sha256':digest(Path(prepared_dir)/'seal.json'),'samples_per_spn':sample_cap,'seed':seed,
            'ensemble_strategy':'single','rdc_threshold':.3,'post_sampling_factor':10,'min_slice_fraction':.01,
            'max_table_data':20000000,'bloom_filters':False,'incremental_learning_rate':0,
            'algorithm_seal':algorithm_seal(),'naive_source_sha256':digest(ROOT/'code/ensemble_creation/naive.py'),
            'resource_policy':'n_jobs=1 only; identical original RDC computations and random-state handling',
            'code':component_code_hash(['single_thread_rdc','model_stage_binding','train_single_models','train_original_reference']),
            'runtime':[np.__version__,pd.__version__,scipy.__version__,sklearn.__version__]}


def train_single_models(schema,prepared_dir,sample_cap,directory,seed=1):
    from aqp_spn.aqp_spn import AQPSPN
    from data_preparation.join_data_preparation import JoinDataPreparator
    from ensemble_compilation.spn_ensemble import SPNEnsemble
    from rspn.algorithms.validity.validity import is_valid
    if not 100<=sample_cap<=1000000:raise ValueError('SSB per-table training cap must be100..1M')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    binding=model_stage_binding(prepared_dir,sample_cap,seed);receipt=directory/'model.json'
    if receipt.exists():
        report=json.loads(receipt.read_text())
        if report['binding']!=binding:raise ValueError('Model stage binding changed')
        for name,sha in report['files_sha256'].items():
            if digest(directory/name)!=sha:raise ValueError('Model checkpoint checksum changed')
        return report
    prep=JoinDataPreparator(str(Path(prepared_dir)/'meta_data.pkl'),schema,max_table_data=20000000)
    ensemble=SPNEnsemble(schema);records=[]
    np.random.seed(seed);random.seed(seed)
    with single_thread_rdc():
        for table in schema.tables:
            checkpoint=directory/(table.table_name+'.pkl');seal=checkpoint.with_suffix('.json')
            if checkpoint.exists() and seal.exists():
                record=json.loads(seal.read_text())
                if record['binding']!=binding or digest(checkpoint)!=record['sha256']:raise ValueError('Per-table model binding changed')
                with checkpoint.open('rb') as stream:state=pickle.load(stream)
                model=state['model'];np.random.set_state(state['numpy_rng']);random.setstate(state['python_rng'])
                record=record['training']
            else:
                frame,types,nulls,normalizer=prep.generate_n_samples(sample_cap,single_table=table.table_name,post_sampling_factor=10)
                data=np.asarray(frame.values);sample_sha=hashlib.sha256(data.tobytes()).hexdigest()
                model=AQPSPN(types,nulls,normalizer,schema,None,full_sample_size=len(frame),table_set={table.table_name},
                             column_names=list(frame.columns),table_meta_data=prep.table_meta_data)
                started=time.perf_counter();model.learn(data,min_instances_slice=.01*min(sample_cap,len(frame)),bloom_filters=False,rdc_threshold=.3)
                elapsed=time.perf_counter()-started
                valid,reason=is_valid(model.mspn,check_ids=True,check_cluster_centers=True)
                if not valid:raise ValueError('Learned RSPN invalid: '+str(reason))
                record={'table':table.table_name,'actual_training_rows':len(frame),'full_join_estimate':float(normalizer),
                        'columns':list(frame.columns),'sample_matrix_sha256':sample_sha,'learning_seconds':elapsed,
                        'structure_sha256':hashlib.sha256(pickle.dumps(model.mspn,protocol=4)).hexdigest()}
                atomic_pickle(checkpoint,{'model':model,'numpy_rng':np.random.get_state(),'python_rng':random.getstate()})
                atomic_json(seal,{'binding':binding,'sha256':digest(checkpoint),'training':record})
                del data,frame
            ensemble.add_spn(model);records.append(record)
    target=directory/'ensemble_single.pkl';atomic_pickle(target,ensemble)
    files=list(directory.glob('*.pkl'))
    report={'status':'PASS','binding':binding,'model_path':str(target),'training_tables':records,
            'spn_count':len(ensemble.spns),'learning_seconds':sum(x['learning_seconds'] for x in records),
            'files_sha256':{x.name:digest(x) for x in files}}
    atomic_json(receipt,report);return report


def train_original_reference(schema,prepared_dir,sample_cap,directory,seed=1):
    """Actual unmodified naive entry; observe its fit matrices and node bytes."""
    from aqp_spn.aqp_spn import AQPSPN
    from ensemble_creation.naive import create_naive_all_split_ensemble
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);receipt=directory/'reference.json'
    binding=model_stage_binding(prepared_dir,sample_cap,seed)
    if receipt.exists():
        record=json.loads(receipt.read_text())
        if record['binding']!=binding or digest(record['model_path'])!=record['sha256']:raise ValueError('Original naive reference changed')
        return record
    native=AQPSPN.learn;observations=[]
    def observe(model,values,*args,**kwargs):
        matrix_sha=hashlib.sha256(np.asarray(values).tobytes()).hexdigest()
        result=native(model,values,*args,**kwargs)
        observations.append({'table':next(iter(model.table_set)),'actual_training_rows':len(values),
                             'sample_matrix_sha256':matrix_sha,'structure_sha256':hashlib.sha256(pickle.dumps(model.mspn,protocol=4)).hexdigest()})
        return result
    np.random.seed(seed);random.seed(seed);started=time.perf_counter();AQPSPN.learn=observe
    try:
        with single_thread_rdc():
            create_naive_all_split_ensemble(schema,str(prepared_dir),sample_cap,str(directory),'sf2_reference',False,.3,20000000,10,0)
    finally:AQPSPN.learn=native
    target=directory/('ensemble_single_sf2_reference_'+str(sample_cap)+'.pkl')
    report={'status':'PASS','binding':binding,'model_path':str(target),'sha256':digest(target),'observations':observations,'seconds':time.perf_counter()-started}
    atomic_json(receipt,report);return report


def sf2_preparation_reuse():
    schema,inputs=sf2_inputs();gate=json.loads((OUTPUT/'sf2_preparation_gate_latest.json').read_text())
    if gate['status']!='PASS' or gate['inputs']!=inputs:raise ValueError('Sealed SF2 preparation/source does not match')
    directory=Path(gate['bounded_directory']);binding=json.loads((directory/'binding.json').read_text())
    if binding['preparation_code_sha256']!=preparation_code_sha256():raise ValueError('Validated preparation algorithm changed')
    for name,sha in json.loads((directory/'seal.json').read_text())['files_sha256'].items():
        if digest(directory/name)!=sha:raise ValueError('Sealed SF2 prepared bytes changed')
    return schema,inputs,directory


def model_input_artifacts(schema,prepared_dir):
    """Validate physical inputs, including unmatched HDFs, before model reuse."""
    import platform,sys,scipy,sklearn,joblib,tables
    from full_common import algorithm_seal
    import spn.algorithms.splitting.RDC as rdc
    directory=Path(prepared_dir).resolve()
    binding=json.loads((directory/'binding.json').read_text())
    if binding!=preparation_binding(schema,binding['chunk_rows']):
        raise ValueError('Prepared input/source artifact binding changed')
    seal=json.loads((directory/'seal.json').read_text())
    recorded=seal['files_sha256']
    for name,expected in recorded.items():
        target=(directory/name).resolve()
        if target.parent!=directory or not target.is_file() or digest(target)!=expected:
            raise ValueError('Prepared artifact checksum changed: '+name)
    if not {'meta_data.pkl','binding.json'}.issubset(recorded):raise ValueError('Prepared artifact seal incomplete')
    with (directory/'meta_data.pkl').open('rb') as stream:metadata=pickle.load(stream)
    if set(metadata)!={t.table_name for t in schema.tables}:raise ValueError('Prepared artifact table set changed')
    required=set()
    for table in schema.tables:
        meta=metadata[table.table_name]
        paths=[meta['hdf_path']]+[value['path'] for value in meta.values() if isinstance(value,dict) and value.get('path')]
        for path in paths:
            candidate=Path(path).resolve()
            if candidate.parent!=directory or candidate.name not in recorded:
                raise ValueError('Main/unmatched HDF artifact omitted from prepared seal')
            required.add(candidate.name)
    if required!={p.name for p in directory.glob('*.hdf')} or not required.issubset(recorded):
        raise ValueError('Prepared HDF artifact inventory changed')
    return {'prepared_directory':str(directory),'prepared_seal_sha256':digest(directory/'seal.json'),
            'prepared_files_sha256':recorded,
            'raw_files':{t.table_name:{'path':str(Path(t.csv_file_location).resolve()),
                                     'sha256':binding['tables'][t.table_name]['source_sha256']} for t in schema.tables},
            'runtime':{'python':sys.version,'executable_sha256':digest(sys.executable),'platform':platform.platform(),
                       'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,
                       'sklearn':sklearn.__version__,'joblib':joblib.__version__,'tables':tables.__version__},
            'rdc_source_sha256':digest(rdc.__file__),'algorithm_seal':algorithm_seal(),
            'guard_code':component_code_hash(['model_input_artifacts','guarded_train_single_models'])}


def guarded_train_single_models(schema,prepared_dir,sample_cap,directory,seed=1,adoption_proof=None):
    """External dependency guard; the already verified training loop is unchanged."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    before=model_input_artifacts(schema,prepared_dir)
    binding={'inputs':before,'model_stage':model_stage_binding(prepared_dir,sample_cap,seed)}
    pending=directory/'input_guard.json';final=directory/'model_guard.json'
    if pending.exists():
        if json.loads(pending.read_text())['binding']!=binding:raise ValueError('Model input artifact guard changed')
    else:
        if (directory/'model.json').exists() and adoption_proof!='SF2_ORIGINAL_NAIVE_MATRICES_AND_NODES_EXACT':
            raise ValueError('An existing unguarded model requires its independently verified original-entry proof')
        atomic_json(pending,{'binding':binding,'adoption_proof':adoption_proof})
    if final.exists():
        record=json.loads(final.read_text())
        if record['binding']!=binding:raise ValueError('Model dependency artifact guard changed')
        for name,expected in record['model_files_sha256'].items():
            if digest(directory/name)!=expected:raise ValueError('Guarded model artifact checksum changed')
    model=train_single_models(schema,prepared_dir,sample_cap,directory,seed)
    if model_input_artifacts(schema,prepared_dir)!=before:raise ValueError('Input artifacts changed while training')
    files={p.name:digest(p) for p in directory.iterdir() if p.is_file() and p.name!='model_guard.json'}
    atomic_json(final,{'status':'PASS','binding':binding,'model_files_sha256':files})
    return model


def population_truth_groups(checkpoint):
    state=json.loads(Path(checkpoint).read_text());queries=[]
    for index,sql in enumerate(SQL_PATH.read_text().splitlines()):
        spec=ssb_query_spec(sql);groups=[]
        for key,total in state['aggregates'][str(index)].items():
            keys=[] if not key else key.split('\t')
            if len(keys)!=len(spec['groups']):raise ValueError('Full-stream truth key shape mismatch')
            keys=[int(x) if name=='d_year' else x for name,x in zip(spec['groups'],keys)]
            groups.append({'key':keys,'numerator':int(total),'denominator':1})
        queries.append({'query_no':index,'query_name':QUERY_NAMES[index],'groups':groups})
    return {'population_rows':state['rows'],'sample_rows':state['sample_rows'],'queries':queries,'checkpoint_sha256':digest(checkpoint)}


def evaluate_ssb(model,truth,moments,directory):
    import warnings
    from ensemble_compilation.spn_ensemble import read_ensemble
    from evaluation.utils import parse_query
    from full_factor_cache import model_aware_factor_cache
    from full_flights_model import compare_groups,reference_ci,legacy_comparison,canonical_key
    binding={'model_sha256':digest(model['model_path']),'truth_checkpoint_sha256':truth['checkpoint_sha256'],
             'model_input_artifact_guard_sha256':digest(Path(model['model_path']).parent/'model_guard.json'),
             'moments_sha256':hashlib.sha256(json.dumps(normalized_moments(moments),sort_keys=True).encode()).hexdigest(),
             'sql_sha256':digest(SQL_PATH),'cache_adapter_sha256':digest(ROOT/'code/full_factor_cache.py'),
             'ci_formula_sha256':digest(ROOT/'code/full_flights_model.py'),
             'code':component_code_hash(['evaluate_ssb','population_truth_groups']),
             'confidence_sample_size':truth['sample_rows'],'merge_indicator_exp':False,'max_variants':5}
    directory=Path(directory)/hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()[:16]
    directory.mkdir(parents=True,exist_ok=True)
    ensemble=read_ensemble(model['model_path'],build_reverse_dict=True);queries=[];point_errors=0;ci_errors=0
    def scalar(value):
        value=float(np.asarray(value).reshape(-1)[0]);return value if math.isfinite(value) else None
    with model_aware_factor_cache():
        for index,sql in enumerate(SQL_PATH.read_text().splitlines()):
            path=directory/('query_%02d.json'%index);seal=path.with_suffix('.seal.json')
            if path.exists() and seal.exists():
                entry=json.loads(seal.read_text())
                if entry['binding']!=binding or digest(path)!=entry['sha256']:raise ValueError('SSB query binding changed')
                result=json.loads(path.read_text());queries.append(result)
                point_errors+=bool(result['point_error']);ci_errors+=bool(result['ci_error']);continue
            query=parse_query(sql,ensemble.schema_graph);point_error=None;ci_error=None
            arguments={'rdc_spn_selection':False,'merge_indicator_exp':False,'max_variants':5,'exploit_overlapping':False}
            ensemble.cached_expecation_vals={};start=time.perf_counter()
            try:_,predicted=ensemble.evaluate_query(query,confidence_intervals=False,**arguments)
            except Exception as error:point_error=type(error).__name__+': '+str(error);predicted=[];point_errors+=1
            point_seconds=time.perf_counter()-start
            ensemble.cached_expecation_vals={};start=time.perf_counter();raw_intervals=None;ci_predicted=None
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                try:raw_intervals,ci_predicted=ensemble.evaluate_query(query,confidence_intervals=True,confidence_sample_size=truth['sample_rows'],**arguments)
                except Exception as error:ci_error=type(error).__name__+': '+str(error);ci_errors+=1
            ci_seconds=time.perf_counter()-start;predictions={};intervals={};nonfinite=[]
            if query.group_bys:
                for row in predicted:predictions[canonical_key(row[:-1])]=scalar(row[-1])
                if raw_intervals is not None:
                    for row,interval in zip(ci_predicted,raw_intervals):
                        key=canonical_key(row[:-1]);pair=[scalar(x) for x in interval]
                        if None in pair:nonfinite.append({'key':list(key),'raw':repr(interval)})
                        else:intervals[key]=pair
            elif not isinstance(predicted,list) or predicted:
                predictions[()]=scalar(predicted)
                if raw_intervals is not None:
                    pair=[scalar(x) for x in raw_intervals]
                    if None in pair:nonfinite.append({'key':[],'raw':repr(raw_intervals)})
                    else:intervals[()]=pair
            rows=compare_groups(truth['queries'][index]['groups'],predictions,intervals)
            moment_map={canonical_key(g['key']):g for g in moments[index]['groups']}
            for row in rows:
                moment=moment_map.get(canonical_key(row['key']),{'count':0,'filter_count':0,'sum_integer':0,'square_sum_integer':0,'scale':1,'component_non_null_counts':[]})
                reference=reference_ci(moment,moments[index]['kind'],truth['population_rows'],truth['sample_rows'])
                if reference['eligible'] and row['truth'] is not None:reference['covers_population_truth']=reference['interval'][0]<=row['truth']<=reference['interval'][1]
                row['sample_moments']=moment;row['reference_ci']=reference
                row['released_ci_comparison']=legacy_comparison(moment,moments[index]['kind'],truth['population_rows'],truth['sample_rows'],reference)
            result={'query_no':index,'query_name':QUERY_NAMES[index],'sql':sql,'point_error':point_error,'ci_error':ci_error,
                    'point_seconds':point_seconds,'ci_seconds':ci_seconds,'ci_warnings':list(dict.fromkeys(str(w.message) for w in caught)),
                    'nonfinite_original_intervals':nonfinite,'groups':rows,'model_groups':len(predictions),
                    'truth_groups':len(truth['queries'][index]['groups']),
                    'missing_model_groups':sum(r['status']=='MISSING_MODEL_GROUP' for r in rows),
                    'extra_model_groups':sum(r['status']=='EXTRA_MODEL_GROUP' for r in rows),
                    'correlated_sum_difference_warning':index>=10,
                    'reference_ci_eligible_groups':sum(r['reference_ci']['eligible'] for r in rows)}
            atomic_json(path,result);atomic_json(seal,{'binding':binding,'sha256':digest(path)});queries.append(result)
    for path in directory.glob('query_*.json'):
        if path.name.endswith('.seal.json'):continue
        seal=json.loads(path.with_suffix('.seal.json').read_text())
        if seal['binding']!=binding or digest(path)!=seal['sha256']:raise ValueError('Query artifact changed during evaluation')
    return {'queries':queries,'point_query_errors':point_errors,'ci_query_errors':ci_errors,'binding':binding,'directory':str(directory)}


def small_model_worker(sample_cap=10000):
    started=time.perf_counter();schema,inputs,prepared=sf2_preparation_reuse()
    binding=model_stage_binding(prepared,sample_cap,1);identity=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()[:16]
    directory=OUTPUT/('sf2_model_'+identity);directory.mkdir(parents=True,exist_ok=True)
    native=sample_moments_native(schema,39712,OUTPUT/'sf2_sample_moments_native')
    sql=sample_moments_sqlite(schema,OUTPUT/'sf2_moments_reference.sqlite')
    if normalized_moments(native['queries'])!=normalized_moments(sql):raise ValueError('Native sample moments disagree with independent SQLite')
    before=model_input_artifacts(schema,prepared)
    original=train_original_reference(schema,prepared,sample_cap,directory/'original')
    # Existing 10K models were independently matched to the original entry,
    # including complete matrix/node hashes; adopt without retraining those bytes.
    if (directory/'checkpointed/model.json').exists():
        trained=train_single_models(schema,prepared,sample_cap,directory/'checkpointed')
        for expected,actual in zip(original['observations'],trained['training_tables']):
            for key in ['table','actual_training_rows','sample_matrix_sha256','structure_sha256']:
                if expected[key]!=actual[key]:raise ValueError('Original-entry adoption proof failed: '+key)
    trained=guarded_train_single_models(schema,prepared,sample_cap,directory/'checkpointed',
                                       adoption_proof='SF2_ORIGINAL_NAIVE_MATRICES_AND_NODES_EXACT')
    if len(original['observations'])!=len(trained['training_tables']) or len(trained['training_tables'])!=len(schema.tables):
        raise ValueError('Original/checkpointed training table count mismatch')
    for expected,actual in zip(original['observations'],trained['training_tables']):
        for key in ['table','actual_training_rows','sample_matrix_sha256','structure_sha256']:
            if expected[key]!=actual[key]:raise ValueError('Checkpointed loop differs from actual original naive entry: '+expected['table']+' '+key)
    truth=population_truth_groups(ROOT/'output/full/ssb/paper/sf2_gate_v2/checkpoint.json')
    evaluated=evaluate_ssb(trained,truth,native['queries'],directory/'evaluation')
    if model_input_artifacts(schema,prepared)!=before:raise ValueError('Small-model input artifacts changed')
    report={'status':'PASS' if evaluated['point_query_errors']==0 and evaluated['ci_query_errors']==0 else 'MODEL_QUERY_ERRORS_RECORDED',
            'stage':'SF2_SMALL_SINGLE_MODEL_AQP_CI_ONLY','paper_scale_reached':False,'sample_cap':sample_cap,
            'population_rows':truth['population_rows'],'fact_sample_rows':truth['sample_rows'],
            'spn_count':trained['spn_count'],'training_tables':trained['training_tables'],'queries':evaluated['queries'],
            'point_query_errors':evaluated['point_query_errors'],'ci_query_errors':evaluated['ci_query_errors'],
            'sample_moments_native_sqlite_exact':True,'checkpointed_matches_original_naive_fit_and_structure_exact':True,
            'preparation_reused_without_recomputation':True,'source_inputs':inputs,'prepared_directory':str(prepared),
            'model_path':trained['model_path'],'directory':str(directory),'model_stage_binding':binding,
            'input_artifact_guard':str(directory/'checkpointed/model_guard.json'),'input_artifact_guard_sha256':digest(directory/'checkpointed/model_guard.json'),
            'evaluation_binding':evaluated['binding'],'evaluation_directory':evaluated['directory'],
            'historical_verified_learning_seconds':trained['learning_seconds'],'historical_original_naive_seconds':original['seconds'],
            'wall_scope':'This invocation reuses completed preparation/models; historical training times are separate. Initial training peak RAM was not captured.',
            'native_moment_seconds':native['native_seconds'],'wall_seconds':time.perf_counter()-started,
            'process_peak_working_set_bytes':windows_peak_working_set(),
            'ci_scope':'Same retained fact sample inner-joined to complete unique-PK dimensions; exact integer first/second moments, central90 reference; original model CI and released-reference discrepancy retained'}
    atomic_json(directory/'small_model_gate.json',report);atomic_json(OUTPUT/'sf2_small_model_gate_latest.json',report)
    atomic_json(directory/'small_model_gate.seal.json',{'sha256':digest(directory/'small_model_gate.json'),
                'model_sha256':digest(trained['model_path']),'guard_sha256':report['input_artifact_guard_sha256'],
                'evaluation_binding':evaluated['binding']})
    return report


def run_small_model(sample_cap=10000):
    path=OUTPUT/'sf2_small_model_gate_latest.json'
    # Always enter the lightweight worker: its physical dependency checks and
    # stage-specific seals are mandatory even when every trained model is cached.
    environment=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    start=time.perf_counter();result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B',__file__,'small-worker','--sample-cap',str(sample_cap)],
                            cwd=str(ROOT),env=environment,capture_output=True,text=True,errors='replace',timeout=1800)
    atomic_json(OUTPUT/'small_model_process.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'seconds':time.perf_counter()-start})
    if result.returncode:raise RuntimeError('Actual SSB small model gate failed: '+result.stderr[-6000:])
    return json.loads(path.read_text())


def raw_hash_and_rows(path):
    """One bounded binary pass verifies SHA and physical records, including EOF."""
    hasher=hashlib.sha256();rows=0;last=b''
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):
            hasher.update(block);rows+=block.count(b'\n');last=block[-1:]
    return hasher.hexdigest(),rows+int(bool(last) and last!=b'\n')


def sf500_final_inputs(result_path=None,checkpoint_path=None):
    """Reject incomplete generation before accessing the changing sample CSV."""
    from full_ssb_paper import author_truth,compare_truth,object_sha,TRUTH
    from schemas.ssb.schema import gen_500gb_ssb_schema
    result_path=Path(result_path or ROOT/'output/full/results/ssb_paper.json')
    checkpoint_path=Path(checkpoint_path or ROOT/'output/full/ssb/paper/sf500/checkpoint.json')
    result=json.loads(result_path.read_text())
    if result.get('status')!='PASS' or not result.get('complete') or result.get('rows')!=3000028242:
        raise ValueError('SF500 generation must be complete with all author truths PASS before sample access')
    if not result.get('row_count_matches_author') or not result.get('author_truth_comparison',{}).get('match'):
        raise ValueError('SF500 author row count and all13 truth groups must match')
    state=json.loads(checkpoint_path.read_text());run=state['binding']
    plan_path=ROOT/'output/full/ssb/paper/sf500_plan.json';generation_plan=json.loads(plan_path.read_text())
    if result['plan_sha256']!=object_sha(generation_plan):raise ValueError('Completed generation plan seal changed')
    if (run['scale']!=500 or run['shards']!=generation_plan['shards'] or state['next_shard']!=run['shards']+1 or
        [x['shard'] for x in state['committed_shards']]!=list(range(1,run['shards']+1))):
        raise ValueError('SF500 generation is missing committed shards')
    if state['rows']!=3000028242 or result['sample_rows']!=state['sample_rows']:
        raise ValueError('SF500 final row counts disagree')
    if not 1000000<=state['sample_rows']<20000000:raise ValueError('Final sample is outside proven preparation domain')
    if (run['inputs']!=generation_plan['binding'] or run['sample_seed']!=generation_plan['sample_seed'] or
        run['sample_probability']!=generation_plan['sample_probability']):raise ValueError('SF500 source/seed/probability changed')
    if run['inputs']['queries_sha256']!=digest(SQL_PATH) or run['inputs']['author_truth_sha256']!=digest(TRUTH):
        raise ValueError('Generation/evaluation author SQL or truth source changed')
    comparison=compare_truth(state['aggregates'],author_truth())
    if not comparison['match']:raise ValueError('Independent comparison to all13 author truths failed')
    data=ROOT/'data/ssb/sf500_paper';dimension_path=data/'dimensions/dimensions.json'
    dimensions=json.loads(dimension_path.read_text())
    if dimensions['status']!='PASS' or dimensions['binding']['scale']!=500 or dimensions['files']!=run['dimensions']:
        raise ValueError('SF500 dimension binding changed')
    expected_dimensions={'customer':15000000,'supplier':1000000,'part':1800000,'date':2556}
    if {name:entry['rows'] for name,entry in dimensions['files'].items()}!=expected_dimensions:
        raise ValueError('SF500 dimension row counts differ from paper-scale schema')
    schema=gen_500gb_ssb_schema(str(data/'dimensions/{}.tbl'));files={}
    for table in schema.tables:
        if table.table_name=='lineorder':
            path=data/'lineorder_sampled.csv';expected=state['sample_sha256'];size=state['sample_bytes']
            expected_rows=state['sample_rows']
            table.table_size=state['rows'];table.sample_rate=float(run['sample_probability'])
            if result['sample_sha256']!=expected:raise ValueError('Final sample digest receipts disagree')
        else:
            source='date' if table.table_name=='dwdate' else table.table_name
            entry=dimensions['files'][source];path=data/'dimensions'/(source+'.tbl')
            expected,size=entry['sha256'],entry['bytes'];table.table_size=entry['rows'];table.sample_rate=1
            expected_rows=entry['rows']
        if path.stat().st_size!=size or raw_hash_and_rows(path)!=(expected,expected_rows):
            raise ValueError('SF500 raw input artifact SHA/physical row count changed: '+table.table_name)
        table.csv_file_location=str(path)
        files[table.table_name]={'path':str(path),'sha256':expected,'bytes':size,'table_size':table.table_size,'sample_rate':table.sample_rate}
    return schema,{'generation_result_sha256':digest(result_path),'checkpoint_sha256':digest(checkpoint_path),
                   'dimension_receipt_sha256':digest(dimension_path),'generation_plan_sha256':digest(plan_path),
                   'author_truth_sha256':digest(TRUTH),'queries_sha256':digest(SQL_PATH),'files':files,
                   'sample_rows':state['sample_rows'],'population_rows':state['rows'],'sample_seed':run['sample_seed'],
                   'sample_probability':run['sample_probability'],'all_author_groups_exact':True},checkpoint_path


def available_memory_bytes():
    if os.name!='nt':
        return int(os.sysconf('SC_AVPHYS_PAGES'))*int(os.sysconf('SC_PAGE_SIZE'))
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(x,ctypes.c_uint64) for x in
                   ['total_physical','available_physical','total_page','available_page','total_virtual','available_virtual','extended']]
    record=Memory();record.length=ctypes.sizeof(record)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(record)):raise ctypes.WinError()
    return record.available_physical


def formal_plan():
    """Only seal the future entry. Do not hash a currently growing sample."""
    import shutil
    small_path=OUTPUT/'sf2_small_model_gate_latest.json';small=json.loads(small_path.read_text())
    small_seal=Path(small['directory'])/'small_model_gate.seal.json'
    if small['status']!='PASS' or small['sample_cap']!=10000 or small['point_query_errors'] or small['ci_query_errors']:
        raise ValueError('Actual SF2 10K model/all13 point+CI gate must pass first')
    if (json.loads(small_seal.read_text())['sha256']!=digest(Path(small['directory'])/'small_model_gate.json') or
        digest(small_path)!=digest(Path(small['directory'])/'small_model_gate.json')):
        raise ValueError('SF2 small-model report seal changed')
    schema,_,prepared=sf2_preparation_reuse()
    guard=json.loads(Path(small['input_artifact_guard']).read_text())
    if (digest(small['input_artifact_guard'])!=small['input_artifact_guard_sha256'] or
        guard['binding']['inputs']!=model_input_artifacts(schema,prepared)):
        raise ValueError('SF2 small-model input artifact guard changed')
    for name,sha in guard['model_files_sha256'].items():
        if digest(Path(small['model_path']).parent/name)!=sha:raise ValueError('SF2 model artifact changed')
    evaluated=small['evaluation_binding']
    if (evaluated['sql_sha256']!=digest(SQL_PATH) or evaluated['ci_formula_sha256']!=digest(ROOT/'code/full_flights_model.py') or
        evaluated['cache_adapter_sha256']!=digest(ROOT/'code/full_factor_cache.py') or
        evaluated['code']!=component_code_hash(['evaluate_ssb','population_truth_groups'])):
        raise ValueError('SF2 evaluation source changed; refresh small-model evaluation without retraining')
    for index in range(13):
        path=Path(small['evaluation_directory'])/('query_%02d.json'%index)
        seal=json.loads(path.with_suffix('.seal.json').read_text())
        if seal['binding']!=evaluated or digest(path)!=seal['sha256']:raise ValueError('SF2 query artifact changed')
    import full_ssb_guard as outer_guard
    outer=outer_guard.seal_small_gate()
    existing=sum(p.stat().st_size for folder in [ROOT/'data/ssb',ROOT/'output/full/ssb'] for p in folder.rglob('*') if p.is_file())
    # Main HDF ~2.3GB, unmatched HDF <=0.9GB, counts/means <=0.5GB,
    # model/indices/HDF overhead reserve ~0.8GB. This is a budget, not a measurement.
    budget={'additional_preparation_models_budget_bytes':int(4.5*1024**3),'existing_ssb_bytes_at_plan':existing,
            'total_ssb_budget_bytes':10*1024**3,'minimum_free_disk_bytes':6*1024**3,
            'estimated_training_peak_bytes':4*1024**3,'minimum_available_memory_bytes':4*1024**3,
            'estimated_preparation_peak_bytes':1536*1024**2,'ci_native_dimension_bytes_approx':110*1024**2,
            'free_disk_bytes_at_plan':shutil.disk_usage(str(ROOT)).free,
            'available_memory_bytes_at_plan':available_memory_bytes(),
            'limit':'Planning bounds only. Original pd.read_hdf/post_sampling keeps numeric tables in RAM; no formal timing/peak measurement yet.'}
    generation=json.loads((ROOT/'output/full/results/ssb_paper.json').read_text())
    from full_common import algorithm_seal
    result={'status':'READY_FOR_FORMAL_WHEN_GENERATION_AND_MEMORY_GATES_PASS','formal_training_started':False,
            'code_sha256':digest(__file__),'algorithm_seal':algorithm_seal(),'sql_sha256':digest(SQL_PATH),
            'outer_guard_source_sha256':digest(outer_guard.__file__),'complete_dependencies':outer_guard.dependencies(),
            'small_outer_guard_sha256':digest(OUTPUT/'sf2_outer_guard_verification.json'),
            'small_model_gate_sha256':digest(small_path),'small_model_gate_seal_sha256':digest(small_seal),
            'samples_per_spn':1000000,'ensemble_strategy':'single','post_sampling_factor':10,'rdc_threshold':.3,'seed':1,
            'required_fact_rows':3000028242,'expected_fact_sample_rows':10000000,'expected_dimension_rows':
            {'customer':15000000,'supplier':1000000,'part':1800000,'dwdate':2556},
            'required_generation_gate':'complete PASS, exact3000028242, all13 author integer groups exact, final physical SHA/counts/seed/source match',
            'observed_generation_status':generation['status'],'resources':budget,
            'resume':'Completed preparation tables, single-table RNG/model checkpoints and per-query atomic seals; partial uncommitted HDF stops, never silently reuses.',
            'command':'.venv/Scripts/python.exe -B code/full_ssb_model.py formal-all --formal-memory-approved',
            'performance_scope':'SF2 10K gate validates execution/equivalence only; no formal1M accuracy or timing claim.'}
    atomic_json(OUTPUT/'formal_plan.json',result)
    atomic_json(OUTPUT/'formal_plan.seal.json',{'sha256':digest(OUTPUT/'formal_plan.json'),'code_sha256':result['code_sha256']})
    return result


def formal_generation_gate():
    try:
        _,inputs,_=sf500_final_inputs()
        result={'status':'PASS','stage':'SSB_SF500_FINAL_SOURCE_GATE_ONLY','formal_training_started':False,'inputs':inputs}
    except ValueError as error:
        result={'status':'BLOCKED_GENERATION_GATE','stage':'SSB_SF500_FINAL_SOURCE_GATE_ONLY',
                'formal_training_started':False,'reason':str(error)}
    atomic_json(OUTPUT/'formal_generation_gate.json',result)
    return result


def formal_worker(memory_approved=False):
    if not memory_approved:raise ValueError('Root memory release is required before formal SSB preparation/training')
    from full_ssb_paper import RunLock
    import full_ssb_guard as outer_guard
    with RunLock(OUTPUT/'formal_model.lock'):
        binding={'plan_sha256':digest(OUTPUT/'formal_plan.json'),'complete_dependencies':outer_guard.dependencies(),
                 'outer_guard_source_sha256':digest(outer_guard.__file__)}
        def validate(report):
            schema,inputs,_=sf500_final_inputs()
            if report['inputs']!=inputs:raise ValueError('Final formal-run raw input check failed')
            directory=Path(report['directory'])
            outer_guard.require_prepared_pass(schema,directory/'prepared')
            model=json.loads((directory/'model/model.json').read_text());outer_guard.require_model_pass(model)
            outer_guard.query_bundle(report['evaluation_directory'],report['evaluation_binding'])
            if report['complete_dependencies']!=outer_guard.dependencies():raise ValueError('Final formal-run dependencies changed')
        report=outer_guard.transaction(OUTPUT/'formal_runs'/binding['plan_sha256'],'FORMAL',binding,formal_worker_locked,validate)
        directory=Path(report['directory']);atomic_json(directory/'verification.json',report)
        atomic_json(directory/'verification_seal.json',{'sha256':digest(directory/'verification.json'),
                    'input_guard_sha256':report['input_artifact_guard_sha256'],'evaluation_binding':report['evaluation_binding'],
                    'formal_outer_receipt_sha256':digest(OUTPUT/'formal_runs'/binding['plan_sha256']/'receipt.json')})
        atomic_json(ROOT/'output/full/results/ssb_model_aqp_ci.json',report)
        return report


def formal_worker_locked():
    import shutil
    plan_path=OUTPUT/'formal_plan.json';plan=json.loads(plan_path.read_text())
    if json.loads((OUTPUT/'formal_plan.seal.json').read_text())['sha256']!=digest(plan_path):
        raise ValueError('Formal resource/source plan checksum changed')
    from full_common import algorithm_seal
    import full_ssb_guard as outer_guard
    if plan['code_sha256']!=digest(__file__) or plan['algorithm_seal']!=algorithm_seal() or plan['sql_sha256']!=digest(SQL_PATH):
        raise ValueError('Formal reviewed source plan changed; regenerate/review the plan')
    if (plan['outer_guard_source_sha256']!=digest(outer_guard.__file__) or
        plan['complete_dependencies']!=outer_guard.dependencies()):raise ValueError('Complete parser/runtime/SPFlow or outer guard source changed')
    if available_memory_bytes()<plan['resources']['minimum_available_memory_bytes']:
        raise ValueError('Insufficient available memory for original HDF/post-sampling training; release other workloads first')
    if shutil.disk_usage(str(ROOT)).free<plan['resources']['minimum_free_disk_bytes']:
        raise ValueError('Insufficient disk budget for formal SSB preparation')
    started=time.perf_counter();schema,inputs,checkpoint=sf500_final_inputs()
    identity=hashlib.sha256(json.dumps({'inputs':inputs,'prep':preparation_code_sha256(),
             'outer_guard_sha256':digest(outer_guard.__file__),'complete_dependencies':outer_guard.value_hash(outer_guard.dependencies())},sort_keys=True).encode()).hexdigest()[:16]
    directory=OUTPUT/('sf500_'+identity);directory.mkdir(parents=True,exist_ok=True)
    atomic_json(directory/'final_inputs.json',inputs)
    existing=sum(p.stat().st_size for folder in [ROOT/'data/ssb',ROOT/'output/full/ssb'] for p in folder.rglob('*') if p.is_file())
    if not (directory/'prepared/seal.json').exists() and existing+plan['resources']['additional_preparation_models_budget_bytes']>10*1024**3:
        raise ValueError('Projected total SSB storage exceeds10GiB; preserve artifacts and review the budget')
    prepared=directory/'prepared';outer_guard.guarded_prepare(schema,prepared,chunk_rows=100000)
    native=sample_moments_native(schema,inputs['sample_rows'],directory/'sample_moments_native')
    trained=outer_guard.guarded_train(schema,prepared,1000000,directory/'model')
    truth=population_truth_groups(checkpoint)
    evaluated=outer_guard.guarded_evaluate(trained,truth,native['queries'],directory/'evaluation')
    # Recheck final physical sources and generation receipts after the whole stage.
    if sf500_final_inputs()[1]!=inputs:raise ValueError('Formal raw inputs changed during model/evaluation')
    outer_guard.require_prepared_pass(schema,prepared);outer_guard.require_model_pass(trained)
    report={'status':'PASS' if evaluated['point_query_errors']==0 and evaluated['ci_query_errors']==0 else 'MODEL_QUERY_ERRORS_RECORDED',
            'stage':'SSB_SF500_SINGLE_1M_AQP_CI','full_paper_reproduction_complete':False,'paper_population_exact':True,
            'formal_training_started':True,'plan_sha256':digest(plan_path),'directory':str(directory),'inputs':inputs,
            'model_path':trained['model_path'],'model_sha256':digest(trained['model_path']),
            'input_artifact_guard_sha256':digest(directory/'model/model_guard.json'),
            'outer_stage_receipts_sha256':{str(outer_guard.home_for(directory/name,kind)/'receipt.json'):
                digest(outer_guard.home_for(directory/name,kind)/'receipt.json')
                for name,kind in [('prepared','prepared'),('model','model'),('evaluation','evaluation')]},
            'complete_dependencies':outer_guard.dependencies(),'outer_guard_source_sha256':digest(outer_guard.__file__),
            'training_tables':trained['training_tables'],'historical_learning_seconds':trained['learning_seconds'],
            'spn_count':trained['spn_count'],'queries':evaluated['queries'],'evaluation_binding':evaluated['binding'],
            'evaluation_directory':evaluated['directory'],'point_query_errors':evaluated['point_query_errors'],
            'ci_query_errors':evaluated['ci_query_errors'],'sample_moments_native_seconds':native['native_seconds'],
            'ci_scope':'Same retained Bernoulli fact sample with all complete unique-PK dimensions; central90 reference, no FPC. Original model CI and released CI comparison retained.',
            'normalizer_scope':'Original preparation and naive entry retain n/p fact-length estimate; exact3B truth is used for evaluation/reference only.',
            'wall_seconds':time.perf_counter()-started,'process_peak_working_set_bytes':windows_peak_working_set()}
    return report


def run_formal(memory_approved=False):
    if not memory_approved:raise ValueError('Root memory release is required before formal SSB launch')
    # Keep the controlling process small and force original RDC to one worker.
    environment=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),'-B',__file__,'formal-worker','--formal-memory-approved'],
                          cwd=str(ROOT),env=environment,capture_output=True,text=True,errors='replace')
    atomic_json(OUTPUT/'formal_process.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    if result.returncode:raise RuntimeError('Formal SSB worker failed: '+result.stderr[-6000:])
    return json.loads((ROOT/'output/full/results/ssb_model_aqp_ci.json').read_text())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['sf2-gate','small-model','small-worker','formal-plan','formal-gate','formal-all','formal-worker'])
    parser.add_argument('--sample-cap',type=int,default=10000)
    parser.add_argument('--formal-memory-approved',action='store_true')
    arguments=parser.parse_args()
    if arguments.action=='sf2-gate':report=run_sf2_gate()
    elif arguments.action=='small-worker':report=small_model_worker(arguments.sample_cap)
    elif arguments.action=='small-model':report=run_small_model(arguments.sample_cap)
    elif arguments.action=='formal-plan':report=formal_plan()
    elif arguments.action=='formal-gate':report=formal_generation_gate()
    elif arguments.action=='formal-worker':report=formal_worker(arguments.formal_memory_approved)
    else:report=run_formal(arguments.formal_memory_approved)
    print(json.dumps({k:report[k] for k in ['status','stage','wall_seconds','process_peak_working_set_bytes'] if k in report}))
    if arguments.action=='formal-gate' and report['status']!='PASS':raise SystemExit(2)
