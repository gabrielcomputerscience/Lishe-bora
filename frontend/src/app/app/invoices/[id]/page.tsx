"use client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { WorkflowPanel } from "@/components/Workflow";
import { ApiError, get, post } from "@/lib/api";
import { METHODS, type Invoice } from "@/lib/finance";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";

export default function InvoicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [inv, setInv] = useState<Invoice | null>(null);
  const [pf, setPf] = useState({ amount: "", method: "bank", transaction_ref: "", paid_on: new Date().toISOString().slice(0, 10), note: "" });
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Invoice>(`/invoices/${id}`).then((x) => { setInv(x); setPf((p) => ({ ...p, amount: String(x.balance) })); }).catch(setErr), [id]);
  useEffect(() => { load(); }, [load]);
  async function pay() {
    setErr(null); setFe({});
    try { await post(`/invoices/${id}/payments`, pf); toast("Payment recorded. The supplier has been notified."); setPf({ ...pf, transaction_ref: "", note: "" }); load(); }
    catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  if (!inv) return <><ErrorBox error={err} /><p className="muted">Loading…</p></>;
  return (
    <>
      <PageHead crumb="Finance · Invoices" title={inv.reference} sub={`${inv.supplier} · supplier invoice no. ${inv.supplier_invoice_no} · dated ${fmtDate(inv.invoice_date)}`}>
        <Pill status={inv.status} />{inv.has_document && <a className="btn sm" href={`/api/v1/invoices/${inv.id}/document`} target="_blank" rel="noreferrer">Invoice copy</a>}
        <Link className="btn sm" href="/app/invoices">All invoices</Link></PageHead>
      <ErrorBox error={err} />
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Invoice total</div><div className="v">{ksh(inv.total)}</div></div>
        <div className="card kpi leaf"><div className="l">Paid</div><div className="v">{ksh(inv.paid_amount)}</div></div>
        <div className="card kpi gold"><div className="l">Balance</div><div className="v">{ksh(inv.balance)}</div></div>
        <div className="card kpi purple"><div className="l">Days to pay</div><div className="v">{inv.days_to_pay ?? "—"}</div></div>
      </div>
      <div className="stack">
          <div className="card">
            <div className="row"><h2>Three-way match</h2><span className="spacer" />{inv.match && <Pill status={inv.match.result} />}</div>
            <p className="small muted">Order <b>{inv.po}</b> ↔ goods accepted at schools ↔ this invoice. Checked {fmtDateTime(inv.match?.checked_at)}{inv.match?.verified_by ? `, verified by ${inv.match.verified_by}` : ""}. Price tolerance {inv.match?.tolerance_pct ?? 0}%.</p>
            <div className="tablewrap"><table>
              <thead><tr><th>Item</th><th className="r">Ordered</th><th className="r">Accepted</th><th className="r">Invoiced before</th><th className="r">This invoice</th><th className="r">PO price</th><th className="r">Invoiced price</th><th /></tr></thead>
              <tbody>{inv.match?.lines.map((m) => <tr key={m.po_line_id}><td>{inv.lines?.find((l) => l.po_line_id === m.po_line_id)?.commodity ?? m.commodity_code}</td>
                <td className="r num">{kg(m.ordered_qty, m.unit)}</td><td className="r num">{kg(m.accepted_qty, m.unit)}</td><td className="r num">{kg(m.previously_invoiced, m.unit)}</td>
                <td className="r num"><b>{kg(m.invoiced_qty, m.unit)}</b></td><td className="r num">{Number(m.po_price).toLocaleString()}</td><td className="r num">{Number(m.invoiced_price).toLocaleString()}</td>
                <td>{m.result === "match" ? "✓" : <span className="small">{m.issues.join("; ")}</span>}</td></tr>)}</tbody></table></div>
            <p className="small" style={{ marginTop: 8 }}>Subtotal {ksh(inv.subtotal)} · tax {ksh(inv.tax_amount)} · <b>total {ksh(inv.total)}</b></p>
            {inv.notes && <p className="small muted">Notes: {inv.notes}</p>}
          </div>
        <div className="grid g2" style={{ alignItems: "start" }}>
          <div className="card"><h3>Payments</h3>
            <div className="tablewrap"><table><tbody>{inv.payments?.map((x) => <tr key={x.id}><td><b>{x.reference}</b></td><td className="r num">{ksh(x.amount)}</td>
              <td className="small">{METHODS[x.method] ?? x.method} · {x.transaction_ref}</td><td className="small">{fmtDate(x.paid_on)}</td></tr>)}
              {!inv.payments?.length && <tr><td className="muted">No payments yet.</td></tr>}</tbody></table></div>
            {inv.can_pay ? <div style={{ marginTop: 12 }}>
              <div className="grid g2">
                <Field label="Amount (KSh)" error={fe.amount}><input type="number" min="0" step="0.01" value={pf.amount} onChange={(e) => setPf({ ...pf, amount: e.target.value })} /></Field>
                <Field label="Method"><select value={pf.method} onChange={(e) => setPf({ ...pf, method: e.target.value })}>{Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
                <Field label="Transaction reference" error={fe.transaction_ref}><input value={pf.transaction_ref} onChange={(e) => setPf({ ...pf, transaction_ref: e.target.value })} /></Field>
                <Field label="Paid on" error={fe.paid_on}><input type="date" value={pf.paid_on} onChange={(e) => setPf({ ...pf, paid_on: e.target.value })} /></Field>
              </div>
              <Field label="Note"><input value={pf.note} onChange={(e) => setPf({ ...pf, note: e.target.value })} /></Field>
              <button className="btn primary" disabled={!pf.transaction_ref} onClick={pay}>Record payment</button>
            </div> : inv.why_not_pay && ["approved", "partially_paid"].includes(inv.status) ? <p className="small muted">{inv.why_not_pay}</p> : null}
          </div>
          <WorkflowPanel wf={inv.workflow ?? null} onDone={load} />
        </div>
      </div>
      {node}
    </>
  );
}
