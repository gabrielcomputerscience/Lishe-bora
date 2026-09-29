import { publicGet } from "@/lib/server";

export const dynamic = "force-dynamic";
type V = { code: string; commodity: string; variety: string; grade: string; status: string; recalled: boolean; recall_reason: string;
  county: string | null; aggregated_by: string | null; formed_on: string | null; expiry_date: string | null;
  inspection: { result: string; date: string } | null; producers: number; women_producers: number; schools_supplied: number };

const load = (code: string) => publicGet<V>(`/trace/${encodeURIComponent(code)}`);
const d = (s: string | null) => (s ? new Date(s).toLocaleDateString("en-KE", { day: "2-digit", month: "short", year: "numeric" }) : "—");

export default async function Verify({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const v = await load(code);
  return (
    <section className="wrap sec narrow">
      <div className="eyebrow">Batch verification</div>
      <h1>{decodeURIComponent(code).toUpperCase()}</h1>
      {!v ? <div className="alert warn">We could not find this batch. Check the code on the label, or contact the county school-feeding office.</div> : <>
        {v.recalled ? <div className="alert bad" role="alert"><b>Do not use this food.</b> This batch was recalled: {v.recall_reason}</div>
          : <div className="alert info">This batch is registered on LisheBora and {v.inspection ? `passed quality inspection (${v.inspection.result.replace(/_/g, " ")}) on ${d(v.inspection.date)}` : "is awaiting inspection"}.</div>}
        <div className="card">
          <table style={{ width: "100%" }}><tbody>
            <tr><td className="muted">Food</td><td><b>{v.commodity}</b>{v.variety ? ` · ${v.variety}` : ""} {v.grade ? `· ${v.grade}` : ""}</td></tr>
            <tr><td className="muted">Aggregated by</td><td>{v.aggregated_by ?? "—"}</td></tr>
            <tr><td className="muted">County</td><td>{v.county ?? "—"}</td></tr>
            <tr><td className="muted">Formed on</td><td>{d(v.formed_on)}</td></tr>
            <tr><td className="muted">Best before</td><td>{d(v.expiry_date)}</td></tr>
            <tr><td className="muted">Grown by</td><td>{v.producers} local producer(s){v.women_producers ? `, including ${v.women_producers} women` : ""}</td></tr>
            <tr><td className="muted">Schools supplied</td><td>{v.schools_supplied}</td></tr>
          </tbody></table>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>No personal information is shown. To report a problem with this food, use the Contact page and quote the batch code.</p>
      </>}
    </section>
  );
}
