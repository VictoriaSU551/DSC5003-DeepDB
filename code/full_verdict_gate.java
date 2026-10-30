import java.io.*;
import java.sql.*;
import java.util.*;
import edu.umich.verdict.VerdictConf;
import edu.umich.verdict.VerdictJDBCContext;
import edu.umich.verdict.datatypes.SampleParam;
import edu.umich.verdict.datatypes.TableUniqueName;
import edu.umich.verdict.dbms.DbmsJDBC;

/** Calls the unmodified original engine; contains no approximate estimator. */
public class full_verdict_gate {
    static final String[] EXPRESSIONS={
        "SELECT COUNT(*) FROM %s",
        "SELECT SUM(x) FROM %s",
        "SELECT AVG(x) FROM %s",
        "SELECT grp, COUNT(*) FROM %s GROUP BY grp",
        "SELECT grp, SUM(x) FROM %s WHERE y>3 GROUP BY grp",
        "SELECT grp, AVG(x) FROM %s WHERE x>=0 GROUP BY grp",
        "SELECT SUM(x*y) FROM %s WHERE y<10",
        "SELECT SUM(x)-SUM(y) FROM %s",
        "SELECT COUNT(x) FROM %s WHERE x>0",
        "SELECT COUNT(*) FROM %s WHERE x IS NULL",
        "SELECT SUM(x) FROM %s",
        "SELECT SUM(y) FROM %s"
    };
    static VerdictJDBCContext context() throws Exception {
        VerdictConf conf=new VerdictConf();
        conf.setDbms("postgresql");conf.setHost("localhost");conf.setPort("55432");
        conf.setDbmsSchema("deepdb_verdict");conf.setUser("postgres");
        conf.set("loglevel","debug");
        conf.set("verdict.error_bound.method","nobound");
        VerdictJDBCContext vc=VerdictJDBCContext.from(conf);
        vc.getDbms().changeDatabase("public");
        Connection c=((DbmsJDBC)vc.getDbms()).getDbmsConnection();
        Statement s=c.createStatement();s.execute("SET statement_timeout='30s'");
        s.execute("SET work_mem='16MB'");s.close();
        return vc;
    }
    static String encode(Object value) throws Exception {
        return value==null ? "N" : "V"+Base64.getEncoder().encodeToString(value.toString().getBytes("UTF-8"));
    }
    static void query(VerdictJDBCContext vc,String path,String table,PrintWriter writer) throws Exception {
        for(int i=0;i<EXPRESSIONS.length;i++) {
            try {
                vc.execute(String.format(EXPRESSIONS[i],table));
                ResultSet rs=vc.getResultSet();int columns=rs.getMetaData().getColumnCount();
                while(rs.next()) {
                    writer.print("ROW\t"+path+"\t"+i);
                    for(int j=1;j<=columns;j++)writer.print("\t"+encode(rs.getObject(j)));
                    writer.println();
                }
                writer.println("OK\t"+path+"\t"+i);writer.flush();
            } catch(Exception error) {
                error.printStackTrace(System.err);
                writer.println("ERROR\t"+path+"\t"+i+"\t"+encode(error.getClass().getName()+": "+error.getMessage()));writer.flush();
            }
        }
    }
    public static void main(String[] args) throws Exception {
        PrintWriter writer=new PrintWriter(new OutputStreamWriter(new FileOutputStream(args[0]),"UTF-8"));
        VerdictJDBCContext standard=context();
        Connection c=((DbmsJDBC)standard.getDbms()).getDbmsConnection();
        Statement s=c.createStatement();s.execute("SELECT setseed(0.314159)");
        SampleParam a=new SampleParam(standard,TableUniqueName.uname("public","v_population"),"uniform",0.2,new ArrayList<String>());
        SampleParam b=new SampleParam(standard,TableUniqueName.uname("public","v_imported"),"uniform",0.2,new ArrayList<String>());
        // The original first-session catalog cache predates metadata creation.
        // Bootstrap through its public API, then refresh before original CREATE.
        standard.getDbms().createCatalog(a.sampleTableName().getSchemaName());
        standard.getMeta().refreshDatabases();
        standard.getMetaDbms().createMetaTablesInDBMS(a.getOriginalTable(),
            standard.getMeta().getMetaSizeTableForSampleTable(a.sampleTableName()),
            standard.getMeta().getMetaNameTableForSampleTable(a.sampleTableName()));
        standard.getMeta().refreshTables(a.sampleTableName().getSchemaName());
        if(args.length<2 || !args[1].equals("reuse"))
            standard.execute("CREATE 20% UNIFORM SAMPLE OF public.v_population");
        standard.getMeta().refreshSampleInfo("public",false);
        String sample=a.sampleTableName().toString(), imported=b.sampleTableName().toString();
        ResultSet count=s.executeQuery("SELECT COUNT(*) FROM "+sample);count.next();long n=count.getLong(1);count.close();
        writer.println("SAMPLE\t"+sample+"\t"+imported+"\t"+n+"\t5000");writer.flush();
        query(standard,"standard","public.v_population",writer);
        s.execute("DROP TABLE IF EXISTS "+imported);
        s.execute("CREATE TABLE "+imported+" AS TABLE "+sample);
        standard.getMeta().insertSampleInfo(b,n,5000L);
        VerdictJDBCContext registered=context();
        registered.getMeta().refreshSampleInfo("public",false);
        query(registered,"registered","public.v_imported",writer);
        writer.close();s.close();
        ((DbmsJDBC)registered.getDbms()).getDbmsConnection().close();c.close();
    }
}
