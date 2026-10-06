"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { human } from "@/lib/format";

type Flag = { rule: string; severity: string; entity: string; entity_id: string; entity_ref: string; title: string; detail: string };
type Dash = { flags: Flag[]; by_rule: Record<string, Record<string, number>>; suppliers: { supplier_id: string; supplier: string | null; score: number; flags: number; high: number }[];
  rules: Record<string, Record<string, number | string>>; counts: Record<string, number> };
const LINK: Record<string, (f: Flag) => string> = { supplier: (f) => `/app/suppliers/${f.entity_id}`, batch: (f) => `/app/trace/${f.entity_ref}`,
  procurement_event: (f) => `/app/sourcing/${f.entity_id}`, contract: () => "/app/contracts" };

export default function Risk() {
  const { can } = useAuth();
  // only link to records this person may open (e.g. warehouse staff see risk flags but not the supplier registry)
  const allowed: Record<string, boolean> = { supplier: can("sup:view"), batch: can("agg:view", "inv:view"), procurement_event: can("src:view"),
                                             contract: can("con:view") };
  const linkFor = (f: Flag) => (LINK[f.entity] && allowed[f.entity] ? LINK[f.entity](f) : null);
  const [d, setD] = useState<Dash | null>(null);
  const [rules, setRules] = useState<Record<string, Record<string, string>>>({});
  const [edit, setEdit] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Dash>("/risk/dashboard").then((x) => {
    setD(x); setRules(Object.fromEntries(Object.entries(x.rules).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).map(([a, b]) => [a, String(b)]))])));
  }).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  async function scan() { setErr(null); try { const r = await post<{ flags: number; new_cases: number }>("/risk/scan"); toast(`${r.flags} flags · ${r.new_cases} new exception case(s) opened`); load(); } catch (x) { setErr(x); } }
  async function saveRules() {
    setErr(null);
    const body = Object.fromEntries(Object.entries(rules).map(([k, v]) => [k, Object.fromEntries(Object.entries(v).map(([a, b]) => [a, isNaN(Number(b)) ? b : Number(b)]))]));
    try { await put("/risk/rules", body); toast("Thresholds saved"); setEdit(false); load(); } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Oversight" title="Risk dashboard" sub="Rule-based flags computed from deliveries, inspections, prices, awards, complaints and invoices. Flags are prompts to look closer, not findings.">
        {can("rsk:create", "rsk:edit") && <button className="btn primary" onClick={scan}>Run scan & open cases</button>}
        {can("rsk:edit") && <button className="btn" onClick={() => setEdit(!edit)}>{edit ? "Close thresholds" : "Thresholds"}</button>}
      </PageHead>
      <ErrorBox error={err} />
      {d && <div className="grid g3" style={{ marginBottom: 16 }}>
        <div className="card kpi purple"><div className="l">High</div><div className="v">{d.counts.high}</div></div>
        <div className="card kpi gold"><div className="l">Medium</div><div className="v">{d.counts.medium}</div></div>
        <div className="card kpi leaf"><div className="l">Low</div><div className="v">{d.counts.low}</div></div>
      </div>}
      {edit && <div className="card" style={{ marginBottom: 16 }}><h2>Thresholds</h2>
        <div className="grid g3">{Object.entries(rules).map(([k, v]) => <div key={k}><b className="small">{human(k)}</b>
          {Object.entries(v).map(([a, b]) => <label key={a} className="small row" style={{ marginTop: 4 }}>{human(a)}
            <input className="btn" style={{ width: 90, fontWeight: 400 }} aria-label={`${k} ${a}`} value={b} onChange={(e) => setRules({ ...rules, [k]: { ...v, [a]: e.target.value } })} /></label>)}</div>)}</div>
        <button className="btn primary" style={{ marginTop: 12 }} onClick={saveRules}>Save thresholds</button></div>}
      {d && <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><h2>Flags ({d.flags.length})</h2><div className="tablewrap"><table><tbody>
          {[...d.flags].sort((a, b) => ["high", "medium", "low"].indexOf(a.severity) - ["high", "medium", "low"].indexOf(b.severity)).map((f, i) => <tr key={i}>
            <td><Pill status={f.severity} label={human(f.severity)} /></td>
            <td><b>{f.title}</b><div className="small muted">{human(f.rule)} · {linkFor(f) ? <Link href={linkFor(f)!}>{f.entity_ref}</Link> : f.entity_ref}</div>
              {f.detail && <div className="small">{f.detail}</div>}</td></tr>)}
          {!d.flags.length && <tr><td className="muted">No flags. Everything within thresholds.</td></tr>}</tbody></table></div></div>
        <div className="card"><h2>Suppliers by risk</h2><div className="tablewrap"><table><thead><tr><th>Supplier</th><th className="r">Flags</th><th className="r">High</th><th className="r">Score</th></tr></thead>
          <tbody>{d.suppliers.map((s) => <tr key={s.supplier_id}><td>{allowed.supplier ? <Link href={`/app/suppliers/${s.supplier_id}`}>{s.supplier ?? "Supplier"}</Link> : (s.supplier ?? "Supplier")}</td>
            <td className="r num">{s.flags}</td><td className="r num">{s.high}</td><td className="r num"><b>{s.score}</b></td></tr>)}
            {!d.suppliers.length && <tr><td colSpan={4} className="muted">No supplier flags.</td></tr>}</tbody></table></div>
          <p className="small muted">Score = 3 per high, 2 per medium, 1 per low flag.</p></div>
      </div>}
      {node}
    </>
  );
}
