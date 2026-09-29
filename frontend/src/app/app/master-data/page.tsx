"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { FoodCategory } from "@/lib/types";

type Com = { id: string; code: string; name: string; category: string; unit: string; standard_pack: string; food_group: string;
  quality_spec: Record<string, unknown>; default_portion_g: string | null; reference_price: string | null; is_active: boolean };
type Org = { id: string; name: string; code: string; type: string; parent_id: string | null; is_active: boolean };
const UNITS = ["kg", "litre", "tray", "piece", "bag"];

function Commodities() {
  const { can } = useAuth();
  const [cats, setCats] = useState<FoodCategory[]>([]);
  const [rows, setRows] = useState<Com[]>([]);
  const [edit, setEdit] = useState<Com | null>(null);
  const [add, setAdd] = useState({ code: "", name: "", category: "", unit: "kg", reference_price: "" });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Com[]>("/commodities").then(setRows).catch(setErr), []);
  useEffect(() => { load(); get<FoodCategory[]>("/public/food-categories").then(setCats).catch(() => {}); }, [load]);
  const clean = (c: Com) => ({ ...c, reference_price: c.reference_price === "" ? null : c.reference_price });
  async function save(c: Com) { setErr(null); try { await put(`/commodities/${c.id}`, clean(c)); setEdit(null); toast("Saved"); load(); } catch (x) { setErr(x); } }
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { await post("/commodities", { ...add, reference_price: add.reference_price || null }); setAdd({ code: "", name: "", category: "", unit: "kg", reference_price: "" }); toast("Commodity added"); load(); }
    catch (x) { setErr(x); }
  }
  const groups = cats.map((g) => ({ ...g, rows: rows.filter((r) => r.category === g.key) }));
  const other = rows.filter((r) => !cats.some((g) => g.key === r.category));
  return (
    <>
      <ErrorBox error={err} />
      {groups.concat(other.length ? [{ key: "_", label: "Other (not a programme category)", group: "", commodities: [], rows: other }] : []).map((g) => (
        <div key={g.key} className="card"><h3>{g.label} <span className="small muted">{g.group && `· counts as ${g.group}`}</span></h3>
          <div className="tablewrap"><table><thead><tr><th>Code</th><th>Name</th><th>Unit</th><th className="r">Reference price (KES)</th><th>Status</th><th /></tr></thead>
            <tbody>{g.rows.map((c) => edit?.id === c.id ? (
              <tr key={c.id}><td className="small muted">{c.code}</td>
                <td><input className="btn" style={{ fontWeight: 400, width: "100%" }} aria-label="Name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></td>
                <td><select aria-label="Unit" value={edit.unit} onChange={(e) => setEdit({ ...edit, unit: e.target.value })}>{UNITS.map((u) => <option key={u}>{u}</option>)}</select></td>
                <td className="r"><input className="btn" style={{ fontWeight: 400, width: 110 }} inputMode="decimal" aria-label="Reference price" value={edit.reference_price ?? ""} onChange={(e) => setEdit({ ...edit, reference_price: e.target.value })} /></td>
                <td><label className="small"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Active</label></td>
                <td className="r"><button className="btn sm primary" onClick={() => save(edit)}>Save</button> <button className="btn sm" onClick={() => setEdit(null)}>Cancel</button></td></tr>
            ) : (
              <tr key={c.id}><td className="small muted">{c.code}</td><td>{c.name}</td><td>{c.unit}</td><td className="r">{c.reference_price ?? "—"}</td>
                <td><Pill status={c.is_active ? "active" : "inactive"} label={c.is_active ? "Active" : "Inactive"} /></td>
                <td className="r">{can("md:edit") && <button className="btn sm" onClick={() => setEdit({ ...c })}>Edit</button>}</td></tr>))}
              {!g.rows.length && <tr><td colSpan={6} className="small muted">No commodities in this category yet.</td></tr>}</tbody></table></div></div>))}
      {can("md:create") && <form className="card" onSubmit={create}><h3>Add a commodity</h3>
        <div className="grid g2">
          <Field label="Food category" id="cc"><select id="cc" value={add.category} onChange={(e) => setAdd({ ...add, category: e.target.value })} required><option value="">Choose…</option>
            {cats.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}</select></Field>
          <Field label="Name" id="cn"><input id="cn" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} required /></Field>
          <Field label="Code" id="cd" hint="Short and permanent, e.g. FINGER-MILLET"><input id="cd" value={add.code} onChange={(e) => setAdd({ ...add, code: e.target.value.toUpperCase() })} required /></Field>
          <Field label="Unit" id="cu"><select id="cu" value={add.unit} onChange={(e) => setAdd({ ...add, unit: e.target.value })}>{UNITS.map((u) => <option key={u}>{u}</option>)}</select></Field>
          <Field label="Reference price (KES per unit, optional)" id="cp"><input id="cp" inputMode="decimal" value={add.reference_price} onChange={(e) => setAdd({ ...add, reference_price: e.target.value })} /></Field>
        </div>
        <button className="btn primary" disabled={!add.category || !add.name || add.code.length < 2}>Add commodity</button></form>}
      {node}
    </>
  );
}

