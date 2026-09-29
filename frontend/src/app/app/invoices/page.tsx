"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { METHODS, type Billable, type Invoice, type PaymentRow } from "@/lib/finance";
import { fmtDate } from "@/lib/format";
import { kg, ksh } from "@/lib/planning";

const today = () => new Date().toISOString().slice(0, 10);

export default function Invoices() {
  const { can, me } = useAuth();
  const [tab, setTab] = useState<"invoices" | "payments" | "new">("invoices");
  const [rows, setRows] = useState<Invoice[]>([]);
  const [pays, setPays] = useState<PaymentRow[]>([]);
  const [bill, setBill] = useState<Billable[]>([]);
  const [filter, setFilter] = useState("");
  const [poId, setPoId] = useState("");
  const [qty, setQty] = useState<Record<string, string>>({});
  const [hdr, setHdr] = useState({ supplier_invoice_no: "", invoice_date: today(), tax_amount: "0", notes: "" });
  const [file, setFile] = useState<File | null>(null);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const creator = can("fin:create") && (!me?.supplier_id || can("fin:submit"));
  const load = useCallback(() => {
    get<Invoice[]>(`/invoices${filter ? `?status=${filter}` : ""}`).then(setRows).catch(setErr);
    get<PaymentRow[]>("/payments").then(setPays).catch(() => {});
    if (creator) get<Billable[]>("/invoices/billable").then(setBill).catch(() => {});
  }, [filter, creator]);
  useEffect(() => { load(); }, [load]);
  const po = bill.find((b) => b.id === poId);
  useEffect(() => { if (po) setQty(Object.fromEntries(po.lines.filter((l) => Number(l.billable_qty) > 0).map((l) => [l.po_line_id, String(l.billable_qty)]))); }, [po]);
  const subtotal = po ? po.lines.reduce((a, l) => a + Number(qty[l.po_line_id] || 0) * Number(l.unit_price), 0) : 0;
  async function submit() {
    setErr(null); setFe({});
    try {
      const inv = await post<Invoice>("/invoices", { po_id: poId, ...hdr, tax_amount: hdr.tax_amount || "0",
        lines: Object.entries(qty).filter(([, v]) => Number(v) > 0).map(([po_line_id, quantity]) => ({ po_line_id, quantity })) });
      if (file) { const fd = new FormData(); fd.append("file", file); await fetch(`/api/v1/invoices/${inv.id}/document`, { method: "POST", body: fd, credentials: "include" }); }
      toast(`Invoice ${inv.reference} submitted. The three-way match passed.`); setPoId(""); setHdr({ supplier_invoice_no: "", invoice_date: today(), tax_amount: "0", notes: "" }); setFile(null); setTab("invoices"); load();
    } catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  const matchIssues = err instanceof ApiError && err.code === "MATCH_FAILED" ? err.details : [];
  return (
    <>
      <PageHead crumb="Finance" title="Invoices & payments" sub="Invoices are checked automatically against the purchase order and the quantities schools accepted. Verification, approval and payment are done by three different people.">
        {tab === "invoices" && <select className="btn" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Status">
          <option value="">All invoices</option><option value="submitted,verified">Awaiting approval</option><option value="approved,partially_paid">Approved, to pay</option>
          <option value="paid">Paid</option><option value="returned,rejected">Returned / rejected</option></select>}
      </PageHead>
      <div className="tabs">
        <button className={`tab ${tab === "invoices" ? "on" : ""}`} onClick={() => setTab("invoices")}>Invoices ({rows.length})</button>
        <button className={`tab ${tab === "payments" ? "on" : ""}`} onClick={() => setTab("payments")}>Payments ({pays.length})</button>
        {creator && <button className={`tab ${tab === "new" ? "on" : ""}`} onClick={() => setTab("new")}>New invoice</button>}
      </div>
      <ErrorBox error={err} />
      {!!matchIssues.length && <div className="alert bad small">{matchIssues.map((d, i) => <div key={i}><b>{String(d.line)}</b>: {(d.issues as string[]).join("; ")}</div>)}</div>}

      {tab === "invoices" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Invoice</th><th>Supplier</th><th>Order</th><th className="r">Total</th><th className="r">Balance</th><th>Match</th><th>Status</th><th>Submitted</th><th /></tr></thead>
        <tbody>{rows.map((i) => <tr key={i.id}><td><b>{i.reference}</b><div className="small muted">No. {i.supplier_invoice_no}</div></td><td className="small">{i.supplier}</td>
          <td className="small">{i.po}</td><td className="r num">{ksh(i.total)}</td><td className="r num">{ksh(i.balance)}</td>
          <td>{i.match_result && <Pill status={i.match_result} />}</td><td><Pill status={i.status} /></td>
          <td className="small">{fmtDate(i.submitted_at)}{i.days_to_pay != null && <div className="muted">paid in {i.days_to_pay} day(s)</div>}</td>
          <td className="r"><Link className="btn sm" href={`/app/invoices/${i.id}`}>Open</Link></td></tr>)}
          {!rows.length && <tr><td colSpan={9} className="muted">No invoices yet.</td></tr>}</tbody></table></div></div>}

      {tab === "payments" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Payment</th><th>Invoice</th><th>Supplier</th><th className="r">Amount</th><th>Method</th><th>Transaction ref</th><th>Paid on</th></tr></thead>
        <tbody>{pays.map((x) => <tr key={x.id}><td><b>{x.reference}</b></td><td><Link href={`/app/invoices/${x.invoice_id}`}>{x.invoice}</Link></td><td className="small">{x.supplier}</td>
          <td className="r num">{ksh(x.amount)}</td><td className="small">{METHODS[x.method] ?? x.method}</td><td className="small">{x.transaction_ref}</td><td className="small">{fmtDate(x.paid_on)}</td></tr>)}
          {!pays.length && <tr><td colSpan={7} className="muted">No payments recorded yet.</td></tr>}</tbody></table></div></div>}

      {tab === "new" && creator && <div className="card">
        <h2>New invoice</h2>
        <p className="small muted">You can invoice only what schools have accepted, at the contract price. Rejected goods are not billable.</p>
        <div className="grid g3">
          <Field label="Purchase order"><select value={poId} onChange={(e) => setPoId(e.target.value)}><option value="">Choose…</option>
            {bill.map((b) => <option key={b.id} value={b.id} disabled={Number(b.billable_value) <= 0}>{b.reference} · {b.supplier} · billable {ksh(b.billable_value)}</option>)}</select></Field>
          <Field label="Your invoice number" error={fe.supplier_invoice_no}><input value={hdr.supplier_invoice_no} onChange={(e) => setHdr({ ...hdr, supplier_invoice_no: e.target.value })} /></Field>
          <Field label="Invoice date" error={fe.invoice_date}><input type="date" max={today()} value={hdr.invoice_date} onChange={(e) => setHdr({ ...hdr, invoice_date: e.target.value })} /></Field>
        </div>
        {po && <div className="tablewrap"><table>
          <thead><tr><th>Item</th><th className="r">Ordered</th><th className="r">Accepted by schools</th><th className="r">Already invoiced</th><th className="r">Unit price</th><th className="r">Invoice qty</th><th className="r">Amount</th></tr></thead>
          <tbody>{po.lines.map((l) => <tr key={l.po_line_id}><td>{l.commodity}{Number(l.rejected_qty) > 0 && <div className="small muted">{kg(l.rejected_qty, l.unit)} rejected</div>}</td>
            <td className="r num">{kg(l.ordered_qty, l.unit)}</td><td className="r num">{kg(l.accepted_qty, l.unit)}</td><td className="r num">{kg(l.invoiced_qty, l.unit)}</td>
            <td className="r num">{Number(l.unit_price).toLocaleString()}</td>
            <td className="r"><input type="number" min="0" max={l.billable_qty} step="0.01" aria-label={`Invoice qty ${l.commodity}`} className="btn" style={{ width: 110, fontWeight: 400 }}
              value={qty[l.po_line_id] ?? ""} disabled={Number(l.billable_qty) <= 0} onChange={(e) => setQty({ ...qty, [l.po_line_id]: e.target.value })} /></td>
            <td className="r num">{ksh(Number(qty[l.po_line_id] || 0) * Number(l.unit_price))}</td></tr>)}</tbody></table></div>}
        {po && <div className="grid g3" style={{ marginTop: 10 }}>
          <Field label="Tax (KSh, if any)" hint="Many food items are VAT-exempt"><input type="number" min="0" value={hdr.tax_amount} onChange={(e) => setHdr({ ...hdr, tax_amount: e.target.value })} /></Field>
          <Field label="Invoice copy (PDF or photo, optional)"><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          <Field label="Notes"><input value={hdr.notes} onChange={(e) => setHdr({ ...hdr, notes: e.target.value })} /></Field>
        </div>}
        {po && <p>Total <b>{ksh(subtotal + Number(hdr.tax_amount || 0))}</b></p>}
        <button className="btn primary" disabled={!po || !hdr.supplier_invoice_no || subtotal <= 0} onClick={submit}>Submit invoice</button>
      </div>}
      {node}
    </>
  );
}
