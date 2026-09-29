"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { WorkflowPanel, type WF } from "@/components/Workflow";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, human } from "@/lib/format";
import type { Balance, Loc, Movement } from "@/lib/fulfilment";
import { kg } from "@/lib/planning";

type Count = { id: string; reference: string; location: string; status: string; note: string; created_at: string;
  lines: { batch_code: string | null; commodity_code: string; system_qty: string; counted_qty: string; variance: string }[]; workflow: WF | null };
type Tab = "balances" | "movements" | "adjust" | "count" | "transfer" | "use";

export default function Inventory() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("balances");
  const [locs, setLocs] = useState<Loc[]>([]);
  const [loc, setLoc] = useState("");
  const [bal, setBal] = useState<Balance[]>([]);
  const [movs, setMovs] = useState<Movement[]>([]);
  const [counts, setCounts] = useState<Count[]>([]);
  const [wf, setWf] = useState<WF | null>(null);
  const [adj, setAdj] = useState({ key: "", quantity: "", type: "waste", reason: "" });
  const [cnt, setCnt] = useState<Record<string, string>>({});
  const [trf, setTrf] = useState({ key: "", to: "", quantity: "", note: "" });
  const [use, setUse] = useState({ commodity_code: "", quantity: "", meals_served: "", note: "" });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const qs = loc ? `?location_id=${loc}` : "";
  const load = useCallback(() => {
    setErr(null);
    get<Balance[]>(`/inventory/balances${qs}`).then(setBal).catch(setErr);
    get<Movement[]>(`/inventory/movements${qs}`).then(setMovs).catch(() => {});
    get<Count[]>("/inventory/counts").then(setCounts).catch(() => {});
  }, [qs]);
  useEffect(() => { get<Loc[]>("/fulfilment/locations").then(setLocs).catch(setErr); }, []);
  useEffect(() => { load(); }, [load]);
  const loadWf = useCallback(() => {
    const u = new URLSearchParams(window.location.search);
    const [ent, id] = u.get("movement") ? ["stock_movement", u.get("movement")] : u.get("count") ? ["stock_count", u.get("count")] : [null, null];
    if (ent && id) get<WF>(`/workflow/for/${ent}/${id}`).then(setWf).catch(setErr);
  }, []);
  useEffect(() => { loadWf(); }, [loadWf]);

  const here = bal.filter((b) => !loc || b.location_id === loc);
  const current = locs.find((l) => l.id === loc);
  const keyOf = (b: Balance) => `${b.location_id}|${b.batch_id ?? ""}|${b.commodity_code}`;
  const byKey = (k: string) => bal.find((b) => keyOf(b) === k);
  async function run(fn: () => Promise<unknown>, msg: string) { setErr(null); try { await fn(); toast(msg); load(); } catch (x) { setErr(x); } }
  const needLoc = <div className="alert info">Choose a location above first.</div>;
  return (
    <>
      <PageHead crumb="Fulfil" title="Inventory" sub="Stock is calculated from posted movements. Adjustments and write-offs take effect only after a second person approves them.">
        <select className="btn" value={loc} onChange={(e) => setLoc(e.target.value)} aria-label="Location">
          <option value="">All my locations</option>{locs.map((l) => <option key={l.id} value={l.id}>{l.name} ({human(l.type)})</option>)}</select>
      </PageHead>
      <ErrorBox error={err} />
      {wf && <div style={{ marginBottom: 16 }}><WorkflowPanel wf={wf} onDone={() => { loadWf(); load(); }} /></div>}
      <div className="tabs">{([["balances", "Stock on hand"], ["movements", "Movements"], ...(can("inv:create") ? [["adjust", "Adjust / write off"], ["count", "Stock count"], ["transfer", "Transfer"]] : []),
        ...(can("inv:create") && current?.type === "school" ? [["use", "Record meals use"]] : [])] as [Tab, string][]).map(([k, l]) =>
        <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}</div>

      {tab === "balances" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>Location</th><th>Commodity</th><th>Batch</th><th className="r">On hand</th><th className="r">Pending</th><th>Expiry</th><th /></tr></thead>
        <tbody>{here.map((b) => <tr key={keyOf(b)}><td>{b.location}<div className="small muted">{human(b.location_type)}</div></td><td>{b.commodity}</td>
          <td>{b.batch_code ? <Link href={`/app/trace/${b.batch_code}`}>{b.batch_code}</Link> : "—"}{b.grade && <div className="small muted">{b.grade}</div>}</td>
          <td className="r num"><b>{kg(b.on_hand, b.unit)}</b></td><td className="r num small">{Number(b.pending_adjustment) ? kg(b.pending_adjustment, b.unit) : ""}</td>
          <td className="small">{fmtDate(b.expiry_date)}</td><td>{b.alerts.map((a) => <span key={a} className="pill p-amber">{a}</span>)}</td></tr>)}
          {!here.length && <tr><td colSpan={7} className="muted">No stock recorded.</td></tr>}</tbody></table></div></div>}

      {tab === "movements" && <div className="card"><div className="tablewrap"><table>
        <thead><tr><th>When</th><th>Location</th><th>Type</th><th>Batch</th><th className="r">Qty</th><th>Reference</th><th>Status</th><th /></tr></thead>
        <tbody>{movs.map((m) => <tr key={m.id}><td className="small">{fmtDateTime(m.at)}</td><td className="small">{m.location}</td><td>{human(m.type)}</td>
          <td className="small">{m.batch_code ?? m.commodity_code}</td><td className={`r num ${Number(m.quantity) < 0 ? "" : ""}`}>{Number(m.quantity) > 0 ? "+" : ""}{kg(m.quantity, m.unit)}</td>
          <td className="small">{m.source_ref || m.source_entity}<div className="muted">{m.reason}</div></td><td><Pill status={m.status} /></td>
          <td>{m.status === "pending_approval" && <Link className="btn sm" href={`/app/inventory?movement=${m.id}`} onClick={() => setTimeout(loadWf, 50)}>Approval</Link>}</td></tr>)}
          {!movs.length && <tr><td colSpan={8} className="muted">No movements.</td></tr>}</tbody></table></div></div>}

      {tab === "adjust" && (!loc ? needLoc : <div className="card" style={{ maxWidth: 640 }}>
        <h2>Adjustment or write-off at {current?.name}</h2>
        <Field label="Stock line"><select value={adj.key} onChange={(e) => setAdj({ ...adj, key: e.target.value })}><option value="">Choose…</option>
          {here.map((b) => <option key={keyOf(b)} value={keyOf(b)}>{b.commodity} · {b.batch_code ?? "no batch"} · {kg(b.on_hand, b.unit)}</option>)}</select></Field>
        <div className="grid g2">
          <Field label="Type"><select value={adj.type} onChange={(e) => setAdj({ ...adj, type: e.target.value })}><option value="waste">Write-off (damaged / expired / lost)</option><option value="adjustment">Correction (+ or −)</option></select></Field>
          <Field label="Quantity" hint={adj.type === "waste" ? "Enter a negative number, e.g. -5" : "Negative reduces stock"}><input type="number" step="0.01" value={adj.quantity} onChange={(e) => setAdj({ ...adj, quantity: e.target.value })} /></Field>
        </div>
        <Field label="Reason"><textarea rows={2} value={adj.reason} onChange={(e) => setAdj({ ...adj, reason: e.target.value })} /></Field>
        <button className="btn primary" disabled={!adj.key} onClick={() => { const b = byKey(adj.key)!; run(() => post("/inventory/adjustments", { location_id: loc, batch_id: b.batch_id, commodity_code: b.commodity_code,
          quantity: adj.quantity, type: adj.type, reason: adj.reason }), "Sent for approval"); setAdj({ key: "", quantity: "", type: "waste", reason: "" }); }}>Submit for approval</button>
      </div>)}

      {tab === "count" && (!loc ? needLoc : <div className="stack">
        <div className="card"><h2>Physical count at {current?.name}</h2>
          <p className="small muted">Enter what you counted. Differences are posted as adjustments once a supervisor approves the count.</p>
          <div className="tablewrap"><table><thead><tr><th>Commodity</th><th>Batch</th><th className="r">System</th><th className="r">Counted</th><th className="r">Difference</th></tr></thead>
            <tbody>{here.map((b) => { const k = keyOf(b); const v = cnt[k]; return <tr key={k}><td>{b.commodity}</td><td className="small">{b.batch_code ?? "—"}</td><td className="r num">{kg(b.on_hand, b.unit)}</td>
              <td className="r"><input type="number" step="0.01" min="0" aria-label={`Counted ${b.batch_code ?? b.commodity_code}`} className="btn" style={{ width: 110, fontWeight: 400 }} value={v ?? ""} onChange={(e) => setCnt({ ...cnt, [k]: e.target.value })} /></td>
              <td className="r num">{v !== undefined && v !== "" ? (Number(v) - Number(b.on_hand)).toFixed(2) : ""}</td></tr>; })}</tbody></table></div>
          <button className="btn primary" style={{ marginTop: 10 }} disabled={!Object.values(cnt).some((v) => v !== "")} onClick={() => run(async () => {
            await post("/inventory/counts", { location_id: loc, lines: here.filter((b) => (cnt[keyOf(b)] ?? "") !== "").map((b) => ({ batch_id: b.batch_id, commodity_code: b.commodity_code, counted_qty: cnt[keyOf(b)] })) });
            setCnt({}); }, "Count submitted")}>Submit count</button></div>
        <div className="card"><h3>Recent counts</h3><div className="tablewrap"><table><tbody>{counts.map((c) => <tr key={c.id}><td><b>{c.reference}</b><div className="small muted">{c.location} · {fmtDateTime(c.created_at)}</div></td>
          <td className="small">{c.lines.map((l) => `${l.batch_code ?? l.commodity_code}: ${l.variance}`).join(" · ")}</td><td><Pill status={c.status} /></td>
          <td>{c.workflow?.status === "active" && <Link className="btn sm" href={`/app/inventory?count=${c.id}`} onClick={() => setTimeout(loadWf, 50)}>Approval</Link>}</td></tr>)}
          {!counts.length && <tr><td className="muted">No counts yet.</td></tr>}</tbody></table></div></div>
      </div>)}

      {tab === "transfer" && (!loc ? needLoc : <div className="card" style={{ maxWidth: 640 }}><h2>Transfer from {current?.name}</h2>
        <Field label="Batch"><select value={trf.key} onChange={(e) => setTrf({ ...trf, key: e.target.value })}><option value="">Choose…</option>
          {here.filter((b) => b.batch_id && Number(b.on_hand) > 0).map((b) => <option key={keyOf(b)} value={keyOf(b)}>{b.commodity} · {b.batch_code} · {kg(b.on_hand, b.unit)}</option>)}</select></Field>
        <div className="grid g2">
          <Field label="To"><select value={trf.to} onChange={(e) => setTrf({ ...trf, to: e.target.value })}><option value="">Choose…</option>
            {locs.filter((l) => l.id !== loc).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></Field>
          <Field label="Quantity"><input type="number" min="0" step="0.01" value={trf.quantity} onChange={(e) => setTrf({ ...trf, quantity: e.target.value })} /></Field>
        </div>
        <Field label="Note"><input value={trf.note} onChange={(e) => setTrf({ ...trf, note: e.target.value })} /></Field>
        <button className="btn primary" disabled={!trf.key || !trf.to} onClick={() => { const b = byKey(trf.key)!; run(() => post("/inventory/transfers", { from_location_id: loc, to_location_id: trf.to,
          batch_id: b.batch_id, quantity: trf.quantity, note: trf.note }), "Transfer posted"); setTrf({ key: "", to: "", quantity: "", note: "" }); }}>Post transfer</button></div>)}

      {tab === "use" && <div className="card" style={{ maxWidth: 640 }}><h2>Food used for meals at {current?.name}</h2>
        <div className="grid g2">
          <Field label="Commodity"><select value={use.commodity_code} onChange={(e) => setUse({ ...use, commodity_code: e.target.value })}><option value="">Choose…</option>
            {[...new Map(here.map((b) => [b.commodity_code, b])).values()].map((b) => <option key={b.commodity_code} value={b.commodity_code}>{b.commodity}</option>)}</select></Field>
          <Field label="Quantity used"><input type="number" min="0" step="0.01" value={use.quantity} onChange={(e) => setUse({ ...use, quantity: e.target.value })} /></Field>
          <Field label="Meals served (optional)"><input type="number" min="0" value={use.meals_served} onChange={(e) => setUse({ ...use, meals_served: e.target.value })} /></Field>
          <Field label="Note"><input value={use.note} onChange={(e) => setUse({ ...use, note: e.target.value })} /></Field>
        </div>
        <button className="btn primary" disabled={!use.commodity_code} onClick={() => run(() => post("/inventory/consumption", { location_id: loc, commodity_code: use.commodity_code, quantity: use.quantity,
          meals_served: use.meals_served ? Number(use.meals_served) : null, note: use.note }), "Recorded")}>Record use</button></div>}
      {node}
    </>
  );
}
