"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { OfflineBar } from "@/components/OfflineBar";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import type { Batch, Loc } from "@/lib/fulfilment";
import { newRef, submitOrQueue } from "@/lib/offline";
import { kg } from "@/lib/planning";

type Comm = { code: string; name: string; unit: string };
const blank = { producer_name: "", producer_phone: "", producer_group: "", producer_gender: "", producer_youth: "", commodity_code: "MAIZE-FLOUR", variety: "", quantity: "", source_location: "" };

export default function Aggregation() {
  const { can } = useAuth();
  const [hubs, setHubs] = useState<Loc[]>([]);
  const [hub, setHub] = useState("");
  const [comms, setComms] = useState<Comm[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [open, setOpen] = useState<Batch | null>(null);
  const [f, setF] = useState(blank);
  const [fe, setFe] = useState<Record<string, string>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<Batch[]>(`/batches${hub ? `?location_id=${hub}` : ""}`).then(setBatches).catch(setErr); }, [hub]);
  useEffect(() => {
    get<Loc[]>("/fulfilment/locations?type=aggregation_centre").then((l) => { setHubs(l); if (l[0]) setHub((h) => h || l[0].id); }).catch(setErr);
    get<Comm[]>("/commodities").then(setComms).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  const openBatch = (id: string) => get<Batch>(`/batches/${id}`).then(setOpen).catch(setErr);
  useEffect(() => { const q = new URLSearchParams(window.location.search).get("batch"); if (q) openBatch(q); }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setFe({});
    const body = { ...f, location_id: hub, quantity: f.quantity, producer_youth: f.producer_youth === "" ? null : f.producer_youth === "yes",
                   received_at: new Date().toISOString(), client_ref: newRef() };
    try {
      const r = await submitOrQueue<{ batch: Batch; reference: string }>("/intakes", body, `Intake · ${f.producer_name} · ${f.quantity} kg ${f.commodity_code}`);
      if (r.queued) toast("Saved on this device. It will sync when you are back online.");
      else { toast(`Intake ${r.data!.reference} recorded in ${r.data!.batch.code}`); openBatch(r.data!.batch.id); }
      setF({ ...blank, commodity_code: f.commodity_code, variety: f.variety, source_location: f.source_location }); load();
    } catch (x) { if (x instanceof ApiError) setFe(x.fieldErrors()); setErr(x); }
  }
  async function requestInspection(b: Batch) {
    setErr(null);
    try { setOpen(await post<Batch>(`/batches/${b.id}/request-inspection`)); toast("Sent to the quality inspector"); load(); } catch (x) { setErr(x); }
  }
  const set = (k: keyof typeof blank) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      <PageHead crumb="Fulfil" title="Aggregation & intake" sub="Record produce received from farmers at the hub. Intakes of the same commodity join one open batch until it is sent for inspection.">
        {hubs.length > 1 && <select className="btn" value={hub} onChange={(e) => setHub(e.target.value)} aria-label="Hub">{hubs.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</select>}
      </PageHead>
      <OfflineBar onSynced={load} />
      <ErrorBox error={err} />
      {!hubs.length && <div className="card muted">No aggregation hub is linked to your account yet.</div>}
      <div className="grid g2" style={{ alignItems: "start" }}>
        {can("agg:create") && hub && <form className="card" onSubmit={save}>
          <h2>New intake</h2>
          <div className="grid g2">
            <Field label="Farmer / producer name" error={fe.producer_name}><input required value={f.producer_name} onChange={set("producer_name")} /></Field>
            <Field label="Phone (optional)"><input value={f.producer_phone} onChange={set("producer_phone")} inputMode="tel" /></Field>
            <Field label="Group / cooperative (optional)"><input value={f.producer_group} onChange={set("producer_group")} /></Field>
            <Field label="Source village / ward"><input value={f.source_location} onChange={set("source_location")} /></Field>
            <Field label="Gender (optional)" hint="For inclusion reporting only"><select value={f.producer_gender} onChange={set("producer_gender")}>
              <option value="">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></Field>
            <Field label="Youth (18–35)?"><select value={f.producer_youth} onChange={set("producer_youth")}><option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option></select></Field>
            <Field label="Commodity" error={fe.commodity_code}><select value={f.commodity_code} onChange={set("commodity_code")}>{comms.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></Field>
            <Field label="Variety (optional)"><input value={f.variety} onChange={set("variety")} /></Field>
            <Field label="Quantity (kg)" error={fe.quantity}><input required type="number" min="0.1" step="0.1" value={f.quantity} onChange={set("quantity")} /></Field>
          </div>
          <button className="btn primary" type="submit">Record intake</button>
        </form>}
        <div className="card">
          <h2>Batches</h2>
          <div className="tablewrap"><table><thead><tr><th>Batch</th><th>Commodity</th><th className="r">Intake</th><th className="r">On hand</th><th>Status</th><th /></tr></thead>
            <tbody>{batches.map((b) => <tr key={b.id}><td><b>{b.code}</b><div className="small muted">{b.intake_count} intake(s) · {b.location}</div></td>
              <td>{b.commodity}{b.variety ? ` · ${b.variety}` : ""}</td><td className="r num">{kg(b.intake_qty, b.unit)}</td><td className="r num">{kg(b.on_hand, b.unit)}</td>
              <td><Pill status={b.status} /></td><td className="r"><button className="btn sm" onClick={() => openBatch(b.id)}>Open</button></td></tr>)}
              {!batches.length && <tr><td colSpan={6} className="muted">No batches yet.</td></tr>}</tbody></table></div>
        </div>
      </div>
      {open && <div className="card" style={{ marginTop: 16 }}>
        <div className="row"><h2>{open.code}</h2><Pill status={open.status} /><span className="small muted">{open.commodity} · {open.location}{open.supplier ? ` · ${open.supplier}` : ""}</span>
          <span className="spacer" /><Link className="btn sm" href={`/app/trace/${open.code}`}>Traceability</Link>
          {open.status === "open" && can("agg:submit") && <button className="btn primary sm" onClick={() => requestInspection(open)}>Close batch & request inspection</button>}
          <button className="btn sm ghost" onClick={() => setOpen(null)}>Close</button></div>
        <p className="small muted">Intake {kg(open.intake_qty, open.unit)} · accepted {kg(open.accepted_qty, open.unit)} · rejected {kg(open.rejected_qty, open.unit)}{open.grade ? ` · ${open.grade}` : ""}</p>
        <div className="tablewrap"><table><thead><tr><th>Ref</th><th>Producer</th><th>Group</th><th>Source</th><th className="r">Qty</th><th>Received</th></tr></thead>
          <tbody>{open.intakes?.map((i) => <tr key={i.id}><td className="small">{i.reference}</td><td>{i.producer_name}{i.producer_phone ? <div className="small muted">{i.producer_phone}</div> : null}</td>
            <td className="small">{i.producer_group || "—"}</td><td className="small">{i.source_location || "—"}</td><td className="r num">{kg(i.quantity, i.unit)}</td><td className="small">{fmtDateTime(i.received_at)}</td></tr>)}</tbody></table></div>
        {open.inspections?.map((x) => <div key={x.id} className="alert info" style={{ marginTop: 10 }}>
          <b>Inspection: {x.result.replace(/_/g, " ")}</b> by {x.inspector} · {fmtDateTime(x.inspected_at)} · accepted {kg(x.accepted_qty)} · rejected {kg(x.rejected_qty)}
          {x.reason && <div>Reason: {x.reason}</div>}{x.corrective_action && <div>Corrective action: {x.corrective_action}</div>}</div>)}
      </div>}
      {node}
    </>
  );
}
