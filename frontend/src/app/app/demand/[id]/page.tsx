"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { WorkflowPanel } from "@/components/Workflow";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { kg, type Demand } from "@/lib/planning";

type Opt = { id: string; name: string };
export default function DemandDetail() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [d, setD] = useState<Demand | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [stock, setStock] = useState<Record<string, string>>({});
  const [ov, setOv] = useState<Record<string, { qty: string; reason: string }>>({});
  const [menus, setMenus] = useState<Opt[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const hydrate = (x: Demand) => {
    setD(x);
    setForm({ menu_id: x.menu_id ?? "", enrolment: String(x.enrolment), attendance_pct: String(x.attendance_pct), feeding_days: String(x.feeding_days),
      wastage_pct: String(x.wastage_pct), storage_capacity_kg: x.storage_capacity_kg == null ? "" : String(x.storage_capacity_kg),
      preferred_delivery: x.preferred_delivery, notes: x.notes });
    setStock(Object.fromEntries((x.lines ?? []).map((l) => [l.commodity, String(l.stock_qty)])));
    setOv(Object.fromEntries((x.lines ?? []).filter((l) => l.override_qty != null).map((l) => [l.commodity, { qty: String(l.override_qty), reason: l.override_reason }])));
  };
  const load = useCallback(() => get<Demand>(`/demands/${id}`).then(hydrate).catch(setErr), [id]);
  useEffect(() => { load(); get<Opt[]>("/menus?status=approved").then(setMenus).catch(() => {}); }, [load]);
  if (!d) return <ErrorBox error={err} />;
  const editable = can("dem:edit") && ["draft", "returned"].includes(d.status);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  async function save(andSubmit = false) {
    setErr(null);
    try {
      const body = { school_id: d!.school_id, term_id: d!.term_id, menu_id: form.menu_id || null, enrolment: +form.enrolment,
        attendance_pct: +form.attendance_pct, feeding_days: +form.feeding_days, wastage_pct: +form.wastage_pct,
        storage_capacity_kg: form.storage_capacity_kg ? +form.storage_capacity_kg : null, preferred_delivery: form.preferred_delivery, notes: form.notes,
        stock: Object.entries(stock).map(([commodity, qty]) => ({ commodity, qty: +qty || 0 })),
        overrides: Object.entries(ov).filter(([, v]) => v.qty !== "").map(([commodity, v]) => ({ commodity, qty: +v.qty, reason: v.reason })) };
      let x = await put<Demand>(`/demands/${id}`, body);
      if (andSubmit) { x = await post<Demand>(`/demands/${id}/submit`); toast("Submitted for approval"); } else toast("Recalculated and saved");
      hydrate(x);
    } catch (e) { setErr(e); load(); }
  }

  return (
    <>
      <PageHead crumb="Plan › School demand" title={`${d.school} · ${d.term}`} sub={d.reference}><Pill status={d.status} /></PageHead>
      <ErrorBox error={err} />
      {d.flags.length > 0 && <div className="card" style={{ marginBottom: 16 }}><h3>Checks</h3>
        {d.flags.map((f, i) => <div key={i} className={`alert ${f.severity === "error" ? "bad" : "warn"}`}>{f.message}</div>)}</div>}
      <div className="grid" style={{ gridTemplateColumns: "1fr 2fr", alignItems: "start" }}>
        <div className="card"><h3>Inputs</h3>
          <fieldset disabled={!editable} style={{ border: 0, padding: 0, margin: 0 }}>
            <Field label="Approved menu"><select value={form.menu_id} onChange={set("menu_id")}><option value="">Choose…</option>{menus.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
            <div className="grid g2"><Field label="Learners (enrolment)"><input type="number" value={form.enrolment} onChange={set("enrolment")} /></Field>
              <Field label="Attendance %"><input type="number" value={form.attendance_pct} onChange={set("attendance_pct")} /></Field></div>
            <div className="grid g2"><Field label="Feeding days"><input type="number" value={form.feeding_days} onChange={set("feeding_days")} /></Field>
              <Field label="Wastage %" hint="Approved by county"><input type="number" value={form.wastage_pct} onChange={set("wastage_pct")} /></Field></div>
            <Field label="Storage capacity (kg)"><input type="number" value={form.storage_capacity_kg} onChange={set("storage_capacity_kg")} /></Field>
            <Field label="Preferred delivery"><input value={form.preferred_delivery} onChange={set("preferred_delivery")} placeholder="e.g. two deliveries, Tue mornings" /></Field>
            <Field label="Notes"><textarea rows={2} value={form.notes} onChange={set("notes")} /></Field>
          </fieldset>
          {d.nutrition && <div className={`alert ${d.nutrition.meets_minimum ? "info" : "warn"}`}>
            Menu covers {d.nutrition.group_count} food groups (minimum {d.nutrition.minimum}).{d.nutrition.missing_groups.length ? ` Missing: ${d.nutrition.missing_groups.join(", ")}.` : ""}</div>}
        </div>
        <div className="stack">
          <div className="card"><div className="row"><h3>Calculated requirement</h3><span className="spacer" /><span className="small muted">Total {kg(d.total_kg)}</span></div>
            <div className="tablewrap"><table>
              <thead><tr><th>Commodity</th><th className="r">g / learner / cycle</th><th className="r">Gross need</th><th className="r">Stock on hand</th><th className="r">To procure</th><th>Adjust</th></tr></thead>
              <tbody>{(d.lines ?? []).map((l) => <tr key={l.commodity}>
                <td><b>{l.name}</b></td><td className="r num">{Number(l.grams_per_learner_cycle)}</td><td className="r num">{kg(l.gross_qty, l.unit)}</td>
                <td className="r">{editable ? <input aria-label={`Stock ${l.name}`} type="number" min={0} className="btn" style={{ width: 100, fontWeight: 400, textAlign: "right" }}
                  value={stock[l.commodity] ?? ""} onChange={(e) => setStock({ ...stock, [l.commodity]: e.target.value })} /> : kg(l.stock_qty, l.unit)}</td>
                <td className="r num"><b>{kg(l.final_qty, l.unit)}</b>{l.override_qty != null && <div className="small muted">calc {kg(l.net_qty, l.unit)}</div>}</td>
                <td>{editable ? <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                  <input aria-label="Override quantity" type="number" min={0} placeholder="qty" className="btn" style={{ width: 80, fontWeight: 400 }}
                    value={ov[l.commodity]?.qty ?? ""} onChange={(e) => setOv({ ...ov, [l.commodity]: { qty: e.target.value, reason: ov[l.commodity]?.reason ?? "" } })} />
                  {ov[l.commodity]?.qty && <input aria-label="Reason" placeholder="reason" className="btn" style={{ width: 130, fontWeight: 400 }}
                    value={ov[l.commodity]?.reason ?? ""} onChange={(e) => setOv({ ...ov, [l.commodity]: { qty: ov[l.commodity].qty, reason: e.target.value } })} />}
                </div> : <span className="small muted">{l.override_reason}</span>}</td></tr>)}
                {!d.lines?.length && <tr><td colSpan={6} className="muted">Choose a menu and save to calculate.</td></tr>}</tbody></table></div>
            {editable && <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
              <button className="btn" onClick={() => save(false)}>Recalculate &amp; save</button>
              {can("dem:submit") && <button className="btn primary" onClick={() => save(true)}>Submit for approval</button>}</div>}
          </div>
          <WorkflowPanel wf={d.workflow ?? null} history={d.history} onDone={load} />
        </div>
      </div>
      {node}
    </>
  );
}
