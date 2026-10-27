"""Execute all JOB-light COUNT queries in a visible, resumable local audit window."""
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT.parent
PG=Path(os.environ.get('DEEPDB_PG_HOME', r'D:\codex\deepdb-postgresql-20261027'))
OUT=PROJECT/'output/truth_audit_20261027'
OUT.mkdir(parents=True,exist_ok=True)
EVENTS=queue.Queue()
STOP=threading.Event()
ACTIVE={'connection':None,'query':None,'started':None,'finished':False}
START=time.perf_counter()
BIG_RETRY=os.environ.get('TRUTH_AUDIT_BIG_RETRY')=='1'
EXACT_REWRITE=os.environ.get('TRUTH_AUDIT_EXACT_REWRITE')=='1'
FIRST_LIMIT=600 if BIG_RETRY else 120
SECOND_LIMIT=900 if BIG_RETRY else 600
WORK_MEM='64MB' if BIG_RETRY else '32MB'
TEMP_LIMIT='16GB' if BIG_RETRY else '4GB'
PARALLEL=2 if BIG_RETRY else 0
PREVIOUS=json.loads((OUT/'run.json').read_text(encoding='utf-8')) if (OUT/'run.json').exists() else {}

def now():return datetime.now().astimezone().isoformat()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic_json(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)

def log(message,query=None):
    EVENTS.put(('log',message))
    with (OUT/'progress.log').open('a',encoding='utf-8') as f:f.write(now()+' '+message+'\n')
    if query is not None:EVENTS.put(('sql',query))

FIELDS=['query_no','status','actual_count','official_count','difference','seconds','timeout_seconds','attempt','sql','error','execution_method','executed_sql']
results={}
state={'status':'PREPARING','started_at':now(),'scope':'Execute raw workload COUNT queries, not EXPLAIN estimates',
       'query_timeout_seconds':FIRST_LIMIT,'retry_timeout_seconds':SECOND_LIMIT,'overall_limit_seconds':7200,
       'large_query_retry':BIG_RETRY,'prior_elapsed_seconds':PREVIOUS.get('cumulative_wall_seconds',PREVIOUS.get('elapsed_seconds',0)),
       'exact_rewrite_mode':EXACT_REWRITE,
       'attempts':0,'tables':{},'settings':{},'output_directory':str(OUT),
       'path_repairs':'Moved project: venv home repaired; new ASCII junction points to current PostgreSQL storage.'}

def checkpoint():
    ordered=[results[i] for i in sorted(results)]
    state['completed_queries']=sum(r['status'] in ['MATCH','MISMATCH'] for r in ordered)
    state['matched_queries']=sum(r['status']=='MATCH' for r in ordered)
    state['mismatched_queries']=sum(r['status']=='MISMATCH' for r in ordered)
    state['unresolved_queries']=[i for i in range(70) if i not in results or results[i]['status'] not in ['MATCH','MISMATCH']]
    state['elapsed_seconds']=time.perf_counter()-START
    state['cumulative_wall_seconds']=state['prior_elapsed_seconds']+state['elapsed_seconds']
    atomic_json(OUT/'run.json',state)
    temp=OUT/'truth_counts.csv.tmp'
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(ordered)
        f.flush();os.fsync(f.fileno())
    temp.replace(OUT/'truth_counts.csv')
    EVENTS.put(('counts',dict(state)))

