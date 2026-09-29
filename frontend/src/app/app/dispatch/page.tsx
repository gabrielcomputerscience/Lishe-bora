"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Balance, Dispatch } from "@/lib/fulfilment";
import { kg } from "@/lib/planning";

type OLine = { po_line_id: string; commodity_code: string; commodity: string; unit: string; quantity: number; dispatched_qty: number; accepted_qty: number;
  schools: { school_id: string; name: string; qty: number; remaining: number }[] };
type Order = { id: string; reference: string; supplier: string; status: string; delivery_window: string; lines: OLine[] };
type Row = { po_line_id: string; school_id: string; batch_id: string; quantity: string; on: boolean };
const today = () => new Date().toISOString().slice(0, 10);

export default function DispatchPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [stock, setStock] = useState<Balance[]>([]);
  const [drivers, setDrivers] = useState<{ id: string; name: string; phone: string }[]>([]);
  const [list, setList] = useState<Dispatch[]>([]);
  const [poId, setPoId] = useState("");
  const [src, setSrc] = useState("");
  const [hdr, setHdr] = useState({ vehicle: "", driver_user_id: "", driver_name: "", driver_phone: "", planned_date: today() });
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => {
    get<{ orders: Order[]; stock: Balance[] }>("/dispatch/orders").then((d) => { setOrders(d.orders); setStock(d.stock); }).catch(setErr);
    get<Dispatch[]>("/dispatches").then(setList).catch(() => {});
  }, []);
  useEffect(() => { load(); get<typeof drivers>("/dispatch/drivers").then(setDrivers).catch(() => {}); }, [load]);
  const po = orders.find((o) => o.id === poId);
  const sources = useMemo(() => [...new Map(stock.map((s) => [s.location_id, s.location])).entries()], [stock]);
  useEffect(() => {
    if (!po || !src) { setRows({}); return; }
    const r: Record<string, Row> = {};
    for (const ln of po.lines) {
      const batches = stock.filter((s) => s.location_id === src && s.commodity_code === ln.commodity_code);
      let avail = batches.reduce((a, b) => a + Number(b.on_hand), 0);
      for (const s of ln.schools) {
        if (Number(s.remaining) <= 0) continue;
        const q = Math.min(Number(s.remaining), avail); avail -= q;
        r[`${ln.po_line_id}|${s.school_id}`] = { po_line_id: ln.po_line_id, school_id: s.school_id, batch_id: batches[0]?.batch_id ?? "", quantity: q > 0 ? String(q) : "", on: q > 0 };
      }
    }
    setRows(r);
  }, [po, src, stock]);
  async function create() {
    setErr(null);
    const lines = Object.values(rows).filter((r) => r.on && Number(r.quantity) > 0).map(({ on: _on, ...r }) => r);
    try {
      await post("/dispatches", { po_id: poId, source_location_id: src, ...hdr, driver_user_id: hdr.driver_user_id || null, lines });
      toast("Dispatch planned"); setPoId(""); load();
    } catch (x) { setErr(x); }
  }
  async function act(d: Dispatch, what: "dispatch" | "cancel") {
    setErr(null);
    try { await post(`/dispatches/${d.id}/${what}`); toast(what === "dispatch" ? "Goods dispatched. Schools and driver notified." : "Cancelled"); load(); } catch (x) { setErr(x); }
  }
  const [route, setRoute] = useState<{ id: string; r: { order: string[]; total_km: number; method: string; without_coordinates: string[];
    stops: { school: string; km: number | null }[]; source: { name: string } } } | null>(null);
  async function showRoute(d: Dispatch) {
    setErr(null);
    try { const x = await get<{ suggested: NonNullable<typeof route>["r"] }>(`/dispatches/${d.id}/route`); setRoute({ id: d.id, r: x.suggested }); } catch (e) { setErr(e); }
  }
  async function saveRoute() { if (!route) return; try { await post(`/dispatches/${route.id}/route`); toast("Stop order saved to the trip"); setRoute(null); load(); } catch (e) { setErr(e); } }
  const upd = (k: string, p: Partial<Row>) => setRows({ ...rows, [k]: { ...rows[k], ...p } });
  return (
    <>
      <PageHead crumb="Fulfil" title="Dispatch" sub="Plan deliveries against acknowledged purchase orders, using stock that has passed inspection." />
      <ErrorBox error={err} />
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Plan a dispatch</h2>
        <div className="grid g3">
          <Field label="Purchase order"><select value={poId} onChange={(e) => setPoId(e.target.value)}><option value="">Choose…</option>
            {orders.map((o) => <option key={o.id} value={o.id}>{o.reference} · {o.supplier}</option>)}</select></Field>
          <Field label="Dispatch from"><select value={src} onChange={(e) => setSrc(e.target.value)}><option value="">Choose…</option>
            {sources.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select></Field>
          <Field label="Planned delivery date"><input type="date" value={hdr.planned_date} onChange={(e) => setHdr({ ...hdr, planned_date: e.target.value })} /></Field>
          <Field label="Vehicle registration"><input value={hdr.vehicle} onChange={(e) => setHdr({ ...hdr, vehicle: e.target.value })} placeholder="KCX 123A" /></Field>
          <Field label="Driver"><select value={hdr.driver_user_id} onChange={(e) => setHdr({ ...hdr, driver_user_id: e.target.value })}><option value="">Not on the platform</option>
            {drivers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
          {!hdr.driver_user_id && <Field label="Driver name / phone"><input value={hdr.driver_name} onChange={(e) => setHdr({ ...hdr, driver_name: e.target.value })} placeholder="Name, phone" /></Field>}
        </div>
        {!orders.length && <p className="small muted">No acknowledged orders are waiting for delivery.</p>}
        {po && src && <div className="tablewrap" style={{ marginTop: 8 }}><table>
          <thead><tr><th /><th>School</th><th>Commodity</th><th className="r">Still to send</th><th>Batch</th><th className="r">Quantity</th></tr></thead>
          <tbody>{po.lines.flatMap((ln) => ln.schools.map((s) => { const k = `${ln.po_line_id}|${s.school_id}`; const r = rows[k];
            const opts = stock.filter((b) => b.location_id === src && b.commodity_code === ln.commodity_code);
            return <tr key={k}><td>{r && <input type="checkbox" aria-label={`Include ${s.name} ${ln.commodity}`} checked={r.on} onChange={(e) => upd(k, { on: e.target.checked })} />}</td>
              <td>{s.name}</td><td>{ln.commodity}</td><td className="r num">{kg(s.remaining, ln.unit)}</td>
              <td>{r ? (opts.length ? <select className="btn" style={{ fontWeight: 400 }} value={r.batch_id} onChange={(e) => upd(k, { batch_id: e.target.value })}>
                {opts.map((b) => <option key={b.batch_id!} value={b.batch_id!}>{b.batch_code} ({kg(b.on_hand, b.unit)})</option>)}</select> : <span className="small muted">No cleared stock here</span>)
                : <span className="small muted">Complete</span>}</td>
              <td className="r">{r && <input type="number" min="0" step="0.01" aria-label={`Qty ${s.name} ${ln.commodity}`} className="btn" style={{ width: 110, fontWeight: 400 }} value={r.quantity} onChange={(e) => upd(k, { quantity: e.target.value })} />}</td></tr>; }))}</tbody></table></div>}
        <button className="btn primary" style={{ marginTop: 12 }} disabled={!po || !src || !Object.values(rows).some((r) => r.on && Number(r.quantity) > 0 && r.batch_id)} onClick={create}>Create dispatch</button>
      </div>
      <div className="card"><h2>Dispatches</h2><div className="tablewrap"><table>
        <thead><tr><th>Dispatch</th><th>Order</th><th>From</th><th>Stops</th><th>Date</th><th>Vehicle / driver</th><th>Status</th><th /></tr></thead>
        <tbody>{list.map((d) => <tr key={d.id}><td><b>{d.reference}</b><div className="small muted">{kg(d.total_qty)}</div></td><td className="small">{d.po}</td><td className="small">{d.source}</td>
          <td className="small">{d.stops.map((s) => <div key={s.school_id}>{s.school} {s.pod ? "✓" : ""}</div>)}</td><td className="small">{fmtDate(d.planned_date)}</td>
          <td className="small">{d.vehicle || "—"}<div className="muted">{d.driver_name}</div></td><td><Pill status={d.status} /></td>
          <td className="r"><div className="row" style={{ justifyContent: "flex-end" }}>
            {d.can_dispatch && <button className="btn sm primary" onClick={() => act(d, "dispatch")}>Dispatch</button>}
            {d.status === "planned" && <button className="btn sm ghost" onClick={() => act(d, "cancel")}>Cancel</button>}
            {(d.status === "planned" || d.status === "dispatched") && <button className="btn sm" onClick={() => showRoute(d)}>Route</button>}
            <Link className="btn sm" href={`/app/deliveries?dispatch=${d.id}`}>Track</Link></div></td></tr>)}
          {!list.length && <tr><td colSpan={8} className="muted">No dispatches yet.</td></tr>}</tbody></table></div>
        {route && <div className="alert info" style={{ marginTop: 12 }}>
          <b>Suggested stop order</b> from {route.r.source.name}: {route.r.stops.map((s, i) => `${i + 1}. ${s.school}${s.km != null ? ` (${s.km} km)` : ""}`).join(" → ")}
          <div className="small">About {route.r.total_km} km in straight lines ({route.r.method}).{route.r.without_coordinates.length ? " Some schools have no coordinates yet and are listed last." : ""}</div>
          <div className="row" style={{ marginTop: 6 }}><button className="btn sm primary" onClick={saveRoute}>Save to trip</button><button className="btn sm ghost" onClick={() => setRoute(null)}>Close</button></div></div>}
      </div>
      {node}
    </>
  );
}
