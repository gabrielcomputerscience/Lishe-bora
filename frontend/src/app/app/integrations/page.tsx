"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, api, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, human } from "@/lib/format";
import { ksh } from "@/lib/planning";

type Pending = { supplier_id: string; supplier: string; registered_phone: string; current: Record<string, string> | null; requested: Record<string, string> };
type Age = { buckets: { bucket: string; amount: number; count: number }[]; invoices: { id: string; reference: string; supplier: string; balance: number; days: number; bucket: string; has_verified_details: boolean }[]; target_days: number };
type Log = { id: string; reference: string; direction: string; system: string; kind: string; status: string; records: number; total: number; has_file: boolean; created_at: string;
  summary: { unmatched?: { line: number; issue: string; transaction_ref?: string }[] } };
type Stmt = { reference: string; status: string; matched: { invoice: string; amount: string; payment: string }[]; unmatched: { line: number; issue: string; transaction_ref?: string }[];
  duplicates: { line: number }[]; errors: { line: number; issue: string }[] };
type Tab = "pay" | "reconcile" | "details" | "log";

export default function Integrations() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("pay");
  const [age, setAge] = useState<Age | null>(null);
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [system, setSystem] = useState("mpesa");
  const [pending, setPending] = useState<Pending[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [log, setLog] = useState<Log[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [stmt, setStmt] = useState<Stmt | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => {
    get<Age>("/finance/ageing").then(setAge).catch(setErr);
    get<Log[]>("/integrations/log").then(setLog).catch(() => {});
    if (can("fin:verify")) get<Pending[]>("/finance/payment-details/pending").then(setPending).catch(() => {});
  }, [can]);
  useEffect(() => { load(); const t = new URLSearchParams(window.location.search).get("tab"); if (t) setTab(t as Tab); }, [load]);
  async function makeFile() {
    setErr(null);
    try { const r = await post<{ reference: string; rows: number; total: number; download: string }>("/finance/payment-files", { invoice_ids: Object.keys(sel).filter((k) => sel[k]), system });
      toast(`${r.reference}: ${r.rows} payment(s), ${ksh(r.total)}`); window.location.assign(r.download); setSel({}); load(); }
    catch (x) { setErr(x); }
  }
  async function importStmt() {
    if (!file) return; setErr(null);
    const fd = new FormData(); fd.append("system", system); fd.append("file", file);
    try { setStmt(await api<Stmt>("/finance/statements", { method: "POST", body: fd })); load(); } catch (x) { setErr(x); }
  }
  async function verify(sid: string, approve: boolean) {
    setErr(null);
    try { await post(`/finance/payment-details/${sid}/verify`, { approve, note: notes[sid] ?? "" }); toast(approve ? "Payment details approved" : "Change rejected"); load(); }
    catch (x) { setErr(x); }
  }
  const blocked = err instanceof ApiError && err.code === "PAYMENT_FILE_BLOCKED" ? err.details : [];
  return (
    <>
      <PageHead crumb="Finance" title="Payment integrations" sub="Bulk payment files for the bank or M-Pesa, statement reconciliation, verified supplier payment details and the county financial-system export. Every file is logged.">
        {can("fin:export", "fin:approve") && <a className="btn" href="/api/v1/finance/ifmis-export.csv?status=approved,partially_paid,paid">IFMIS export (CSV)</a>}
      </PageHead>
      <div className="tabs">{([["pay", "Pay approved invoices"], ["reconcile", "Import statement"], ...(can("fin:verify") ? [["details", `Payment details (${pending.length})`]] : []), ["log", "Integration log"]] as [Tab, string][])
        .map(([k, l]) => <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}</div>
      <ErrorBox error={err} />
      {!!blocked.length && <div className="alert bad small">{blocked.map((d, i) => <div key={i}>{String(d.issue)}</div>)}</div>}

      {tab === "pay" && age && <div className="stack">
        <div className="grid g4">{age.buckets.map((b) => <div key={b.bucket} className={`card kpi ${b.bucket === "61+" ? "purple" : b.bucket === "31-60" ? "gold" : ""}`}>
          <div className="l">{b.bucket} days since approval</div><div className="v">{ksh(b.amount)}</div><div className="small muted">{b.count} invoice(s)</div></div>)}</div>
        <div className="card"><div className="row"><h2>Approved, not yet paid</h2><span className="spacer" />
          <select className="btn" value={system} onChange={(e) => setSystem(e.target.value)} aria-label="Channel"><option value="mpesa">M-Pesa B2C file</option><option value="bank">Bank EFT file</option></select>
          <button className="btn primary" disabled={!Object.values(sel).some(Boolean) || !can("fin:pay")} onClick={makeFile}>Create payment file</button></div>
          <div className="tablewrap"><table><thead><tr><th /><th>Invoice</th><th>Supplier</th><th className="r">Balance</th><th className="r">Days</th><th>Payment details</th></tr></thead>
            <tbody>{age.invoices.map((i) => <tr key={i.id}><td><input type="checkbox" aria-label={`Select ${i.reference}`} checked={!!sel[i.id]} onChange={(e) => setSel({ ...sel, [i.id]: e.target.checked })} /></td>
              <td><a href={`/app/invoices/${i.id}`}>{i.reference}</a></td><td>{i.supplier}</td><td className="r num">{ksh(i.balance)}</td>
              <td className="r num">{i.days > age.target_days ? <b style={{ color: "#B3261E" }}>{i.days}</b> : i.days}</td>
              <td>{i.has_verified_details ? <Pill status="verified" label="Verified" /> : <Pill status="rejected" label="Missing" />}</td></tr>)}
              {!age.invoices.length && <tr><td colSpan={6} className="muted">Nothing waiting for payment.</td></tr>}</tbody></table></div>
          <p className="small muted">Upload the file to the bank or M-Pesa portal. The payment is recorded when the statement is imported (next tab) or the gateway confirms it.</p></div>
      </div>}

      {tab === "reconcile" && <div className="card" style={{ maxWidth: 820 }}>
        <h2>Import a bank or M-Pesa statement</h2>
        <p className="small muted">CSV with columns <code>date, amount, transaction_ref, reference</code>. Rows that quote an invoice number (INV-…) are matched to approved invoices and recorded as payments.</p>
        <div className="grid g2">
          <Field label="Channel"><select value={system} onChange={(e) => setSystem(e.target.value)}><option value="mpesa">M-Pesa</option><option value="bank">Bank</option></select></Field>
          <Field label="Statement file (CSV)"><input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        </div>
        <button className="btn primary" disabled={!file || !can("fin:pay")} onClick={importStmt}>Import & reconcile</button>
        {stmt && <div style={{ marginTop: 14 }}>
          <div className="row"><b>{stmt.reference}</b><Pill status={stmt.status === "completed" ? "approved" : "submitted"} label={human(stmt.status)} />
            <span className="small">{stmt.matched.length} matched · {stmt.unmatched.length} to review · {stmt.duplicates.length} already recorded · {stmt.errors.length} unreadable</span></div>
          {!!stmt.matched.length && <table className="small" style={{ marginTop: 8 }}><tbody>{stmt.matched.map((m, i) => <tr key={i}><td>{m.invoice}</td><td>{ksh(Number(m.amount))}</td><td>{m.payment}</td></tr>)}</tbody></table>}
          {!!(stmt.unmatched.length + stmt.errors.length) && <div className="alert warn small" style={{ marginTop: 8 }}>{[...stmt.unmatched, ...stmt.errors].map((u, i) => <div key={i}>Line {u.line}: {u.issue}</div>)}</div>}
        </div>}
      </div>}

      {tab === "details" && <div className="stack">{pending.map((p) => <div key={p.supplier_id} className="card">
        <div className="row"><h3>{p.supplier}</h3><span className="spacer" /><span className="small muted">Registered phone {p.registered_phone || "—"}</span></div>
        <div className="grid g2 small">
          <div><b>Current</b><div>{p.current ? `${p.current.method?.toUpperCase()} · ${p.current.account_name} · ${p.current.mpesa_phone || `${p.current.bank_name} ${p.current.account_no}`}` : "None"}</div></div>
          <div><b>Requested</b> by {p.requested.submitted_by} · {fmtDateTime(p.requested.submitted_at)}
            <div>{p.requested.method?.toUpperCase()} · {p.requested.account_name} · {p.requested.mpesa_phone || `${p.requested.bank_name} ${p.requested.branch} ${p.requested.account_no}`}</div></div>
        </div>
        <div className="alert warn small" style={{ marginTop: 8 }}>Before approving, call the supplier on the registered phone number (not a number given in the request) to confirm the change.</div>
        <div className="row"><input className="btn" style={{ flex: 1, fontWeight: 400 }} aria-label={`Verification note ${p.supplier}`} placeholder="How you verified (e.g. called registered number, confirmed by chairperson)"
          value={notes[p.supplier_id] ?? ""} onChange={(e) => setNotes({ ...notes, [p.supplier_id]: e.target.value })} />
          <button className="btn primary sm" onClick={() => verify(p.supplier_id, true)}>Approve</button><button className="btn danger sm" onClick={() => verify(p.supplier_id, false)}>Reject</button></div>
      </div>)}{!pending.length && <div className="card muted">No payment-detail changes waiting.</div>}</div>}

      {tab === "log" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Reference</th><th>When</th><th>System</th><th>Type</th><th className="r">Records</th><th className="r">Amount</th><th>Status</th><th /></tr></thead>
        <tbody>{log.map((t) => <tr key={t.id}><td><b>{t.reference}</b><div className="small muted">{t.direction === "out" ? "Sent" : "Received"}</div></td><td className="small">{fmtDateTime(t.created_at)}</td>
          <td>{t.system.toUpperCase()}</td><td>{human(t.kind)}</td><td className="r num">{t.records}</td><td className="r num">{ksh(t.total)}</td>
          <td><Pill status={t.status === "completed" ? "approved" : t.status === "failed" ? "rejected" : "submitted"} label={human(t.status)} /></td>
          <td>{t.has_file && can("fin:pay") && <a className="btn sm" href={`/api/v1/integrations/${t.id}/file`}>File</a>}</td></tr>)}
          {!log.length && <tr><td colSpan={8} className="muted">No integration activity yet.</td></tr>}</tbody></table></div></div>}
      {node}
    </>
  );
}
