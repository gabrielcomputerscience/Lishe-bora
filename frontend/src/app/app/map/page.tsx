"use client";
import "leaflet/dist/leaflet.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBox, PageHead, useToast } from "@/components/ui";
import { get, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, human } from "@/lib/format";
import { kg } from "@/lib/planning";

type Pt = { id: string; name: string; type: string; lat: number; lng: number; on_hand_kg: number; stock_alerts: number; deliveries?: number;
  last_delivery?: string | null; open_complaints?: number };
type Trip = { id: string; reference: string; status: string; vehicle: string; driver: string; last_fix: { lat: number; lng: number; at: string; status: string } | null;
  source: { lat: number; lng: number } | null; stops: { school: string; lat?: number; lng?: number }[] };
type MapData = { points: Pt[]; without_coordinates: Omit<Pt, "lat" | "lng">[]; trips: Trip[];
  counts: { schools: number; schools_served: number; mapped: number; unmapped: number; trips_on_road: number } };

const STYLE: Record<string, { color: string; label: string }> = {
  served: { color: "#3D5A27", label: "School receiving food" }, waiting: { color: "#C98A00", label: "School not yet supplied" },
  aggregation_centre: { color: "#8A5A00", label: "Aggregation hub" }, warehouse: { color: "#6B3F8A", label: "Store / warehouse" },
};
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
const kind = (p: Pt) => (p.type === "school" ? (p.deliveries ? "served" : "waiting") : p.type);

export default function MapPage() {
  const { can } = useAuth();
  const el = useRef<HTMLDivElement>(null);
  const [d, setD] = useState<MapData | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<MapData>("/gis/map").then(setD).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!d || !el.current) return;
    // React (dev Strict Mode) runs this effect twice. Leaflet loads asynchronously, so the first run's cleanup can fire
    // before its map exists; the `cancelled` flag stops that run, and we clear any map left on the container.
    let map: import("leaflet").Map | null = null;
    let cancelled = false;
    const box = el.current as HTMLDivElement & { _leaflet_id?: number };
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !box) return;
      if (box._leaflet_id) { box.innerHTML = ""; delete box._leaflet_id; }
      map = L.map(box, { scrollWheelZoom: false });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(map);
      const bounds: [number, number][] = [];
      for (const p of d.points) {
        const k = kind(p), st = STYLE[k];
        bounds.push([p.lat, p.lng]);
        L.circleMarker([p.lat, p.lng], { radius: p.type === "school" ? 8 : 10, color: "#fff", weight: 2, fillColor: st.color, fillOpacity: 1 })
          .bindPopup(`<b>${esc(p.name)}</b><br>${st.label}` + (p.type === "school" ? `<br>${p.deliveries} deliveries · last ${p.last_delivery ? fmtDate(p.last_delivery) : "none"}` +
            (p.open_complaints ? `<br>${p.open_complaints} open complaint(s)` : "") : "") + `<br>Stock ${kg(p.on_hand_kg)}` + (p.stock_alerts ? ` · ${p.stock_alerts} alert(s)` : ""))
          .addTo(map);
      }
      for (const t of d.trips) {
        const path: [number, number][] = [];
        if (t.source) path.push([t.source.lat, t.source.lng]);
        t.stops.forEach((s) => s.lat != null && path.push([s.lat, s.lng!]));
        if (path.length > 1) L.polyline(path, { color: "#3D5A27", weight: 2, dashArray: "6 6" }).addTo(map);
        if (t.last_fix) {
          bounds.push([t.last_fix.lat, t.last_fix.lng]);
          L.circleMarker([t.last_fix.lat, t.last_fix.lng], { radius: 9, color: "#fff", weight: 2, fillColor: "#1F2A1A", fillOpacity: 1 })
            .bindPopup(`<b>${esc(t.reference)}</b><br>${esc(human(t.last_fix.status))} · ${esc(t.vehicle)} ${esc(t.driver)}`).addTo(map);
        }
      }
      if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 }); else map.setView([0.02, 37.9], 6);
    })();
    return () => { cancelled = true; map?.remove(); map = null; };
  }, [d]);
  function here(id: string) {
    if (!("geolocation" in navigator)) { toast("This device cannot share its location."); return; }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try { await put(`/fulfilment/locations/${id}/gps`, { lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy_m: pos.coords.accuracy }); toast("Location saved"); load(); }
      catch (x) { setErr(x); }
    }, () => toast("Location permission was refused."), { enableHighAccuracy: true, timeout: 10000 });
  }
  return (
    <>
      <PageHead crumb="Performance" title="Programme map" sub="Schools, hubs and stores with coordinates, and trips on the road with their last GPS position. Straight lines join each trip's stops." />
      <ErrorBox error={err} />
      {d && <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Schools receiving food</div><div className="v">{d.counts.schools_served} / {d.counts.schools}</div></div>
        <div className="card kpi leaf"><div className="l">Locations on the map</div><div className="v">{d.counts.mapped}</div></div>
        <div className="card kpi gold"><div className="l">Missing coordinates</div><div className="v">{d.counts.unmapped}</div></div>
        <div className="card kpi purple"><div className="l">Trips on the road</div><div className="v">{d.counts.trips_on_road}</div></div>
      </div>}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div ref={el} style={{ height: 520 }} role="application" aria-label="Map of schools, hubs and stores" />
        <div className="row small" style={{ padding: "10px 16px" }}>{Object.values(STYLE).map((s) => <span key={s.label} className="row" style={{ gap: 6 }}>
          <span style={{ width: 12, height: 12, borderRadius: 6, background: s.color, display: "inline-block" }} />{s.label}</span>)}
          <span className="row" style={{ gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 6, background: "#1F2A1A", display: "inline-block" }} />Vehicle (last GPS)</span></div>
      </div>
      {d && d.without_coordinates.length > 0 && <div className="card" style={{ marginTop: 16 }}><h2>Locations without coordinates</h2>
        <p className="small muted">Staff at the location can open this page on their phone and tap “Use my location”. To type, correct or pick coordinates on a map, use <a href="/app/locations">School locations</a>.</p>
        <div className="tablewrap"><table><tbody>{d.without_coordinates.map((o) => <tr key={o.id}><td>{o.name}</td><td className="small">{human(o.type)}</td>
          <td className="r">{can("md:edit", "inv:create", "agg:create", "log:approve") && <button className="btn sm" onClick={() => here(o.id)}>Use my location</button>}</td></tr>)}</tbody></table></div></div>}
      {node}
    </>
  );
}
