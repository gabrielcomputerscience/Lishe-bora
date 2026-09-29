"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill } from "@/components/ui";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import { kg, type Demand } from "@/lib/planning";

type Opt = { id: string; name: string };
export default function DemandList() {
  const { can } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Demand[]>([]);
  const [schools, setSchools] = useState<Opt[]>([]);
  const [terms, setTerms] = useState<(Opt & { feeding_days: number })[]>([]);
  const [menus, setMenus] = useState<Opt[]>([]);
  const [f, setF] = useState({ school_id: "", term_id: "", menu_id: "", enrolment: "", feeding_days: "" });
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    get<Demand[]>("/demands").then(setRows).catch(setErr);
    get<(Opt & { meta?: { enrolment?: number } })[]>("/demands/schools").then((s) => { setSchools(s); if (s.length === 1) setF((x) => ({ ...x, school_id: s[0].id, enrolment: x.enrolment || (s[0].meta?.enrolment ? String(s[0].meta.enrolment) : "") })); }).catch(() => {});
    get<(Opt & { feeding_days: number })[]>("/terms").then(setTerms).catch(() => {});
    get<Opt[]>("/menus?status=approved").then(setMenus).catch(() => {});
  }, []);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try {
      const d = await post<Demand>("/demands", { school_id: f.school_id, term_id: f.term_id, menu_id: f.menu_id || null,
        enrolment: Number(f.enrolment), feeding_days: Number(f.feeding_days) });
      router.push(`/app/demand/${d.id}`);
    } catch (x) { setErr(x); }
  }
  return (
    <>
      <PageHead crumb="Plan" title="School demand" sub="Enrolment × attendance × feeding days × menu portions, less stock on hand." />
      <ErrorBox error={err} />
      <div className="grid" style={{ gridTemplateColumns: can("dem:create") ? "2fr 1fr" : "1fr", alignItems: "start" }}>
        <div className="card"><div className="tablewrap"><table>
          <thead><tr><th>School</th><th>Term</th><th className="r">Learners</th><th className="r">Total food</th><th>Checks</th><th>Updated</th><th>Status</th><th /></tr></thead>
          <tbody>{rows.map((d) => {
            const errs = d.flags.filter((x) => x.severity === "error").length, warns = d.flags.length - errs;
            return <tr key={d.id}><td><b>{d.school}</b><div className="small muted">{d.reference}</div></td><td>{d.term}</td>
              <td className="r num">{d.enrolment}</td><td className="r num">{kg(d.total_kg)}</td>
              <td>{errs ? <span className="pill p-red">{errs} to fix</span> : warns ? <span className="pill p-amber">{warns} warning{warns > 1 ? "s" : ""}</span> : <span className="pill p-green">OK</span>}</td>
              <td className="small">{fmtDate(d.updated_at)}</td><td><Pill status={d.status} /></td>
              <td className="r"><Link className="btn sm primary" href={`/app/demand/${d.id}`}>Open</Link></td></tr>;
          })}{!rows.length && <tr><td colSpan={8} className="muted">No demand plans yet.</td></tr>}</tbody></table></div></div>
        {can("dem:create") && <form className="card" onSubmit={create}><h3>Start a demand plan</h3>
          <Field label="School"><select value={f.school_id} onChange={(e) => { const sc = schools.find((x) => x.id === e.target.value) as (Opt & { meta?: { enrolment?: number } }) | undefined;
            setF({ ...f, school_id: e.target.value, enrolment: f.enrolment || (sc?.meta?.enrolment ? String(sc.meta.enrolment) : "") }); }}><option value="">Choose…</option>{schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
          <Field label="Term"><select value={f.term_id} onChange={(e) => { const t = terms.find((x) => x.id === e.target.value); setF({ ...f, term_id: e.target.value, feeding_days: t ? String(t.feeding_days) : f.feeding_days }); }}>
            <option value="">Choose…</option>{terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
          <Field label="Approved menu"><select value={f.menu_id} onChange={(e) => setF({ ...f, menu_id: e.target.value })}><option value="">Choose…</option>{menus.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
          <div className="grid g2"><Field label="Learners"><input type="number" min={0} value={f.enrolment} onChange={(e) => setF({ ...f, enrolment: e.target.value })} /></Field>
            <Field label="Feeding days"><input type="number" min={0} value={f.feeding_days} onChange={(e) => setF({ ...f, feeding_days: e.target.value })} /></Field></div>
          <button className="btn primary" disabled={!f.school_id || !f.term_id}>Create &amp; calculate</button></form>}
      </div>
    </>
  );
}
