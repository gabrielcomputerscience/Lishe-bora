"use client";
import { useEffect, useState } from "react";
import { ErrorBox, Pill } from "@/components/ui";
import { api, get } from "@/lib/api";
import { fmtBytes, fmtDate } from "@/lib/format";
import type { Supplier } from "@/lib/types";

type DocType = { key: string; label: string; required: boolean };

export function SupplierDocs({ supplier, canUpload, canReview, onChange }:
  { supplier: Supplier; canUpload: boolean; canReview: boolean; onChange: () => void }) {
  const [types, setTypes] = useState<DocType[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { get<DocType[]>("/suppliers/doc-types").then(setTypes).catch(() => {}); }, []);

  const latest = (t: string) => supplier.documents.filter((d) => d.doc_type === t).sort((a, b) => b.version - a.version)[0];
  async function upload(t: string, file: File, expires?: string) {
    setErr(null); setBusy(t);
    const fd = new FormData(); fd.append("doc_type", t); fd.append("file", file); if (expires) fd.append("expires_on", expires);
    try { await api(`/suppliers/${supplier.id}/documents`, { method: "POST", body: fd }); onChange(); }
    catch (e) { setErr(e); } finally { setBusy(null); }
  }
  async function review(id: string, status: "verified" | "rejected") {
    const note = status === "rejected" ? prompt("Reason for rejection (shown to the supplier)") ?? "" : "";
    try { await api(`/suppliers/${supplier.id}/documents/${id}/review`, { method: "POST", body: { status, note } }); onChange(); }
    catch (e) { setErr(e); }
  }
  return (
    <div className="card">
      <h2>Documents</h2>
      <p className="small muted" style={{ marginTop: 0 }}>PDF, JPG or PNG, up to 10 MB. Phone photos are fine. New uploads create a new version.</p>
      <ErrorBox error={err} />
      <div className="tablewrap"><table>
        <thead><tr><th>Document</th><th>File</th><th>Expires</th><th>Status</th><th /></tr></thead>
        <tbody>{types.map((t) => {
          const d = latest(t.key);
          return (
            <tr key={t.key}>
              <td><b>{t.label}</b> {t.required && <span className="pill p-gold">Required</span>}</td>
              <td className="small">{d ? <a href={`/api/v1/suppliers/${supplier.id}/documents/${d.id}/file`} target="_blank" rel="noreferrer">{d.file_name}</a> : "—"}
                {d && <div className="muted">v{d.version} · {fmtBytes(d.size_bytes)} · {fmtDate(d.created_at)}</div>}
                {d?.review_note && <div style={{ color: "var(--danger)" }}>{d.review_note}</div>}</td>
              <td className="small">{d?.expires_on ? fmtDate(d.expires_on) : "—"}</td>
              <td>{d ? <Pill status={d.status} /> : <span className="pill p-grey">Missing</span>}</td>
              <td className="r"><div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                {canReview && d && d.status === "uploaded" && <>
                  <button className="btn sm primary" onClick={() => review(d.id, "verified")}>Verify</button>
                  <button className="btn sm danger" onClick={() => review(d.id, "rejected")}>Reject</button></>}
                {canUpload && <label className="btn sm">{busy === t.key ? "Uploading…" : d ? "Replace" : "Upload"}
                  <input type="file" accept="application/pdf,image/jpeg,image/png" hidden onChange={(e) => {
                    const file = e.target.files?.[0]; if (!file) return;
                    const exp = ["food_safety", "licence", "tax_compliance"].includes(t.key) ? prompt("Expiry date (YYYY-MM-DD), leave blank if none") ?? "" : "";
                    upload(t.key, file, exp || undefined); e.target.value = "";
                  }} /></label>}
              </div></td>
            </tr>);
        })}</tbody></table></div>
    </div>
  );
}
