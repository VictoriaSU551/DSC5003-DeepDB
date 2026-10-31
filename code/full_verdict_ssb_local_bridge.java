import java.io.*;
import java.nio.file.Files;
import java.sql.*;
import java.util.*;
import edu.umich.verdict.VerdictConf;
import edu.umich.verdict.VerdictJDBCContext;
import edu.umich.verdict.datatypes.SampleParam;
import edu.umich.verdict.datatypes.TableUniqueName;
import edu.umich.verdict.dbms.DbmsJDBC;

/** LOCAL I/O only; original pinned Verdict JAR computes every native query. */
public class full_verdict_ssb_local_bridge {
    static final String DATABASE="deepdb_verdict_ssb_local500";
    static final long SAMPLE_ROWS=9996946L, POPULATION_ROWS=3000028242L;
    static VerdictJDBCContext context() throws Exception {
        Locale.setDefault(Locale.US);
        VerdictConf conf=new VerdictConf();
        conf.setDbms("postgresql");conf.setHost("127.0.0.1");conf.setPort("55432");
        conf.setDbmsSchema(DATABASE);conf.setUser("postgres");
        conf.set("loglevel","debug");conf.set("verdict.error_bound.method","nobound");
        conf.set("verdict.error_bound.confidence_internal_probability","95%");
        VerdictJDBCContext vc=VerdictJDBCContext.from(conf);
        vc.getDbms().changeDatabase("public");
        Connection c=((DbmsJDBC)vc.getDbms()).getDbmsConnection();Statement s=c.createStatement();
        s.execute("SET application_name='verdict_local_ssb_original_bridge'");
        s.execute("SET statement_timeout='600s'");s.execute("SET lock_timeout='10s'");
        s.execute("SET work_mem='16MB'");s.execute("SET temp_file_limit='1GB'");
        s.execute("SET extra_float_digits=3");s.execute("SET timezone='UTC'");s.close();return vc;
    }
    static String encode(Object value) throws Exception {
        return value==null?"N":"V"+Base64.getEncoder().encodeToString(value.toString().getBytes("UTF-8"));
    }
    public static void main(String[] args) throws Exception {
        if(args.length<1)throw new IllegalArgumentException("register/query required");
        boolean registration=args[0].equals("register");
        if(!registration&&!args[0].equals("query"))throw new IllegalArgumentException("Unknown operation");
        if((registration&&args.length!=4)||(!registration&&args.length!=5))throw new IllegalArgumentException("Wrong argument count");
        File result=new File(args[registration?3:4]);
        if(!result.createNewFile())throw new IOException("Refuse existing result path");
        FileOutputStream fs=new FileOutputStream(result);PrintWriter out=new PrintWriter(new OutputStreamWriter(fs,"UTF-8"));
        VerdictJDBCContext vc=null;
        try {
            vc=context();Connection c=((DbmsJDBC)vc.getDbms()).getDbmsConnection();
            if(registration) {
                long n=Long.parseLong(args[1]),N=Long.parseLong(args[2]);
                if(n!=SAMPLE_ROWS||N!=POPULATION_ROWS)throw new IllegalArgumentException("Exact LOCAL population guard");
                SampleParam param=new SampleParam(vc,TableUniqueName.uname("public","lineorder"),"uniform",n/(double)N,new ArrayList<String>());
                if(!param.sampleTableName().toString().equals("public_verdict.vs_lineorder_uf_0_0033"))throw new IllegalArgumentException("Original sample-name derivation differs");
                vc.getDbms().createCatalog(param.sampleTableName().getSchemaName());vc.getMeta().refreshDatabases();
                vc.getMetaDbms().createMetaTablesInDBMS(param.getOriginalTable(),vc.getMeta().getMetaSizeTableForSampleTable(param.sampleTableName()),vc.getMeta().getMetaNameTableForSampleTable(param.sampleTableName()));
                vc.getMeta().refreshTables(param.sampleTableName().getSchemaName());vc.getMeta().insertSampleInfo(param,n,N);
                vc.getMeta().refreshSampleInfo("public",false);
                out.println("REGISTER\t"+param.sampleTableName().toString()+"\t"+n+"\t"+N+"\t"+Double.toString(n/(double)N));
            } else {
                String mode=args[1],qid=args[2];
                if(!mode.equals("nobound")&&!mode.equals("subsampling"))throw new IllegalArgumentException("Unknown native mode");
                if(!qid.matches("Q[1-4]\\.[1-4]\\.(raw|sum_revenue|sum_supplycost)\\.(nobound|subsampling)"))throw new IllegalArgumentException("Invalid call identity");
                String sql=new String(Files.readAllBytes(new File(args[3]).toPath()),"UTF-8");
                if(!sql.trim().toLowerCase(Locale.US).startsWith("select "))throw new IllegalArgumentException("SELECT only");
                vc.getMeta().refreshTables("public_verdict");vc.getMeta().refreshSampleInfo("public",false);
                c.setReadOnly(true);vc.getConf().set("verdict.error_bound.method",mode);
                long started=System.nanoTime();
                try {
                    vc.execute(sql);ResultSet rs=vc.getResultSet();int width=rs.getMetaData().getColumnCount();
                    out.print("META\t"+qid);for(int i=1;i<=width;i++)out.print("\t"+encode(rs.getMetaData().getColumnLabel(i)));out.println();
                    while(rs.next()){out.print("ROW\t"+qid);for(int i=1;i<=width;i++)out.print("\t"+encode(rs.getObject(i)));out.println();}
                    rs.close();
                } catch(Exception error) {
                    error.printStackTrace(System.err);out.println("ERROR\t"+qid+"\t"+encode(error.getClass().getName()+": "+error.getMessage()));
                }
                out.println("TIME\t"+qid+"\t"+(System.nanoTime()-started));
            }
            out.flush();if(out.checkError())throw new IOException("Result write failed");fs.getFD().sync();
        } finally {out.close();if(vc!=null)((DbmsJDBC)vc.getDbms()).getDbmsConnection().close();}
    }
}
