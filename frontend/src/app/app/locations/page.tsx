"use client";
import "leaflet/dist/leaflet.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCrosshairs, faLocationDot, faMapLocationDot, faPen, faTrashCan } from "@fortawesome/free-solid-svg-icons";
import { ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { del, get, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";

type Gps = { lat: number; lng: number; accuracy_m?: number | null; source?: string; note?: string; by?: string; at?: string };
type Loc = { id: string; name: string; code: string; type: string; sub_county: string | null; county: string | null; gps: Gps | null };
type Resp = { items: Loc[]; total: number; mapped: number };

const SOURCE: Record<string, string> = { device: "Phone GPS on site", manual: "Typed in", map: "Picked on map", import: "Workbook import" };
const KENYA_CENTRE: [number, number] = [-1.8, 37.6];   // Makueni area; the map starts here when a school has no point yet

/** Accepts "-1.80, 37.62", "-1.80 37.62" or a Google Maps link (…@-1.80,37.62,15z or ?q=-1.80,37.62). */
function parsePair(s: string): [number, number] | null {
  const m = s.match(/(-?\d{1,2}\.\d+)\s*[, ]\s*(-?\d{1,3}\.\d+)/);
  return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
}

function PickMap({ lat, lng, onPick }: { lat?: number; lng?: number; onPick: (lat: number, lng: number) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const marker = useRef<import("leaflet").CircleMarker | null>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  useEffect(() => {
    let cancelled = false;
    const box = el.current as (HTMLDivElement & { _leaflet_id?: number }) | null;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !box) return;
      if (box._leaflet_id) { box.innerHTML = ""; delete box._leaflet_id; }
      const has = lat != null && lng != null && !isNaN(lat) && !isNaN(lng);
      const map = L.map(box).setView(has ? [lat!, lng!] : KENYA_CENTRE, has ? 16 : 9);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
      marker.current = L.circleMarker(has ? [lat!, lng!] : KENYA_CENTRE, { radius: 9, color: "#fff", weight: 3, fillColor: "#912E91", fillOpacity: has ? 1 : 0 }).addTo(map);
      map.on("click", (e: import("leaflet").LeafletMouseEvent) => onPick(e.latlng.lat, e.latlng.lng));
    })();
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {   // follow the form when the numbers change
    if (lat == null || lng == null || isNaN(lat) || isNaN(lng) || !marker.current) return;
    marker.current.setLatLng([lat, lng]).setStyle({ fillOpacity: 1 });
    mapRef.current?.panTo([lat, lng]);
  }, [lat, lng]);
  return <div ref={el} style={{ height: 300, borderRadius: 8, overflow: "hidden", border: "1px solid #D0D5C6" }} role="application"
              aria-label="Map: click the school's position" />;
}

function Editor({ loc, onDone, onCancel }: { loc: Loc; onDone: () => void; onCancel: () => void }) {
  const [lat, setLat] = useState(loc.gps ? String(loc.gps.lat) : "");
  const [lng, setLng] = useState(loc.gps ? String(loc.gps.lng) : "");
  const [acc, setAcc] = useState<number | null>(null);
  const [source, setSource] = useState<"device" | "manual" | "map">("manual");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);

  function locate() {
    setErr(null); setMsg(null);
    if (!("geolocation" in navigator)) { setMsg("This device cannot share its location. Type the coordinates or pick the point on the map."); return; }
    if (!window.isSecureContext) { setMsg("The browser only shares GPS on a secure (https) address. Type the coordinates or pick the point on the map, or open the system through its https address."); return; }
    setBusy(true); setMsg("Getting your position… stand outside, near the school kitchen or office, for the best reading.");
    navigator.geolocation.getCurrentPosition((pos) => {
      setBusy(false);
      setLat(pos.coords.latitude.toFixed(6)); setLng(pos.coords.longitude.toFixed(6)); setAcc(Math.round(pos.coords.accuracy)); setSource("device");
      setMsg(pos.coords.accuracy > 100 ? `Accuracy is only about ±${Math.round(pos.coords.accuracy)} m. Move into the open and tap “Use my location” again, or save if the point on the map is right.`
        : `Position found (±${Math.round(pos.coords.accuracy)} m). Check the point on the map, then save.`);
    }, (e) => { setBusy(false); setMsg(e.code === 1 ? "Location permission was refused. Allow location for this site in the browser settings, or type the coordinates." : "Could not get a GPS fix. Try again outside, or type the coordinates."); },
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  }
  function paste(v: string) {
    const pr = parsePair(v);
    if (pr) { setLat(pr[0].toFixed(6)); setLng(pr[1].toFixed(6)); setSource("manual"); setAcc(null); return true; }
    return false;
  }
  async function save() {
    setErr(null);
    const a = parseFloat(lat), b = parseFloat(lng);
    if (isNaN(a) || isNaN(b)) { setErr(new Error("Enter both latitude and longitude as decimal numbers, e.g. -1.803512 and 37.620145.")); return; }
    setBusy(true);
    try { await put(`/fulfilment/locations/${loc.id}/gps`, { lat: a, lng: b, accuracy_m: source === "device" ? acc : null, source, note }); onDone(); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  const a = parseFloat(lat), b = parseFloat(lng);
  return (
    <div className="card" style={{ marginBottom: 16, borderLeft: "4px solid var(--purple)" }}>
      <h2 style={{ marginTop: 0 }}>Set location: {loc.name}</h2>
      <p className="small muted" style={{ marginTop: -6 }}>At the school, tap <b>Use my location</b>. From the office, click the school on the map, type the numbers, or paste a Google Maps link.</p>
      <ErrorBox error={err} />
      {msg && <div className="alert warn small">{msg}</div>}
      <div className="row" style={{ marginBottom: 12 }}>
        <button className="btn gold" onClick={locate} disabled={busy}><FontAwesomeIcon icon={faCrosshairs} /> Use my location</button>
      </div>
      <div className="grid g2" style={{ gap: 16, alignItems: "start" }}>
        <div>
          <Field label="Latitude" hint="Kenya: about -4.7 to 5.0. South of the equator is negative (Makueni ≈ -1.8)." id="lat">
            <input id="lat" inputMode="decimal" value={lat} onChange={(e) => { if (!paste(e.target.value)) { setLat(e.target.value); setSource("manual"); setAcc(null); } }} placeholder="-1.803512" />
          </Field>
          <Field label="Longitude" hint="Kenya: about 33.9 to 41.9 (Makueni ≈ 37.6)." id="lng">
            <input id="lng" inputMode="decimal" value={lng} onChange={(e) => { setLng(e.target.value); setSource("manual"); setAcc(null); }} placeholder="37.620145" />
          </Field>
          <Field label="Or paste coordinates / a Google Maps link" id="paste">
            <input id="paste" placeholder="-1.803512, 37.620145" onChange={(e) => paste(e.target.value)} />
          </Field>
          <Field label="Note (optional)" hint="e.g. “Taken at the school kitchen gate”." id="note">
            <input id="note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="small muted" style={{ marginBottom: 10 }}>How this will be recorded: <b>{SOURCE[source]}</b>{source === "device" && acc != null ? ` (±${acc} m)` : ""}</div>
          <div className="row">
            <button className="btn" onClick={save} disabled={busy}>Save location</button>
            <button className="btn ghost" onClick={onCancel} disabled={busy}>Cancel</button>
          </div>
        </div>
        <PickMap lat={isNaN(a) ? undefined : a} lng={isNaN(b) ? undefined : b}
                 onPick={(y, x) => { setLat(y.toFixed(6)); setLng(x.toFixed(6)); setSource("map"); setAcc(null); setMsg("Point picked on the map. Zoom in to check it is on the school, then save."); }} />
      </div>
    </div>
  );
}

export default function LocationsPage() {
  const { can } = useAuth();
  const admin = can("md:edit");
  const [d, setD] = useState<Resp | null>(null);
  const [q, setQ] = useState("");
  const [missing, setMissing] = useState(false);
  const [edit, setEdit] = useState<Loc | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Resp>(`/fulfilment/gps-locations?type=school&missing=${missing}&q=${encodeURIComponent(q)}`).then(setD).catch(setErr), [q, missing]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  async function clear(l: Loc) {
    if (!window.confirm(`Remove the coordinates of ${l.name}? The school will need to be located again.`)) return;
    try { await del(`/fulfilment/locations/${l.id}/gps`); toast("Coordinates removed"); load(); } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Schools" title="School locations"
                sub="GPS coordinates put each school on the programme map and in delivery route planning. School staff can set their own school; administrators can set or correct any school." />
      <ErrorBox error={err} />
      {d && <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Schools</div><div className="v">{d.total}</div></div>
        <div className="card kpi leaf"><div className="l">With coordinates</div><div className="v">{d.mapped}</div></div>
        <div className="card kpi gold"><div className="l">Still to locate</div><div className="v">{d.total - d.mapped}</div></div>
      </div>}
      {edit && <Editor key={edit.id} loc={edit} onCancel={() => setEdit(null)} onDone={() => { setEdit(null); toast("Location saved"); load(); }} />}
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input placeholder="Search school name or code" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 320 }} aria-label="Search schools" />
          <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} /> Only schools without coordinates</label>
        </div>
        <div className="tablewrap"><table>
          <thead><tr><th>School</th><th>Area</th><th>Coordinates</th><th>How captured</th><th /></tr></thead>
          <tbody>{d?.items.map((l) => <tr key={l.id}>
            <td><b>{l.name}</b><div className="small muted">{l.code}</div></td>
            <td className="small">{[l.sub_county, l.county].filter(Boolean).join(", ")}</td>
            <td className="small">{l.gps ? <a href={`https://www.openstreetmap.org/?mlat=${l.gps.lat}&mlon=${l.gps.lng}#map=17/${l.gps.lat}/${l.gps.lng}`} target="_blank" rel="noreferrer">
              <FontAwesomeIcon icon={faLocationDot} /> {l.gps.lat.toFixed(5)}, {l.gps.lng.toFixed(5)}</a> : <span className="muted">Not set</span>}</td>
            <td className="small">{l.gps ? <>{SOURCE[l.gps.source ?? ""] ?? "Recorded"}{l.gps.accuracy_m ? ` (±${Math.round(l.gps.accuracy_m)} m)` : ""}
              {(l.gps.by || l.gps.at) && <div className="muted">{l.gps.by}{l.gps.at ? ` · ${fmtDateTime(l.gps.at)}` : ""}</div>}
              {l.gps.note && <div className="muted">“{l.gps.note}”</div>}</> : ""}</td>
            <td className="r" style={{ whiteSpace: "nowrap" }}>
              <button className="btn sm" onClick={() => { setEdit(l); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                <FontAwesomeIcon icon={l.gps ? faPen : faMapLocationDot} /> {l.gps ? "Update" : "Set location"}</button>
              {admin && l.gps && <button className="btn sm ghost" style={{ marginLeft: 6 }} onClick={() => clear(l)} aria-label={`Remove coordinates of ${l.name}`}><FontAwesomeIcon icon={faTrashCan} /></button>}
            </td></tr>)}
            {d && !d.items.length && <tr><td colSpan={5} className="muted">No schools match.</td></tr>}
          </tbody></table></div>
      </div>
      {node}
    </>
  );
}
