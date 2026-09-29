"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { OfflineBar } from "@/components/OfflineBar";
import { SignaturePad } from "@/components/SignaturePad";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, api, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, human } from "@/lib/format";
import { fileUrl, type Dispatch, type Stop } from "@/lib/fulfilment";
import { newRef, submitOrQueue } from "@/lib/offline";
import { kg } from "@/lib/planning";

const CACHE = "lb_deliveries_cache_v1";
const CONDITIONS = [["good", "Good"], ["damaged", "Damaged packaging"], ["wet", "Wet / damp"], ["pests", "Pests seen"], ["short", "Short count"]];

function where(): Promise<{ lat?: number; lng?: number }> {
  return new Promise((res) => {
    if (!("geolocation" in navigator)) return res({});
    setTimeout(() => res({}), 4500);   // never block the update on a GPS fix or an unanswered permission prompt
    navigator.geolocation.getCurrentPosition((p) => res({ lat: p.coords.latitude, lng: p.coords.longitude }), () => res({}), { timeout: 4000, maximumAge: 60000 });
  });
}

function PodForm({ d, stop, onDone }: { d: Dispatch; stop: Stop; onDone: () => void }) {
  const { me } = useAuth();
  const [lines, setLines] = useState<Record<string, { accepted_qty: string; rejected_qty: string; rejection_reason: string }>>(
    Object.fromEntries(stop.lines.map((l) => [l.id, { accepted_qty: String(l.quantity), rejected_qty: "0", rejection_reason: "" }])));
  const [f, setF] = useState({ receiver_name: me?.full_name ?? "", condition: "good", remarks: "" });
  const [sig, setSig] = useState("");
  const [photos, setPhotos] = useState<string[]>([]);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  async function upload(file: File) {
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api<{ file_key: string }>("/fulfilment/uploads", { method: "POST", body: fd }); setPhotos((p) => [...p, r.file_key]); } catch (x) { setErr(x); }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setFe({});
    const body = { school_id: stop.school_id, ...f, signature: sig, photos, received_at: new Date().toISOString(), client_ref: newRef(),
                   lines: stop.lines.map((l) => ({ line_id: l.id, ...lines[l.id] })) };
    try {
      const r = await submitOrQueue(`/dispatches/${d.id}/pod`, body, `Receipt · ${d.reference} · ${stop.school}`);
      toast(r.queued ? "Receipt saved on this device; it will sync when you reconnect." : "Receipt confirmed. Thank you.");
      onDone();
    } catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  return (
    <form className="card" onSubmit={submit} style={{ borderLeft: "4px solid var(--gold)" }}>
      <h3>Confirm receipt at {stop.school}</h3>
      <p className="small muted">Count what arrived. Anything you reject goes back with the vehicle and opens a follow-up case with the county.</p>
      <div className="tablewrap"><table><thead><tr><th>Item</th><th className="r">Sent</th><th className="r">Accepted</th><th className="r">Rejected</th><th>Reason for rejection</th></tr></thead>
        <tbody>{stop.lines.map((l) => { const v = lines[l.id]; const set = (p: Partial<typeof v>) => setLines({ ...lines, [l.id]: { ...v, ...p } });
          return <tr key={l.id}><td>{l.commodity}<div className="small muted">{l.batch_code}</div></td><td className="r num">{kg(l.quantity, l.unit)}</td>
            <td className="r"><input type="number" min="0" step="0.01" aria-label={`Accepted ${l.commodity}`} className="btn" style={{ width: 100, fontWeight: 400 }} value={v.accepted_qty} onChange={(e) => set({ accepted_qty: e.target.value })} /></td>
            <td className="r"><input type="number" min="0" step="0.01" aria-label={`Rejected ${l.commodity}`} className="btn" style={{ width: 90, fontWeight: 400 }} value={v.rejected_qty} onChange={(e) => set({ rejected_qty: e.target.value })} /></td>
            <td><input aria-label={`Reason ${l.commodity}`} className="btn" style={{ fontWeight: 400, width: "100%" }} value={v.rejection_reason} onChange={(e) => set({ rejection_reason: e.target.value })} disabled={!Number(v.rejected_qty)} />
              {fe[`line.${l.id}`] && <span className="err small">{fe[`line.${l.id}`]}</span>}</td></tr>; })}</tbody></table></div>
      <div className="grid g2" style={{ marginTop: 10 }}>
        <Field label="Received by" error={fe.receiver_name}><input required value={f.receiver_name} onChange={(e) => setF({ ...f, receiver_name: e.target.value })} /></Field>
        <Field label="Condition on arrival"><select value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })}>{CONDITIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
      </div>
      <Field label="Remarks"><textarea rows={2} value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></Field>
      <Field label="Signature of receiver"><SignaturePad onChange={setSig} /></Field>
      <Field label="Photo (optional, needs connection)"><input type="file" accept="image/png,image/jpeg" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></Field>
      {!!photos.length && <div className="row">{photos.map((k) => <img key={k} src={fileUrl(k)} alt="Delivery photo" style={{ height: 60, borderRadius: 6 }} />)}</div>}
      <ErrorBox error={err} />
      <button className="btn primary" type="submit">Confirm receipt</button>
      {node}
    </form>
  );
}

