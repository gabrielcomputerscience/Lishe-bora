"use client";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { WorkflowPanel, type WF } from "@/components/Workflow";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { kg, ksh } from "@/lib/planning";

type Line = { id: string; lot: string; name: string; unit: string; quantity: number; unit_price: number | null; estimated_value: number | null; schools: { name: string; qty: string }[]; delivery_window: string };
type Plan = { id: string; reference: string; title: string; county: string; county_id: string; term: string; status: string; method: string; notes: string;
  budget_line_id: string | null; estimated_value: number; unpriced_lines: number; demand_count: number; lines: Line[]; workflow: WF | null; history?: WF["history"];
  budget?: { line: string; approved: number; committed: number; available: number; requested: number; sufficient: boolean; shortfall: number };
  exception?: { id: string; status: string; shortfall: number; justification: string; decision_note: string } | null };
type BL = { id: string; name: string; org: string; available: number };

export default function PlanDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [p, setP] = useState<Plan | null>(null);
  const [lines, setLines] = useState<BL[]>([]);
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [bl, setBl] = useState("");
  const [method, setMethod] = useState("rfq");
  const [just, setJust] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const hydrate = (x: Plan) => { setP(x); setBl(x.budget_line_id ?? ""); setMethod(x.method); setPrices(Object.fromEntries(x.lines.map((l) => [l.id, l.unit_price == null ? "" : String(l.unit_price)]))); };
  const load = useCallback(() => get<Plan>(`/plans/${id}`).then(hydrate).catch(setErr), [id]);
  useEffect(() => { load(); get<BL[]>("/budget-lines").then(setLines).catch(() => {}); }, [load]);
  if (!p) return <ErrorBox error={err} />;
  const editable = can("src:edit") && ["draft", "returned"].includes(p.status);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); await load(); } catch (e) { setErr(e); } };
  const save = () => put<Plan>(`/plans/${id}`, { budget_line_id: bl || null, method,
    lines: p.lines.map((l) => ({ id: l.id, unit_price: prices[l.id] === "" ? null : Number(prices[l.id]), delivery_window: l.delivery_window })) });

  return (
    <>
      <PageHead crumb="Plan › Procurement plans" title={p.reference} sub={`${p.title} · ${p.demand_count} schools`}><Pill status={p.status} /></PageHead>
      <ErrorBox error={err} />
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Estimated value</div><div className="v num">{ksh(p.estimated_value)}</div></div>
        <div className="card kpi gold"><div className="l">Lots / lines</div><div className="v">{new Set(p.lines.map((l) => l.lot)).size} / {p.lines.length}</div></div>
        <div className={`card kpi ${p.budget?.sufficient === false ? "amber" : "leaf"}`}><div className="l">Budget available</div><div className="v num">{p.budget ? ksh(p.budget.available) : "—"}</div></div>
        <div className="card kpi purple"><div className="l">Unpriced lines</div><div className="v">{p.unpriced_lines}</div></div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr", alignItems: "start" }}>
        <div className="card"><h3>Lots</h3><div className="tablewrap"><table>
          <thead><tr><th>Lot</th><th>Commodity</th><th className="r">Quantity</th><th className="r">Unit price (KSh)</th><th className="r">Estimate</th></tr></thead>
          <tbody>{p.lines.map((l) => <Fragment key={l.id}><tr onClick={() => setOpen(open === l.id ? null : l.id)} style={{ cursor: "pointer" }}>
            <td className="small">{l.lot}</td><td><b>{l.name}</b></td><td className="r num">{kg(l.quantity, l.unit)}</td>
            <td className="r" onClick={(e) => e.stopPropagation()}>{editable ? <input aria-label={`Price ${l.name}`} type="number" min={0} className="btn" style={{ width: 100, fontWeight: 400, textAlign: "right" }}
              value={prices[l.id] ?? ""} onChange={(e) => setPrices({ ...prices, [l.id]: e.target.value })} /> : l.unit_price ?? "—"}</td>
            <td className="r num">{ksh(l.estimated_value)}</td></tr>
            {open === l.id && <tr><td colSpan={5} className="small muted">{l.schools.map((s) => `${s.name}: ${Number(s.qty).toLocaleString()} ${l.unit}`).join(" · ")}</td></tr>}</Fragment>)}</tbody></table></div>
          <p className="small muted">Click a line to see which schools it serves. Prices are estimates for budgeting; actual prices come from bids.</p></div>
        <div className="stack">
          <div className="card"><h3>Budget</h3>
            {editable ? <>
              <Field label="Funding budget line"><select value={bl} onChange={(e) => setBl(e.target.value)}><option value="">Choose…</option>
                {lines.map((l) => <option key={l.id} value={l.id}>{l.name} · {ksh(l.available)} available</option>)}</select></Field>
              <Field label="Procurement method"><select value={method} onChange={(e) => setMethod(e.target.value)}><option value="rfq">RFQ</option><option value="competitive">Competitive bid</option><option value="framework">Framework</option><option value="call_off">Call-off</option></select></Field>
              <button className="btn" onClick={() => run(save, "Plan saved")}>Save</button></> : p.budget && <p className="small">{p.budget.line}</p>}
            {p.budget && <div className={`alert ${p.budget.sufficient ? "info" : "bad"}`} style={{ marginTop: 12 }}>
              Approved {ksh(p.budget.approved)} · committed {ksh(p.budget.committed)} · <b>available {ksh(p.budget.available)}</b>
              {!p.budget.sufficient && <><br /><b>Shortfall {ksh(p.budget.shortfall)}.</b> Reduce the plan or request a budget exception.</>}</div>}
            {p.exception && <div className={`alert ${p.exception.status === "approved" ? "info" : p.exception.status === "rejected" ? "bad" : "warn"}`}>
              Budget exception <b>{p.exception.status}</b> (shortfall {ksh(p.exception.shortfall)}){p.exception.decision_note ? ` — “${p.exception.decision_note}”` : ""}</div>}
            {p.budget && !p.budget.sufficient && can("bud:submit") && (!p.exception || p.exception.status === "rejected") && <>
              <Field label="Justification for exception" hint="At least 20 characters. Recorded in the audit trail."><textarea rows={3} value={just} onChange={(e) => setJust(e.target.value)} /></Field>
              <button className="btn gold" disabled={just.length < 20} onClick={() => run(() => post("/budget-exceptions", { plan_id: p.id, justification: just }), "Exception requested")}>Request budget exception</button></>}
            {editable && can("src:submit") && <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" onClick={() => run(async () => { await save(); await post(`/plans/${id}/submit`); }, "Submitted for approval")}>Submit for approval</button></div>}
          </div>
          <WorkflowPanel wf={p.workflow} history={p.history} onDone={load} />
        </div>
      </div>
      {node}
    </>
  );
}