function Schools() {
  const { can } = useAuth();
  const [counties, setCounties] = useState<Org[]>([]);
  const [subs, setSubs] = useState<Org[]>([]);
  const [schools, setSchools] = useState<Org[]>([]);
  const [county, setCounty] = useState("");
  const [edit, setEdit] = useState<Org | null>(null);
  const [add, setAdd] = useState({ name: "", code: "", parent_id: "" });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => Promise.all([get<Org[]>("/orgs?type=county"), get<Org[]>("/orgs?type=sub_county"), get<Org[]>("/orgs?type=school_cluster"), get<Org[]>("/orgs?type=school")])
    .then(([c, s, cl, sc]) => { setCounties(c); setSubs([...s, ...cl]); setSchools(sc); setCounty((x) => x || c[0]?.id || ""); }).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  const mySubs = useMemo(() => {
    const ids = new Set([county]);
    const out: Org[] = [];
    for (let i = 0; i < 3; i++) for (const s of subs) if (s.parent_id && ids.has(s.parent_id) && !ids.has(s.id)) { ids.add(s.id); out.push(s); }
    return out;
  }, [subs, county]);
  async function save(o: Org) { setErr(null); try { await put(`/orgs/${o.id}`, { name: o.name, code: o.code, is_active: o.is_active }); setEdit(null); toast("Saved"); load(); } catch (x) { setErr(x); } }
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { await post("/orgs", { type: "school", name: add.name, code: add.code.toUpperCase(), parent_id: add.parent_id }); setAdd({ name: "", code: "", parent_id: "" }); toast("School added"); load(); }
    catch (x) { setErr(x); }
  }
  const row = (o: Org, kind: string) => edit?.id === o.id ? (
    <tr key={o.id}><td>{kind}</td>
      <td><input className="btn" style={{ fontWeight: 400, width: "100%" }} aria-label="Name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></td>
      <td><input className="btn" style={{ fontWeight: 400, width: 170 }} aria-label="Code" value={edit.code} onChange={(e) => setEdit({ ...edit, code: e.target.value.toUpperCase() })} /></td>
      <td><label className="small"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Active</label></td>
      <td className="r"><button className="btn sm primary" onClick={() => save(edit)}>Save</button> <button className="btn sm" onClick={() => setEdit(null)}>Cancel</button></td></tr>
  ) : (
    <tr key={o.id}><td className="small muted">{kind}</td><td>{kind === "School" ? o.name : <b>{o.name}</b>}</td><td className="small muted">{o.code}</td>
      <td>{!o.is_active && <Pill status="inactive" label="Inactive" />}</td>
      <td className="r">{can("md:edit") && <button className="btn sm" onClick={() => setEdit({ ...o })}>Edit</button>}</td></tr>);
  return (
    <>
      <ErrorBox error={err} />
      <div className="card">
        <div className="row"><Field label="County" id="ct"><select id="ct" value={county} onChange={(e) => setCounty(e.target.value)}>{counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field></div>
        <p className="small muted">Change a school code to its NEMIS code here, or import many at once under System & onboarding. Orders, deliveries and users stay linked.</p>
        <div className="tablewrap"><table><thead><tr><th>Level</th><th>Name</th><th>Code</th><th /><th /></tr></thead><tbody>
          {mySubs.map((s) => [row(s, s.type === "sub_county" ? "Sub-county" : "Cluster"), ...schools.filter((x) => x.parent_id === s.id).map((x) => row(x, "School"))])}
          {!mySubs.length && <tr><td colSpan={5} className="small muted">No sub-counties yet. Import schools under System & onboarding.</td></tr>}</tbody></table></div>
      </div>
      {can("md:create") && mySubs.length > 0 && <form className="card" onSubmit={create}><h3>Add a school</h3>
        <div className="grid g2">
          <Field label="Sub-county" id="sp"><select id="sp" value={add.parent_id} onChange={(e) => setAdd({ ...add, parent_id: e.target.value })} required><option value="">Choose…</option>
            {mySubs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
          <Field label="School name" id="sn"><input id="sn" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} required /></Field>
          <Field label="School code" id="sc" hint="NEMIS code if known"><input id="sc" value={add.code} onChange={(e) => setAdd({ ...add, code: e.target.value.toUpperCase() })} required /></Field>
        </div>
        <button className="btn primary" disabled={!add.parent_id || add.name.length < 2 || add.code.length < 2}>Add school</button></form>}
      {node}
    </>
  );
}

export default function MasterData() {
  const [tab, setTab] = useState<"commodities" | "schools">("commodities");
  return (
    <>
      <PageHead crumb="Administration › Master data" title="Master data" sub="Commodities by food category, and the county → sub-county → school structure" />
      <div className="tabs"><button className={`tab ${tab === "commodities" ? "on" : ""}`} onClick={() => setTab("commodities")}>Commodities & food categories</button>
        <button className={`tab ${tab === "schools" ? "on" : ""}`} onClick={() => setTab("schools")}>Counties & schools</button></div>
      {tab === "commodities" ? <Commodities /> : <Schools />}
    </>
  );
}