def report():
    grouped=sum(r.get('execution_method')=='factorized_exact_sql' for r in results.values())
    for zh,language in [(True,'中文版'),(False,'英文版')]:
        folder=ROOT/'学习记录/图表与解释'/language
        folder.mkdir(parents=True,exist_ok=True)
        complete=state['completed_queries'];matched=state['matched_queries'];mismatch=state['mismatched_queries']
        lines=[('JOB-light 全量真值独立重算（2026-10-27）' if zh else 'Independent JOB-light True-Count Audit (2026-10-27)'),'',
          ('结果：实际执行完成 %d/70 条，与官方答案一致 %d 条，不一致 %d 条，未解决 %d 条。' if zh else
           'Results: %d/70 executed successfully; %d match official counts; %d mismatch; %d unresolved.')%(complete,matched,mismatch,len(state['unresolved_queries'])),
          ('状态：'+state['status'] if zh else 'Status: '+state['status']),
          ('完整过程耗时 %.2f 秒（包括检查、查询及收尾，累计值见 run.json）。' if zh else
           'Elapsed %.2f seconds including checks, queries and cleanup; see run.json for final duration.')%state['cumulative_wall_seconds'],'',
          '方法：' if zh else 'Method:',
          ('原始 SQL 直接执行成功 %d 条，等价分组计数 SQL 完成 %d 条。实际数量只来自数据库返回值，之后与官方 CSV 比较，没有使用估计值或官方答案填充实际数量。' if zh else
           '%d queries completed by direct original SQL execution and %d by equivalent grouped-count SQL. Actual counts come only from database results and are then compared with official references; estimates/reference values never populate actual counts.')%(complete-grouped,grouped),
          '先核对查询文件与已有实验的指纹、SQL 及编号，检查六张数据库表行数。数据库连接为只读；逐条顺序执行，每条结束即保存。' if zh else
          'Matched workload hashes, SQL and IDs against earlier experiments and checked all six table counts. A read-only database connection executes queries sequentially, checkpointing after each result.',
          ('本轮设置：work_mem=%s，查询并行上限 %d，临时文件上限 %s；首次每条 %d 秒，重试 %d 秒。大查询续跑禁用嵌套循环；JIT 关闭。初轮使用 32MB/不并行/4GB，慢查询的失败与重试记录均保留。' if zh else
           'Current run: work_mem=%s, max parallel workers/query %d, temp_file_limit=%s; first attempt %d seconds, retry %d seconds. Large-query retries disable nested loops; JIT is off. Initial settings were 32MB/no parallelism/4GB; failed attempts are retained.')%(WORK_MEM,PARALLEL,TEMP_LIMIT,FIRST_LIMIT,SECOND_LIMIT),'',
          '结论与范围：' if zh else 'Interpretation and scope:',
          ('70 条答案均已从数据库独立计算，与官方答案一致；其中 %d 条采用等价分组计数，不宣称 70 条原始 SQL 全部直接执行成功。'%grouped if complete==matched==70 else
           '仅能对已经成功执行的查询给出核验结论；未解决或不一致部分见逐条表格。') if zh else
          ('All 70 answers were independently computed and match the official counts; %d used equivalent grouped-count SQL. This is not a claim that all original SQL executions succeeded.'%grouped if complete==matched==70 else
           'Only successfully executed queries have audit conclusions; see the per-query table for unresolved or mismatching cases.'),
          '独立重算指使用原始 SQL 在本机数据库重新计算，不表示由另一个团队、另一份数据或独立实现的查询引擎完成。' if zh else
          'Independent recomputation means locally executing the original SQL, not an audit by another team, another dataset, or an independently implemented SQL engine.',
          '这次测得的是数据库实际 COUNT 执行和返回时间，受缓存、执行顺序、索引及负载影响，不与 DeepDB 的估计时间直接计算加速比。' if zh else
          'These are actual COUNT execution/return timings, affected by cache, query order, indexes and load. They are not directly comparable to DeepDB estimation latency as a speedup ratio.',
          '本次没有训练 RDC 优化模型，也不等于完成独立核心算法重实现。' if zh else
          'This does not train the optimized RDC ensemble or establish an independent core-algorithm reimplementation.','',
          '逐条结果（query_no 从 0 开始）：' if zh else 'Per-query results (zero-based query_no):',
          'ID | status | actual | official | difference | seconds']
        for i in range(70):
            r=results.get(i,{})
            lines.append('%d | %s | %s | %s | %s | %s'%(i,r.get('status','NOT_RUN'),r.get('actual_count',''),r.get('official_count',''),r.get('difference',''),r.get('seconds','')))
        lines+=['','结果文件：DeepDB/output/truth_audit_20261027/truth_counts.csv、run.json、attempts.jsonl、progress.log、verification.json。' if zh else
          'Results: DeepDB/output/truth_audit_20261027/{truth_counts.csv,run.json,attempts.jsonl,progress.log,verification.json}.']
        (folder/('10_全量真值核验报告.txt' if zh else '10_full_ground_truth_audit_report.txt')).write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')

