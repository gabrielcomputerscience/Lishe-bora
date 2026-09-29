"use client";
import { useCallback, useEffect, useState } from "react";
import { WorkflowPanel, type WF } from "@/components/Workflow";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";

type Comp = { commodity: string; portion_g: number };
type Day = { label: string; dish: string; components: Comp[] };
type Summary = { cycle_days: number; food_groups: Record<string, number>; group_count: number; meets_minimum: boolean; minimum: number; missing_groups: string[] };
type MenuT = { id: string; name: string; description: string; status: string; days: Day[]; summary: Summary; workflow: WF | null; approved_at: string | null };
type Term = { id: string; name: string; year: number; term_no: number; starts_on: string; ends_on: string; feeding_days: number };
type Com = { code: string; name: string; category: string; food_group?: string };
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export default function Menus() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"menus" | "terms">("menus");
  const [menus, setMenus] = useState<MenuT[]>([]);
  const [terms, setTerms] = useState<Term[]>([]);
  const [comms, setComms] = useState<Com[]>([]);
  const [edit, setEdit] = useState<{ id?: string; name: string; description: string; days: Day[] } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [t, setT] = useState({ year: 2027, term_no: 1, name: "", starts_on: "", ends_on: "", feeding_days: 60 });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => {
    get<MenuT[]>("/menus").then(setMenus).catch(setErr);
    get<Term[]>("/terms").then(setTerms).catch(() => {});
  }, []);
  useEffect(() => {
    load(); get<Com[]>("/public/commodities").then(setComms).catch(() => {});
    const id = new URLSearchParams(window.location.search).get("id"); if (id) setOpen(id);
  }, [load]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); load(); } catch (e) { setErr(e); } };
  const name = (c: string) => comms.find((x) => x.code === c)?.name ?? c;

  const blank = () => setEdit({ name: "", description: "", days: DAYS.map((l) => ({ label: l, dish: "", components: [{ commodity: "", portion_g: 0 }] })) });
  const setDay = (i: number, d: Partial<Day>) => edit && setEdit({ ...edit, days: edit.days.map((x, j) => (j === i ? { ...x, ...d } : x)) });

  return (
    <>
      <PageHead crumb="Plan" title="Menus & terms" sub="Approved menus drive the demand calculation. Portions are grams per learner per meal." >
        {tab === "menus" && can("md:create") && <button className="btn primary" onClick={blank}>+ New menu</button>}
      </PageHead>
      <div className="tabs"><button className={`tab ${tab === "menus" ? "on" : ""}`} onClick={() => setTab("menus")}>Menus</button>
        <button className={`tab ${tab === "terms" ? "on" : ""}`} onClick={() => setTab("terms")}>Academic terms</button></div>
      <ErrorBox error={err} />

      {tab === "menus" && edit && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>{edit.id ? "Edit menu" : "New menu"}</h2>
          <div className="grid g2"><Field label="Name"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Description"><input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field></div>
          {edit.days.map((d, i) => (
            <div key={i} style={{ borderTop: "1px solid var(--line)", padding: "10px 0" }}>
              <div className="grid" style={{ gridTemplateColumns: "90px 1fr", gap: 10 }}>
                <Field label="Day"><input value={d.label} onChange={(e) => setDay(i, { label: e.target.value })} /></Field>
                <Field label="Dish"><input value={d.dish} onChange={(e) => setDay(i, { dish: e.target.value })} placeholder="e.g. Githeri with cabbage" /></Field></div>
              {d.components.map((c, k) => (
                <div key={k} className="row" style={{ marginBottom: 6 }}>
                  <select aria-label="Commodity" className="btn" style={{ fontWeight: 400, minWidth: 220 }} value={c.commodity}
                    onChange={(e) => setDay(i, { components: d.components.map((x, j) => (j === k ? { ...x, commodity: e.target.value } : x)) })}>
                    <option value="">Commodity…</option>{comms.map((m) => <option key={m.code} value={m.code}>{m.name}</option>)}</select>
                  <input aria-label="Portion grams" type="number" min={1} className="btn" style={{ fontWeight: 400, width: 110 }} value={c.portion_g || ""} placeholder="grams"
                    onChange={(e) => setDay(i, { components: d.components.map((x, j) => (j === k ? { ...x, portion_g: Number(e.target.value) } : x)) })} />
                  <span className="small muted">g / learner</span>
                  <button className="btn sm" aria-label="Remove" onClick={() => setDay(i, { components: d.components.filter((_, j) => j !== k) })}>×</button>
                </div>))}
              <button className="btn sm" onClick={() => setDay(i, { components: [...d.components, { commodity: "", portion_g: 0 }] })}>+ Ingredient</button>
            </div>))}
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn sm" onClick={() => setEdit({ ...edit, days: [...edit.days, { label: `Day ${edit.days.length + 1}`, dish: "", components: [{ commodity: "", portion_g: 0 }] }] })}>+ Day</button>
            <span className="spacer" />
            <button className="btn" onClick={() => setEdit(null)}>Cancel</button>
            <button className="btn primary" onClick={() => run(async () => {
              const body = { name: edit.name, description: edit.description, days: edit.days.map((d) => ({ ...d, components: d.components.filter((c) => c.commodity && c.portion_g > 0) })) };
              if (edit.id) await put(`/menus/${edit.id}`, body); else await post("/menus", body); setEdit(null); }, "Menu saved as draft")}>Save draft</button>
          </div>
        </div>)}

      {tab === "menus" && <div className="stack">{menus.map((m) => (
        <div key={m.id} className="card">
          <div className="row"><h3>{m.name}</h3><Pill status={m.status} />
            <span className={`pill ${m.summary.meets_minimum ? "p-green" : "p-amber"}`}>{m.summary.group_count} food groups{m.summary.meets_minimum ? "" : ` · minimum ${m.summary.minimum}`}</span>
            <span className="spacer" />
            {m.status === "draft" && can("md:edit") && <button className="btn sm" onClick={() => setEdit({ id: m.id, name: m.name, description: m.description, days: m.days })}>Edit</button>}
            {m.status === "draft" && can("md:submit") && <button className="btn sm primary" onClick={() => run(() => post(`/menus/${m.id}/submit`), "Submitted for nutrition validation")}>Submit</button>}
            <button className="btn sm" onClick={() => setOpen(open === m.id ? null : m.id)}>{open === m.id ? "Hide" : "Details"}</button></div>
          {m.description && <p className="small muted" style={{ margin: "6px 0 0" }}>{m.description}</p>}
          {open === m.id && (<div className="grid g2" style={{ marginTop: 12, alignItems: "start" }}>
            <div className="tablewrap" style={{ margin: 0 }}><table><thead><tr><th>Day</th><th>Dish</th><th>Portions (g)</th></tr></thead>
              <tbody>{m.days.map((d) => <tr key={d.label}><td><b>{d.label}</b></td><td>{d.dish}</td>
                <td className="small">{d.components.map((c) => `${name(c.commodity)} ${c.portion_g}`).join(" · ")}</td></tr>)}</tbody></table>
              <p className="small muted">Food groups: {Object.entries(m.summary.food_groups).map(([g, n]) => `${g} (${n} days)`).join(", ") || "—"}
                {m.summary.missing_groups.length > 0 && <> · Missing: {m.summary.missing_groups.join(", ")}</>}</p>
              {m.approved_at && <p className="small muted">Approved {fmtDate(m.approved_at)}</p>}</div>
            <WorkflowPanel wf={m.workflow} onDone={load} /></div>)}
        </div>))}
        {!menus.length && <div className="card muted">No menus yet.</div>}</div>}

      {tab === "terms" && (<div className="grid" style={{ gridTemplateColumns: "2fr 1fr", alignItems: "start" }}>
        <div className="card"><div className="tablewrap"><table><thead><tr><th>Term</th><th>Starts</th><th>Ends</th><th className="r">Feeding days</th></tr></thead>
          <tbody>{terms.map((x) => <tr key={x.id}><td><b>{x.name}</b></td><td>{fmtDate(x.starts_on)}</td><td>{fmtDate(x.ends_on)}</td><td className="r">{x.feeding_days}</td></tr>)}</tbody></table></div>
          <p className="small muted">Dates are placeholders until the programme confirms the school calendar.</p></div>
        {can("md:create") && <div className="card"><h3>Add term</h3>
          <div className="grid g2"><Field label="Year"><input type="number" value={t.year} onChange={(e) => setT({ ...t, year: +e.target.value })} /></Field>
            <Field label="Term"><select value={t.term_no} onChange={(e) => setT({ ...t, term_no: +e.target.value })}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></Field></div>
          <Field label="Starts"><input type="date" value={t.starts_on} onChange={(e) => setT({ ...t, starts_on: e.target.value })} /></Field>
          <Field label="Ends"><input type="date" value={t.ends_on} onChange={(e) => setT({ ...t, ends_on: e.target.value })} /></Field>
          <Field label="Feeding days"><input type="number" value={t.feeding_days} onChange={(e) => setT({ ...t, feeding_days: +e.target.value })} /></Field>
          <button className="btn primary" disabled={!t.starts_on || !t.ends_on} onClick={() => run(() => post("/terms", { ...t, name: `Term ${t.term_no} ${t.year}` }), "Term added")}>Add term</button></div>}
      </div>)}
      {node}
    </>
  );
}
