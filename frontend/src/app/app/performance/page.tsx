"use client";
import { useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { pct, type Scorecard } from "@/lib/finance";
import { fmtDate, human } from "@/lib/format";

const PARTS: [keyof Scorecard["rates"], string][] = [["on_time", "On-time delivery"], ["acceptance", "Accepted at schools"], ["fill", "Order filled"],
  ["inspection", "Passed inspection"], ["complaints", "Complaint-free"]];
type County = { county_id: string; county: string; invoices: number; paid: number; avg_days_to_pay: number | null; paid_within_target_pct: number | null;
  approvals_completed: number; avg_approval_hours: number | null; approvals_overdue: number; deliveries_confirmed: number;
  avg_hours_to_confirm_delivery: number | null; complaints: number; complaints_resolved_in_sla_pct: number | null; unpaid_approved: number; payment_target_days: number };
const bandPill = (b: string | null) => (b === "Good" ? "approved" : b === "Fair" ? "submitted" : b ? "rejected" : "draft");

function Meter({ v }: { v: number | null }) {
  return <div title={v == null ? "No data yet" : `${v.toFixed(1)}%`} style={{ height: 8, background: "#EEF0E9", borderRadius: 4, overflow: "hidden", minWidth: 80 }}>
    {v != null && <div style={{ width: `${Math.max(2, v)}%`, height: "100%", background: "var(--green)", borderRadius: 4 }} />}</div>;
}

export default function Performance() {
  const [rows, setRows] = useState<Scorecard[]>([]);
  const [sel, setSel] = useState<Scorecard | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [counties, setCounties] = useState<County[]>([]);
  const { me, can } = useAuth();
  const buyerView = !!me && !me.supplier_id && can("meal:view", "cmp:view");   // county performance is for buyer-side staff
  useEffect(() => { if (buyerView) get<County[]>("/performance/counties").then(setCounties).catch(() => {}); }, [buyerView]);
  useEffect(() => { get<Scorecard[]>("/performance/suppliers").then((r) => { setRows(r); if (r.length === 1) open(r[0].supplier_id); }).catch(setErr); }, []);
  const open = (id: string) => get<Scorecard>(`/performance/suppliers/${id}`).then(setSel).catch(setErr);
  return (
    <>
      <PageHead crumb="Performance" title="Supplier performance" sub="Scorecards are calculated from deliveries, school receipts, inspections, complaints and payments recorded in the platform. The weights are provisional until the programme agrees them." />
      <ErrorBox error={err} />
      <div className="card" style={{ marginBottom: 16 }}><div className="tablewrap"><table>
        <thead><tr><th>Supplier</th><th className="r">Orders</th><th className="r">Deliveries</th>{PARTS.map(([, l]) => <th key={l}>{l}</th>)}<th className="r">Days to pay</th><th className="r">Score</th><th /></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.supplier_id}><td><b>{r.supplier}</b><div className="small muted">{human(r.supplier_type)}{r.inclusion ? ` · ${r.inclusion}-led (verified)` : ""}</div></td>
          <td className="r num">{r.orders}</td><td className="r num">{r.deliveries}</td>
          {PARTS.map(([k]) => <td key={k}><div className="small num">{pct(r.rates[k])}</div><Meter v={r.rates[k]} /></td>)}
          <td className="r num">{r.avg_days_to_pay ?? "—"}</td>
          <td className="r"><b className="num">{r.score ?? "—"}</b>{r.band && <div><Pill status={bandPill(r.band)} label={r.band} /></div>}</td>
          <td className="r"><button className="btn sm" onClick={() => open(r.supplier_id)}>Details</button></td></tr>)}
          {!rows.length && <tr><td colSpan={11} className="muted">No suppliers in your area.</td></tr>}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Weights: {rows[0] ? Object.entries(rows[0].weights).map(([k, v]) => `${human(k)} ${v}%`).join(" · ") : ""}. A score needs at least two measures with data. 85+ Good · 70–84 Fair · below 70 Needs improvement.</p>
      </div>
      {!!counties.length && <div className="card" style={{ marginBottom: 16 }}><h2>County & school performance (buyer side)</h2>
        <div className="tablewrap"><table><thead><tr><th>County</th><th className="r">Avg days to pay</th><th className="r">Paid within target</th><th className="r">Avg approval time</th>
          <th className="r">Approvals overdue</th><th className="r">Hours for schools to confirm</th><th className="r">Complaints on time</th><th className="r">Approved, unpaid</th></tr></thead>
          <tbody>{counties.map((c) => <tr key={c.county_id}><td><b>{c.county}</b><div className="small muted">{c.invoices} invoices · {c.deliveries_confirmed} deliveries</div></td>
            <td className="r num">{c.avg_days_to_pay ?? "—"}</td><td className="r num">{pct(c.paid_within_target_pct)}</td>
            <td className="r num">{c.avg_approval_hours != null ? `${c.avg_approval_hours} h` : "—"}</td><td className="r num">{c.approvals_overdue}</td>
            <td className="r num">{c.avg_hours_to_confirm_delivery ?? "—"}</td><td className="r num">{pct(c.complaints_resolved_in_sla_pct)}</td><td className="r num">{c.unpaid_approved}</td></tr>)}</tbody></table></div>
        <p className="small muted">Payment target: {counties[0].payment_target_days} days from invoice. Approval time covers every approval type (plans, events, awards, invoices, stock).</p></div>}
      {sel && <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><h2>{sel.supplier}: recent deliveries</h2><div className="tablewrap"><table><tbody>{sel.recent_deliveries?.map((d, i) => <tr key={i}>
          <td>{d.dispatch}<div className="small muted">{d.school}</div></td><td className="small">planned {fmtDate(d.planned)}<div>received {fmtDate(d.received_at)}</div></td>
          <td><Pill status={d.on_time ? "approved" : "rejected"} label={d.on_time ? "On time" : "Late"} /></td><td><Pill status={d.status} /></td></tr>)}
          {!sel.recent_deliveries?.length && <tr><td className="muted">No confirmed deliveries yet.</td></tr>}</tbody></table></div></div>
        <div className="card"><h2>Complaints</h2><div className="tablewrap"><table><tbody>{sel.recent_complaints?.map((c) => <tr key={c.reference}>
          <td><b>{c.reference}</b><div className="small">{c.subject}</div></td><td className="small">{human(c.category)}</td><td><Pill status={c.status} /></td></tr>)}
          {!sel.recent_complaints?.length && <tr><td className="muted">No complaints.</td></tr>}</tbody></table></div></div>
      </div>}
    </>
  );
}