def worker():
    started_server=False;conn=None
    try:
        state['status']='RUNNING'
        log('步骤 1/4：检查原始查询、数据来源和保存的数据库')
        truthpath=PROJECT/'code/benchmarks/job-light/sql/job_light_true_cardinalities.csv'
        querypath=PROJECT/'code/benchmarks/job-light/sql/job_light_queries.sql'
        state['query_sha256']=digest(querypath);state['official_truth_sha256']=digest(truthpath)
        state['script_sha256']=digest(Path(__file__))
        old=json.loads((PROJECT/'output/postgresql_baseline_20261015/run.json').read_text(encoding='utf-8'))
        assert state['query_sha256']==old['query_file_sha256']
        assert state['official_truth_sha256']==old['truth_file_sha256']
        queries=[q.strip()+';' for q in querypath.read_text(encoding='utf-8').split(';') if q.strip()]
        with truthpath.open(encoding='utf-8',newline='') as f:truths=list(csv.DictReader(f))
        assert len(queries)==len(truths)==70
        for i,(query,row) in enumerate(zip(queries,truths)):
            assert int(row['query_no'])==i and query==row['query'].strip()
            assert re.match(r'^SELECT\s+COUNT\(\*\)\s+FROM\s+',query,re.I)
        prior=OUT/'truth_counts.csv'
        if prior.exists():
            with prior.open(encoding='utf-8-sig',newline='') as f:saved=list(csv.DictReader(f))
            for r in saved:
                i=int(r['query_no'])
                assert r['sql']==queries[i] and int(r['official_count'])==int(truths[i]['cardinality_true'])
                if r['status'] in ['MATCH','MISMATCH']:
                    r.update(query_no=i,actual_count=int(r['actual_count']),official_count=int(r['official_count']),difference=int(r['difference']),seconds=float(r['seconds']),timeout_seconds=int(r['timeout_seconds']),attempt=int(r['attempt']))
                    r.setdefault('execution_method','original_sql');r.setdefault('executed_sql',r['sql'])
                    results[i]=r
        checkpoint()
        control=PG/'pgsql/bin/pg_ctl.exe'
        status=subprocess.run([str(control),'-D',str(PG/'data'),'status'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if status.returncode:
            log('启动本机 PostgreSQL（使用已保存数据，无需重新导入）')
            with (OUT/'server_start.log').open('wb') as f:
                s=subprocess.run([str(control),'-D',str(PG/'data'),'-l',str(PG/'server.log'),'-w','start'],stdout=f,stderr=subprocess.STDOUT,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
            if s.returncode:raise RuntimeError('数据库启动失败，见 server_start.log')
            started_server=True
        credential=json.loads((ROOT/'tools/postgresql/local_credentials.json').read_text(encoding='utf-8'))
        conn=psycopg2.connect(host='127.0.0.1',port=55432,user=credential['user'],password=credential['password'],dbname='deepdb_joblight',connect_timeout=10)
        ACTIVE['connection']=conn
        conn.set_session(readonly=True,autocommit=True)
        with conn.cursor() as cur:
            for setting in ['SET statement_timeout=120000','SET max_parallel_workers_per_gather=%d'%PARALLEL,"SET work_mem='%s'"%WORK_MEM,'SET jit=off',"SET temp_file_limit='%s'"%TEMP_LIMIT]:
                cur.execute(setting)
            if BIG_RETRY:cur.execute('SET enable_nestloop=off')
            cur.execute('SELECT version()');state['postgresql_version']=cur.fetchone()[0]
            for key in ['transaction_read_only','max_parallel_workers_per_gather','work_mem','jit','temp_file_limit','enable_nestloop','data_directory']:
                cur.execute('SHOW '+key);state['settings'][key]=cur.fetchone()[0]
            assert state['settings']['transaction_read_only']=='on'
            expected=json.loads((PROJECT/'output/results/data_audit.json').read_text())['row_counts']
            for table,total in expected.items():
                if STOP.is_set():raise InterruptedError('用户停止')
                log('步骤 1/4：核对表行数 '+table)
                cur.execute('SELECT COUNT(*) FROM '+table)
                actual=cur.fetchone()[0];assert actual==total,(table,actual,total)
                state['tables'][table]=actual;checkpoint()
            log('步骤 2/4：开始逐条执行 70 条真实 COUNT 查询（不是估计）')
            if EXACT_REWRITE:
                from joblight_exact_count import factorized_count_sql
                state['factorized_source_sha256']=digest(PROJECT/'code/joblight_exact_count.py')
                state['factorized_cross_checks']=[]
                for check_id in [0,14,34,57]:
                    if STOP.is_set():raise InterruptedError('用户停止')
                    assert check_id in results and results[check_id]['status']=='MATCH'
                    exact_sql=factorized_count_sql(queries[check_id])
                    log('交叉验证等价计数 ID %d：与此前原始 SQL 实算值比较'%check_id,exact_sql)
                    ACTIVE.update(query=check_id,started=time.perf_counter())
                    cur.execute('SET statement_timeout=300000')
                    begin=time.perf_counter();cur.execute(exact_sql);value=int(cur.fetchone()[0])
                    assert value==results[check_id]['actual_count'], ('Grouped count validation failed',check_id,value)
                    state['factorized_cross_checks'].append({'query_no':check_id,'original_count':results[check_id]['actual_count'],'grouped_count':value,'seconds':time.perf_counter()-begin,'original_sql':queries[check_id],'executed_sql':exact_sql})
                    atomic_json(OUT/'factorized_cross_checks.json',state['factorized_cross_checks'])
                    log('交叉验证 ID %d：一致，实际值 %d'%(check_id,value))
                    ACTIVE.update(query=None,started=None)
                    checkpoint()
            if results:log('已读取并保留 %d 条成功结果，只计算未完成查询。'%len(results))
            for attempt,limit in [(1,FIRST_LIMIT),(2,SECOND_LIMIT)]:
                pending=[i for i in range(70) if i not in results or results[i]['status'] not in ['MATCH','MISMATCH']]
                if not pending:break
                if attempt==2:log('步骤 3/4：重试超时或失败查询，上限每条 %d 秒'%SECOND_LIMIT)
                for i in pending:
                    if STOP.is_set():raise InterruptedError('用户停止，已有结果保存')
                    remaining=7200-(time.perf_counter()-START)
                    if remaining<5:raise TimeoutError('整体两小时限额已到，保存当前结果')
                    timeout=min(limit,max(1,int(remaining)))
                    cur.execute('SET statement_timeout=%s',(timeout*1000,))
                    ACTIVE.update(query=i,started=time.perf_counter())
                    execution_sql=factorized_count_sql(queries[i]) if EXACT_REWRITE else queries[i]
                    log('正在计算第 %d/70 条（query_no=%d），单条限时 %d 秒%s'%(i+1,i,timeout,'，使用等价精确分组计数' if EXACT_REWRITE else ''),execution_sql)
                    checkpoint()
                    began=time.perf_counter()
                    r={'query_no':i,'status':'ERROR','actual_count':'','official_count':int(truths[i]['cardinality_true']),
                       'difference':'','seconds':0,'timeout_seconds':timeout,'attempt':attempt,'sql':queries[i],'error':'',
                       'execution_method':'factorized_exact_sql' if EXACT_REWRITE else 'original_sql','executed_sql':execution_sql}
                    try:
                        cur.execute(execution_sql);actual=cur.fetchone()[0]
                        if EXACT_REWRITE:actual=int(actual)
                        if not isinstance(actual,int):raise TypeError('COUNT result is not an integer')
                        r['actual_count']=actual;r['difference']=actual-r['official_count']
                        r['status']='MATCH' if r['difference']==0 else 'MISMATCH'
                    except psycopg2.errors.QueryCanceled as exc:
                        r['status']='CANCELLED' if STOP.is_set() else 'TIMEOUT';r['error']=str(exc).strip()
                    except psycopg2.Error as exc:
                        r['error']=str(exc).strip()
                    finally:
                        r['seconds']=round(time.perf_counter()-began,6)
                        results[i]=r;state['attempts']+=1
                        with (OUT/'attempts.jsonl').open('a',encoding='utf-8') as f:
                            f.write(json.dumps(dict(r,finished_at=now()),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
                        checkpoint();ACTIVE.update(query=None,started=None)
                    log('结果 ID %d：%s；实际=%s，官方=%s，用时 %.2f 秒'%(i,r['status'],r['actual_count'],r['official_count'],r['seconds']))
            state['status']='PASS' if state['matched_queries']==70 else 'COMPLETED_WITH_MISMATCHES' if state['completed_queries']==70 else 'PARTIAL'
    except InterruptedError as exc:
        state['status']='STOPPED';state['error']=str(exc);log(str(exc))
    except BaseException as exc:
        state['status']='FAILED_OR_STOPPED';state['error']=str(exc);log('停止：'+str(exc))
        (OUT/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        ACTIVE['connection']=None
        if conn is not None:conn.close()
        if started_server:
            log('步骤 4/4：关闭本次启动的数据库，释放内存并保留数据')
            with (OUT/'server_stop.log').open('wb') as f:
                p=subprocess.run([str(PG/'pgsql/bin/pg_ctl.exe'),'-D',str(PG/'data'),'-w','stop','-m','fast'],stdout=f,stderr=subprocess.STDOUT,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
            state['database_stopped']=p.returncode==0
        state['ended_at']=now();checkpoint()
        proof={'status':state['status'],'executed':state['completed_queries'],'matched':state['matched_queries'],'mismatched':state['mismatched_queries'],
               'unresolved':state['unresolved_queries'],'actual_source':'PostgreSQL execution of raw SELECT COUNT(*) SQL',
               'query_sha256':state.get('query_sha256'),'official_truth_sha256':state.get('official_truth_sha256')}
        atomic_json(OUT/'verification.json',proof)
        report()
        ACTIVE['finished']=True
        log('任务结束：%s；完成 %d/70，匹配 %d/70。中英文报告已保存。'%(state['status'],state['completed_queries'],state['matched_queries']))
        EVENTS.put(('finished',state['status']))

window=tk.Tk()
window.title('DeepDB 真值独立重算 - 等价精确核验' if EXACT_REWRITE else 'DeepDB 真值独立重算 - 大查询续跑' if BIG_RETRY else 'DeepDB 真值独立重算 - 70 条查询实时进度')
window.geometry('1040x730+20+15')
window.configure(bg='#f5f7fa')
style=ttk.Style();style.theme_use('clam')
style.configure('TLabel',font=('Microsoft YaHei UI',11),background='#f5f7fa')
frame=ttk.Frame(window,padding=18);frame.pack(fill='both',expand=True)
ttk.Label(frame,text='70 条查询：真正执行并数清楚结果',font=('Microsoft YaHei UI',19,'bold')).pack(anchor='w')
ttk.Label(frame,text='只读计算 · 每条立即保存 · 单条限时 %d 秒 · 保留已成功的结果'%FIRST_LIMIT).pack(anchor='w',pady=(7,12))
countvar=tk.StringVar(value='准备检查数据库和查询文件…')
ttk.Label(frame,textvariable=countvar,font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w')
bar=ttk.Progressbar(frame,maximum=70);bar.pack(fill='x',pady=10)
activevar=tk.StringVar(value='窗口打开后 8 秒自动开始，请保持窗口开启。')
ttk.Label(frame,textvariable=activevar).pack(anchor='w',pady=4)
ttk.Label(frame,text='当前执行的 SQL：').pack(anchor='w')
sqlbox=tk.Text(frame,height=5,wrap='word',font=('Consolas',11),bg='#edf3fa',relief='flat');sqlbox.pack(fill='x',pady=6)
sqlbox.configure(state='disabled')
ttk.Label(frame,text='过程与结果（MATCH 表示计算值和官方答案一致）：').pack(anchor='w',pady=(8,4))
logframe=ttk.Frame(frame);logframe.pack(fill='both',expand=True)
logbox=tk.Text(logframe,height=10,wrap='word',font=('Microsoft YaHei UI',10),bg='white',relief='flat')
scroll=ttk.Scrollbar(logframe,command=logbox.yview);logbox.configure(yscrollcommand=scroll.set)
scroll.pack(side='right',fill='y');logbox.pack(side='left',fill='both',expand=True);logbox.configure(state='disabled')
buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=(10,0))

def request_stop():
    if ACTIVE['finished']:window.destroy();return
    if messagebox.askyesno('停止并保存','停止当前计算并保存已完成的结果？'):
        STOP.set()
        c=ACTIVE.get('connection')
        if c is not None:
            try:c.cancel()
            except Exception:pass
        activevar.set('正在停止并保存，请等待收尾完成。')

stopbutton=ttk.Button(buttons,text='停止并保存',command=request_stop);stopbutton.pack(side='right')
ttk.Label(buttons,text='结果保存位置：DeepDB/output/truth_audit_20261027').pack(side='left')
window.protocol('WM_DELETE_WINDOW',request_stop)

def tick():
    try:
        while True:
            kind,value=EVENTS.get_nowait()
            if kind=='log':
                logbox.configure(state='normal');logbox.insert('end',datetime.now().strftime('%H:%M:%S')+' '+value+'\n');logbox.see('end');logbox.configure(state='disabled')
            elif kind=='sql':
                sqlbox.configure(state='normal');sqlbox.delete('1.0','end');sqlbox.insert('1.0',value);sqlbox.configure(state='disabled')
            elif kind=='counts':
                countvar.set('已完成 %d/70  |  匹配 %d  |  不一致 %d'%(value['completed_queries'],value['matched_queries'],value['mismatched_queries']))
                bar['value']=value['completed_queries']
            elif kind=='finished':
                activevar.set('任务结束：'+value+'。结果已保存，可以关闭本窗口。');stopbutton.configure(text='关闭窗口')
    except queue.Empty:pass
    if ACTIVE['query'] is not None:
        activevar.set('正在执行第 %d/70 条（ID %d），本条已运行 %.0f 秒'%(ACTIVE['query']+1,ACTIVE['query'],time.perf_counter()-ACTIVE['started']))
    window.after(500,tick)

window.after(8000,lambda:threading.Thread(target=worker,daemon=False).start())
window.after(300,lambda:window.attributes('-topmost',False))
window.lift();window.attributes('-topmost',True)
tick();window.mainloop()
