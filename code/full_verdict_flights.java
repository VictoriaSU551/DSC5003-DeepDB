import java.io.*;
import java.sql.*;
import java.util.*;
import edu.umich.verdict.VerdictJDBCContext;
import edu.umich.verdict.datatypes.SampleParam;
import edu.umich.verdict.datatypes.TableUniqueName;
import edu.umich.verdict.dbms.DbmsJDBC;

/** Original engine calls and raw result capture only; no replacement estimator. */
public class full_verdict_flights {
    public static void main(String[] args) throws Exception {
        VerdictJDBCContext vc=full_verdict_gate.context();
        vc.getMeta().refreshTables("public_verdict");vc.getMeta().refreshSampleInfo("public",false);
        Connection connection=((DbmsJDBC)vc.getDbms()).getDbmsConnection();
        connection.createStatement().execute("SET statement_timeout='120s'");
        if(args[0].equals("register")) {
            long n=Long.parseLong(args[1]);
            SampleParam param=new SampleParam(vc,TableUniqueName.uname("public","flights"),"uniform",.01,new ArrayList<String>());
            vc.getMeta().insertSampleInfo(param,n,1000000000L);
            connection.close();return;
        }
        String method=args[1];vc.getConf().set("verdict.error_bound.method",method);
        File output=new File(args[3]);Set<String> complete=new HashSet<String>();
        if(output.exists()) {
            BufferedReader old=new BufferedReader(new InputStreamReader(new FileInputStream(output),"UTF-8"));String line;
            while((line=old.readLine())!=null)if(line.startsWith("TIME\t"))complete.add(line.split("\t")[1]);old.close();
        }
        PrintWriter writer=new PrintWriter(new OutputStreamWriter(new FileOutputStream(output,true),"UTF-8"));
        BufferedReader input=new BufferedReader(new InputStreamReader(new FileInputStream(args[2]),"UTF-8"));String line;
        while((line=input.readLine())!=null) {
            String[] fields=line.split("\t");String qid=fields[0];if(complete.contains(qid))continue;
            String sql=new String(Base64.getDecoder().decode(fields[1]),"UTF-8");long start=System.nanoTime();
            try {
                vc.execute(sql);ResultSet rs=vc.getResultSet();int count=rs.getMetaData().getColumnCount();
                writer.print("META\t"+qid);
                for(int i=1;i<=count;i++)writer.print("\t"+full_verdict_gate.encode(rs.getMetaData().getColumnLabel(i)));
                writer.println();
                while(rs.next()) {
                    writer.print("ROW\t"+qid);for(int i=1;i<=count;i++)writer.print("\t"+full_verdict_gate.encode(rs.getObject(i)));writer.println();
                }
            } catch(Exception error) {
                error.printStackTrace(System.err);writer.println("ERROR\t"+qid+"\t"+full_verdict_gate.encode(error.getClass().getName()+": "+error.getMessage()));
            }
            writer.println("TIME\t"+qid+"\t"+(System.nanoTime()-start));writer.flush();
        }
        input.close();writer.close();connection.close();
    }
}
