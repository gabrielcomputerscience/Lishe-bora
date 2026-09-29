"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { OfflineBar } from "@/components/OfflineBar";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, api, get } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { fileUrl, type Batch } from "@/lib/fulfilment";
import { newRef, submitOrQueue } from "@/lib/offline";
import { kg } from "@/lib/planning";

const VISUAL = [["pests", "Live insects / pests"], ["mould", "Mould or rot"], ["foreign_matter", "Stones, dust or foreign matter"], ["bad_smell", "Unusual smell"]] as const;
const RESULTS = [["accepted", "Accept all"], ["partially_accepted", "Accept part, reject part"], ["downgraded", "Accept at a lower grade"], ["rejected", "Reject all"]] as const;

export default function Quality() {
  const [queue, setQueue] = useState<Batch[]>([]);
  const [done, setDone] = useState<Batch[]>([]);
  const [b, setB] = useState<Batch | null>(null);
  const [params, setParams] = useState<Record<string, string>>({});
  const [visual, setVisual] = useState<Record<string, boolean>>({});
  const [f, setF] = useState({ result: "accepted", accepted_qty: "", rejected_qty: "0", grade: "Grade 1", reason: "", corrective_action: "", expiry_date: "" });
  const [photos, setPhotos] = useState<string[]>([]);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => {
    get<Batch[]>("/batches?status=awaiting_inspection").then(setQueue).catch(setErr);
    get<Batch[]>("/batches?status=cleared,rejected").then((r) => setDone(r.slice(0, 15))).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  async function pick(id: string) {
    setErr(null); setFe({});
    const x = await get<Batch>(`/batches/${id}`).catch((e) => { setErr(e); return null; });
    if (!x) return;
    setB(x); setParams({}); setVisual({}); setPhotos([]);
    setF({ result: "accepted", accepted_qty: String(x.intake_qty), rejected_qty: "0", grade: "Grade 1", reason: "", corrective_action: "", expiry_date: "" });
  }
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("batch"); if (q) pick(q); }, []);
  const specs = Object.entries(b?.quality_spec ?? {}).filter(([k]) => k.startsWith("max_") || k.startsWith("min_"));
  const failed = specs.filter(([k, lim]) => { const v = params[k.slice(4)]; if (v === undefined || v === "") return false; return k.startsWith("max_") ? Number(v) > lim : Number(v) < lim; })
    .map(([k]) => k.slice(4)).concat(Object.entries(visual).filter(([, v]) => v).map(([k]) => k));
  function setResult(r: string) {
    if (!b) return;
    const t = Number(b.intake_qty);
    if (r === "accepted" || r === "downgraded") setF({ ...f, result: r, accepted_qty: String(t), rejected_qty: "0" });
    else if (r === "rejected") setF({ ...f, result: r, accepted_qty: "0", rejected_qty: String(t) });
    else setF({ ...f, result: r });
  }
  function setAccepted(v: string) { if (!b) return; setF({ ...f, accepted_qty: v, rejected_qty: String(Math.max(0, Number(b.intake_qty) - Number(v || 0))) }); }
  async function upload(file: File) {
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api<{ file_key: string }>("/fulfilment/uploads", { method: "POST", body: fd }); setPhotos((p) => [...p, r.file_key]); }
    catch (x) { setErr(x); }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!b) return; setErr(null); setFe({});
    const body = { parameters: Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)])), visual_checks: visual,
                   ...f, expiry_date: f.expiry_date || null, photos, inspected_at: new Date().toISOString(), client_ref: newRef() };
    try {
      const r = await submitOrQueue(`/batches/${b.id}/inspections`, body, `Inspection · ${b.code} · ${f.result}`);
      toast(r.queued ? "Inspection saved on this device; it will sync when you reconnect." : "Inspection recorded");
      setB(null); load();
    } catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Fulfil" title="Quality inspection" sub="Inspect batches against the commodity specification. Cleared quantities go into stock; rejections open an exception for follow-up." />
      <OfflineBar onSynced={load} />
      <ErrorBox error={err} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card">
          <h2>Waiting for inspection ({queue.length})</h2>
          <div className="tablewrap"><table><thead><tr><th>Batch</th><th>Hub</th><th className="r">Quantity</th><th /></tr></thead>
            <tbody>{queue.map((x) => <tr key={x.id}><td><b>{x.code}</b><div className="small muted">{x.commodity}{x.variety ? ` · ${x.variety}` : ""}</div></td><td className="small">{x.location}</td>
              <td className="r num">{kg(x.intake_qty, x.unit)}</td><td className="r"><button className="btn sm primary" onClick={() => pick(x.id)}>Inspect</button></td></tr>)}
              {!queue.length && <tr><td colSpan={4} className="muted">Nothing waiting.</td></tr>}</tbody></table></div>
          <h3 style={{ marginTop: 18 }}>Recently inspected</h3>
          <div className="tablewrap"><table><tbody>{done.map((x) => <tr key={x.id}><td><Link href={`/app/trace/${x.code}`}>{x.code}</Link></td><td className="small">{x.commodity}</td>
            <td className="r num small">{kg(x.accepted_qty, x.unit)} accepted</td><td><Pill status={x.status} /></td></tr>)}</tbody></table></div>
        </div>
        {b && <form className="card" onSubmit={submit}>
          <div className="row"><h2>{b.code}</h2><Pill status={b.status} /></div>
          <p className="small muted">{b.commodity} · {kg(b.intake_qty, b.unit)} from {b.intake_count} intake(s) at {b.location} · formed {fmtDateTime(b.created_at)}</p>
          {b.can_inspect === false && <div className="alert warn">{b.why_not_inspect}</div>}
          <h3>Measurements</h3>
          {!specs.length && <p className="small muted">No numeric specification for this commodity. Record visual checks below.</p>}
          <div className="grid g2">{specs.map(([k, lim]) => { const p = k.slice(4); return (
            <Field key={k} label={`${p.replace(/_/g, " ")} (${k.startsWith("max_") ? "max" : "min"} ${lim})`}>
              <input type="number" step="0.1" aria-label={p} value={params[p] ?? ""} onChange={(e) => setParams({ ...params, [p]: e.target.value })} /></Field>); })}</div>
          <h3>Visual checks</h3>
          <div className="chips">{VISUAL.map(([k, l]) => <label key={k} className="chip"><input type="checkbox" checked={!!visual[k]} onChange={(e) => setVisual({ ...visual, [k]: e.target.checked })} />{l}</label>)}</div>
          {failed.length > 0 && <div className="alert warn" style={{ marginTop: 10 }}>Failed: {failed.map((x) => x.replace(/_/g, " ")).join(", ")}. The batch cannot be accepted as it is.</div>}
          <h3 style={{ marginTop: 12 }}>Decision</h3>
          <div className="chips">{RESULTS.map(([k, l]) => <label key={k} className="chip"><input type="radio" name="res" checked={f.result === k} onChange={() => setResult(k)} disabled={k === "accepted" && failed.length > 0} />{l}</label>)}</div>
          <div className="grid g2" style={{ marginTop: 10 }}>
            <Field label="Accepted (kg)" error={fe.accepted_qty}><input type="number" step="0.01" min="0" value={f.accepted_qty} onChange={(e) => setAccepted(e.target.value)} disabled={f.result === "rejected"} /></Field>
            <Field label="Rejected (kg)"><input type="number" value={f.rejected_qty} readOnly /></Field>
            <Field label="Grade" error={fe.grade}><input value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })} /></Field>
            <Field label="Best-before / expiry (optional)"><input type="date" value={f.expiry_date} onChange={(e) => setF({ ...f, expiry_date: e.target.value })} /></Field>
          </div>
          <Field label="Reason (required unless accepting all)" error={fe.reason}><textarea rows={2} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
          <Field label="Corrective action for the supplier"><textarea rows={2} value={f.corrective_action} onChange={(e) => setF({ ...f, corrective_action: e.target.value })} /></Field>
          <Field label="Photos (optional, needs connection)"><input type="file" accept="image/png,image/jpeg" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></Field>
          {!!photos.length && <div className="row">{photos.map((k) => <a key={k} href={fileUrl(k)} target="_blank" rel="noreferrer"><img src={fileUrl(k)} alt="Inspection photo" style={{ height: 60, borderRadius: 6 }} /></a>)}</div>}
          <div className="row" style={{ marginTop: 12 }}><button className="btn primary" type="submit" disabled={b.can_inspect === false}>Record inspection</button>
            <button type="button" className="btn ghost" onClick={() => setB(null)}>Cancel</button></div>
        </form>}
      </div>
      {node}
    </>
  );
}
