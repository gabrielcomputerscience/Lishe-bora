"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";

type Plan = { id: string; reference: string; title: string; county: string; term: string; status: string; estimated_value: number; demand_count: number; updated_at: string };
type Opt = { id: string; name: string };
type Preview = { demand_count: number; schools: string[]; lines: { lot: string; name: string; unit: string; quantity: number; unit_price: number | null }[] };

export default function Plans() {
  const { can } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Plan[]>([]);
  const [counties, setCounties] = useState<Opt[]>([]);
  const [terms, setTerms] = useState<Opt[]>([]);
  const [f, setF] = useState({ county_id: "", term_id: "", group_by: "cluster" });
  const [pv, setPv] = useState<Preview | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    get<Plan[]>("/plans").then(setRows).catch(setErr);
    get<Opt[]>("/public/counties").then(setCounties).catch(() => {});
    get<Opt[]>("/terms").then(setTerms).catch(() => {});
  }, []);
  const preview = async () => { setErr(null); try { setPv(await post<Preview>("/plans/preview", f)); } catch (e) { setErr(e); } };
  const create = async () => { setErr(null); try { const p = await post<{ id: string }>("/plans", f); router.push(`/app/plans/${p.id}`); } catch (e) { setErr(e); } };
  return (
    <>
      <PageHead crumb="Plan" title="Procurement plans" sub="Approved school demand consolidated into lots, checked against budget, then approved by the county." />
      <ErrorBox error={err} />
      {can("src:create") && <div className="card" style={{ marginBottom: 16 }}><h3>Consolidate approved demand</h3>
        <div className="grid g4" style={{ alignItems: "end" }}>
          <Field label="County"><select value={f.county_id} onChange={(e) => { setF({ ...f, county_id: e.target.value }); setPv(null); }}><option value="">Choose…</option>{counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="Term"><select value={f.term_id} onChange={(e) => { setF({ ...f, term_id: e.target.value }); setPv(null); }}><option value="">Choose…</option>{terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
          <Field label="Lots by"><select value={f.group_by} onChange={(e) => { setF({ ...f, group_by: e.target.value }); setPv(null); }}><option value="cluster">School cluster</option><option value="county">Whole county</option></select></Field>
          <div className="field"><button className="btn" disabled={!f.county_id || !f.term_id} onClick={preview}>Preview</button></div>
        </div>
        {pv && <><p className="small muted">{pv.demand_count} approved school plans: {pv.schools.join(", ") || "none"}</p>
          {pv.lines.length > 0 && <div className="tablewrap" style={{ margin: 0 }}><table><thead><tr><th>Lot</th><th>Commodity</th><th className="r">Quantity</th><th className="r">Est. value</th></tr></thead>
            <tbody>{pv.lines.map((l, i) => <tr key={i}><td>{l.lot}</td><td>{l.name}</td><td className="r num">{kg(l.quantity, l.unit)}</td>
              <td className="r num">{l.unit_price != null ? ksh(l.quantity * l.unit_price) : "price needed"}</td></tr>)}</tbody></table></div>}
          <div className="row" style={{ marginTop: 12 }}><span className="spacer" /><button className="btn primary" disabled={!pv.demand_count} onClick={create}>Create procurement plan</button></div></>}
      </div>}
      <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Plan</th><th>County</th><th>Term</th><th className="r">Schools</th><th className="r">Estimate</th><th>Updated</th><th>Status</th><th /></tr></thead>
        <tbody>{rows.map((p) => <tr key={p.id}><td><b>{p.reference}</b><div className="small muted">{p.title}</div></td><td>{p.county}</td><td>{p.term}</td>
          <td className="r">{p.demand_count}</td><td className="r num">{ksh(p.estimated_value)}</td><td className="small">{fmtDate(p.updated_at)}</td><td><Pill status={p.status} /></td>
          <td className="r"><Link className="btn sm primary" href={`/app/plans/${p.id}`}>Open</Link></td></tr>)}
          {!rows.length && <tr><td colSpan={8} className="muted">No plans yet.</td></tr>}</tbody></table></div></div>
    </>
  );
}
