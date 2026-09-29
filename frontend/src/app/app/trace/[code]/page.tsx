"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, human } from "@/lib/format";
import type { Batch } from "@/lib/fulfilment";
import { kg } from "@/lib/planning";

type Trace = Batch & { recalled_at?: string | null; recall_reason?: string; producer_summary: { producers: number; women: number; youth: number; intakes: number };
  movements: { at: string; location: string; type: string; quantity: number; status: string; source_ref: string; reason: string }[];
  deliveries: { dispatch: string; dispatch_id: string; school: string; quantity: number; accepted_qty: number | null; rejected_qty: number | null; status: string; received_at: string | null; receiver: string | null }[] };

export default function TracePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const [t, setT] = useState<Trace | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  const [showRecall, setShowRecall] = useState(false);
  const { can } = useAuth();
  const { toast, node } = useToast();
  const load = () => get<Trace>(`/trace/${encodeURIComponent(code)}`).then(setT).catch(setErr);
  useEffect(() => { load(); }, [code]); // eslint-disable-line react-hooks/exhaustive-deps
  async function recall() {
    if (!t) return; setErr(null);
    try { const r = await post<{ schools_notified: number }>(`/batches/${t.id}/recall`, { reason }); toast(`Batch recalled. ${r.schools_notified} school(s) alerted by SMS.`); setShowRecall(false); load(); }
    catch (x) { setErr(x); }
  }
  const step = (n: number, title: string, body: React.ReactNode) => (
    <div className="card" style={{ borderLeft: "4px solid var(--green)" }}><div className="row"><span className="pill p-green">{n}</span><h3 style={{ margin: 0 }}>{title}</h3></div><div style={{ marginTop: 8 }}>{body}</div></div>);
  return (
    <>
      <PageHead crumb="Fulfil · Traceability" title={decodeURIComponent(code)} sub={t ? `${t.commodity}${t.variety ? ` · ${t.variety}` : ""} · formed at ${t.location}` : ""}>
        {t && <Pill status={t.status} />}
        {t && <a className="btn sm" href={`/app/trace/${t.code}/label`} target="_blank" rel="noreferrer">Print QR label</a>}
        {t && t.status !== "recalled" && t.status !== "open" && can("agg:approve", "rsk:approve", "rsk:edit") && <button className="btn sm danger" onClick={() => setShowRecall(!showRecall)}>Recall batch</button>}
        <Link className="btn sm" href="/app/trace">Another batch</Link></PageHead>
      <ErrorBox error={err} />
      {t?.status === "recalled" && <div className="alert bad" role="alert"><b>Recalled</b> on {fmtDateTime(t.recalled_at)}: {t.recall_reason}. Schools and stores holding this batch must not use it.</div>}
      {showRecall && <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid #B3261E" }}>
        <h3>Recall {t?.code}</h3>
        <p className="small muted">Blocks dispatch, transfer and use everywhere, alerts every school and store that holds it by SMS, and opens a high-priority exception.</p>
        <Field label="Reason (shared with schools)"><textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <button className="btn danger" disabled={reason.trim().length < 10} onClick={recall}>Confirm recall</button></div>}
      {t && <div className="stack">
        {step(1, "Farmers & intake", <>
          <p className="small">{t.producer_summary.producers} producer(s) · {t.producer_summary.intakes} intake(s) · {t.producer_summary.women} women · {t.producer_summary.youth} youth · total {kg(t.intake_qty, t.unit)}{t.supplier ? ` · aggregated by ${t.supplier}` : ""}</p>
          <div className="tablewrap"><table><thead><tr><th>Producer</th><th>Group</th><th>From</th><th className="r">Qty</th><th>Received</th></tr></thead>
            <tbody>{t.intakes?.map((i) => <tr key={i.id}><td>{i.producer_name}</td><td className="small">{i.producer_group || "—"}</td><td className="small">{i.source_location || "—"}</td>
              <td className="r num">{kg(i.quantity, i.unit)}</td><td className="small">{fmtDateTime(i.received_at)}</td></tr>)}</tbody></table></div></>)}
        {step(2, "Quality inspection", t.inspections?.length ? t.inspections.map((x) => <div key={x.id} className="small">
          <b>{human(x.result)}</b> by {x.inspector} on {fmtDateTime(x.inspected_at)} · accepted {kg(x.accepted_qty)} · rejected {kg(x.rejected_qty)} · {x.grade}
          <div className="muted">{x.checks.map((c) => `${human(c.param)} ${c.value ?? "n/a"}${c.pass === false ? " ✗" : c.pass ? " ✓" : ""}`).join(" · ")}</div>
          {x.reason && <div>Reason: {x.reason}</div>}</div>) : <p className="small muted">Not inspected yet.</p>)}
        {step(3, "Stock movements", <div className="tablewrap"><table><tbody>{t.movements.map((m, i) => <tr key={i}><td className="small">{fmtDateTime(m.at)}</td><td>{m.location}</td>
          <td>{human(m.type)}</td><td className="r num">{Number(m.quantity) > 0 ? "+" : ""}{kg(m.quantity, t.unit)}</td><td className="small muted">{m.source_ref} {m.reason}</td><td><Pill status={m.status} /></td></tr>)}
          {!t.movements.length && <tr><td className="muted">No stock movements yet.</td></tr>}</tbody></table></div>)}
        {step(4, "Delivered to schools", <div className="tablewrap"><table><thead><tr><th>School</th><th>Dispatch</th><th className="r">Sent</th><th className="r">Accepted</th><th>Received</th></tr></thead>
          <tbody>{t.deliveries.map((x, i) => <tr key={i}><td>{x.school}</td><td><Link href={`/app/deliveries?dispatch=${x.dispatch_id}`}>{x.dispatch}</Link></td><td className="r num">{kg(x.quantity, t.unit)}</td>
            <td className="r num">{x.accepted_qty != null ? kg(x.accepted_qty, t.unit) : "—"}</td><td className="small">{x.received_at ? `${fmtDate(x.received_at)} · ${x.receiver}` : <Pill status={x.status} />}</td></tr>)}
            {!t.deliveries.length && <tr><td colSpan={5} className="muted">Not dispatched yet.</td></tr>}</tbody></table></div>)}
      </div>}
      {node}
    </>
  );
}