export default function Deliveries() {
  const [list, setList] = useState<Dispatch[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [cached, setCached] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => {
    get<Dispatch[]>("/dispatches").then((l) => { setList(l); setCached(false); try { localStorage.setItem(CACHE, JSON.stringify(l)); } catch { /* ignore */ } })
      .catch((e) => { try { const c = localStorage.getItem(CACHE); if (c) { setList(JSON.parse(c)); setCached(true); return; } } catch { /* ignore */ } setErr(e); });
  }, []);
  useEffect(() => { load(); setSel(new URLSearchParams(window.location.search).get("dispatch")); }, [load]);
  const d = list.find((x) => x.id === sel) ?? null;
  async function milestone(status: string, school_id?: string) {
    if (!d) return; setErr(null);
    try { await post(`/dispatches/${d.id}/milestones`, { status, school_id, ...(await where()) }); toast(`Marked ${human(status).toLowerCase()}`); load(); } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Fulfil" title="Deliveries" sub="Drivers update trip progress. Schools confirm what they received (works offline and syncs later)." />
      <OfflineBar onSynced={load} />
      {cached && <div className="alert warn">Showing the last list saved on this device.</div>}
      <ErrorBox error={err} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><h2>Trips & incoming deliveries</h2>
          <div className="tablewrap"><table><tbody>{list.map((x) => <tr key={x.id} style={{ background: x.id === sel ? "#F4F7EE" : undefined }}>
            <td><b>{x.reference}</b><div className="small muted">{x.source} → {x.stops.map((s) => s.school).join(", ")}</div></td><td className="small">{fmtDate(x.planned_date)}</td>
            <td><Pill status={x.status} />{!!x.can_confirm?.length && <div><span className="pill p-amber">Confirm receipt</span></div>}</td>
            <td className="r"><button className="btn sm" onClick={() => { setSel(x.id); history.replaceState(null, "", `?dispatch=${x.id}`); }}>Open</button></td></tr>)}
            {!list.length && <tr><td className="muted">No deliveries for you yet.</td></tr>}</tbody></table></div></div>
        {d && <div className="stack">
          <div className="card">
            <div className="row"><h2>{d.reference}</h2><Pill status={d.status} /><span className="spacer" /><span className="small muted">PO {d.po}</span></div>
            <p className="small muted">{d.supplier} · from {d.source} · vehicle {d.vehicle || "—"} · driver {d.driver_name || "—"} {d.driver_phone} · planned {fmtDate(d.planned_date)}</p>
            {d.can_drive && <div className="row" style={{ margin: "8px 0" }}>
              {d.status === "dispatched" && <button className="btn primary" onClick={() => milestone("in_transit")}>Start trip (in transit)</button>}
              {d.stops.filter((s) => !s.pod).map((s) => <button key={s.school_id} className="btn" onClick={() => milestone("arrived", s.school_id)}>Arrived at {s.school}</button>)}
              <button className="btn gold" onClick={() => milestone("delivered")}>All stops delivered</button></div>}
            {d.stops.map((s) => <div key={s.school_id} style={{ borderTop: "1px solid var(--line)", padding: "10px 0" }}>
              <div className="row"><b>{s.school}</b><span className="spacer" />{s.pod ? <Pill status={s.pod.status} /> : <span className="pill p-grey">Awaiting confirmation</span>}</div>
              <div className="small">{s.lines.map((l) => <div key={l.id}>{l.commodity} · sent {kg(l.quantity, l.unit)}{l.accepted_qty != null ? ` · accepted ${kg(l.accepted_qty, l.unit)}` : ""}
                {Number(l.rejected_qty) ? ` · rejected ${kg(l.rejected_qty, l.unit)} (${l.rejection_reason})` : ""} · <Link href={`/app/trace/${l.batch_code}`}>{l.batch_code}</Link></div>)}</div>
              {s.pod && <div className="small muted">Received by {s.pod.receiver_name} · {fmtDateTime(s.pod.received_at)} · {human(s.pod.condition)}{s.pod.captured_offline ? " · captured offline" : ""}
                {s.pod.signature_key && <div><img src={fileUrl(s.pod.signature_key)} alt="Signature" style={{ height: 50, background: "#fff", border: "1px solid var(--line)", borderRadius: 4 }} /></div>}</div>}
            </div>)}
            <h3 style={{ marginTop: 10 }}>Timeline</h3>
            <div className="small">{d.milestones.map((m, i) => <div key={i} style={{ padding: "4px 0" }}><b>{human(m.status)}</b>{m.school ? ` · ${m.school}` : ""} · {m.by} · <span className="muted">{fmtDateTime(m.at)}</span>
              {m.lat != null && <span className="muted"> · {m.lat.toFixed(4)}, {m.lng?.toFixed(4)}</span>}{m.note && <span className="muted"> · {m.note}</span>}</div>)}</div>
          </div>
          {d.stops.filter((s) => d.can_confirm?.includes(s.school_id)).map((s) => <PodForm key={s.school_id} d={d} stop={s} onDone={load} />)}
        </div>}
      </div>
      {node}
    </>
  );
}
