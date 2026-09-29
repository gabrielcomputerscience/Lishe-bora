"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, Pill, useToast } from "@/components/ui";
import { ApiError, get, put } from "@/lib/api";

type D = Record<string, string> | null;

/** Supplier's own payment details. Changes are held until county finance verifies them by phone. */
export function PaymentDetails() {
  const [d, setD] = useState<{ active: D; pending: D } | null>(null);
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ method: "mpesa", account_name: "", mpesa_phone: "", bank_name: "", branch: "", account_no: "" });
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<{ active: D; pending: D }>("/suppliers/me/payment-details").then(setD).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setFe({});
    try { setD(await put("/suppliers/me/payment-details", f)); setEdit(false); toast("Sent for verification. Finance will call your registered number."); }
    catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  const show = (x: D) => x ? `${x.method === "mpesa" ? "M-Pesa" : "Bank"} · ${x.account_name} · ${x.mpesa_phone || `${x.bank_name} ${x.account_no}`}` : "Not set";
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row"><h2>How you get paid</h2><span className="spacer" />{!edit && <button className="btn sm" onClick={() => setEdit(true)}>{d?.active ? "Change" : "Add"}</button>}</div>
      <ErrorBox error={err} />
      {d && <p>{show(d.active)} {d.active && <Pill status="verified" label="Verified" />}</p>}
      {d?.pending && <div className="alert warn small">Change waiting for verification: {show(d.pending)}. Payments continue to the verified details until finance confirms.</div>}
      {edit && <form onSubmit={save}>
        <div className="grid g2">
          <Field label="Method"><select value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}><option value="mpesa">M-Pesa</option><option value="bank">Bank account</option></select></Field>
          <Field label="Account name" error={fe.account_name}><input value={f.account_name} onChange={(e) => setF({ ...f, account_name: e.target.value })} /></Field>
          {f.method === "mpesa" ? <Field label="M-Pesa number" error={fe.mpesa_phone}><input inputMode="tel" value={f.mpesa_phone} onChange={(e) => setF({ ...f, mpesa_phone: e.target.value })} /></Field> : <>
            <Field label="Bank"><input value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} /></Field>
            <Field label="Branch"><input value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })} /></Field>
            <Field label="Account number" error={fe.account_no}><input value={f.account_no} onChange={(e) => setF({ ...f, account_no: e.target.value })} /></Field></>}
        </div>
        <p className="small muted">For your protection, new details take effect only after the county finance office confirms them with you by phone.</p>
        <div className="row"><button className="btn primary" type="submit">Submit for verification</button><button type="button" className="btn ghost" onClick={() => setEdit(false)}>Cancel</button></div>
      </form>}
      {node}
    </div>
  );
}
