"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHead, Pill, useToast } from "@/components/ui";
import { ApiError, api, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, human } from "@/lib/format";

type Status = { env: string; database: string; notify_backend: string; email: string; rate_limits: boolean; https_cookies: boolean;
  jobs: Record<string, { at: string; result: Record<string, number> | null; error: string }>; outbox: { queued: number; sent: number; failed: number };
  failed_messages: { id: string; channel: string; to: string; subject: string; attempts: number; error: string; created_at: string }[];
  counts: { users: number; schools: number } };
type Line = { line: number; action: string; errors: string[]; [k: string]: unknown };
type Preview = { committed: boolean; rows: number; create: number; update?: number; add_role?: number; errors: number; lines: Line[] };
const JOBS: [string, string][] = [["send", "Send SMS & email"], ["sla", "Overdue approval reminders"], ["late_payments", "Late-payment check"],
  ["risk", "Risk scan"], ["documents", "Expiring supplier documents"], ["contracts", "Expiring contracts"], ["stock", "Stock expiry & stock-outs"]];
const TEMPLATES = {
  schools: "county,sub_county,cluster,school_code,school_name,enrolment,lat,lng,nemis_code\nMakueni County,Kibwezi West,,MAKUENI-SCH101,Example Primary School,450,-2.3551,37.9012,\n",
  prices: "code,reference_price\nBEANS,130\nMAIZE-FLOUR,70\n",
  users: "full_name,email,phone,role,org_code\nExample Head Teacher,head@example.org,,school_admin,MAKUENI-SCH101\nExample Meals Officer,,0712345678,school_meals_officer,MAKUENI-SCH101\n",
};

type Org = { id: string; name: string; code: string; type: string; parent_id: string | null };

/** Counties: replace the placeholder pilot names with the confirmed ones, or add a county before importing its schools. */
function Counties() {
  const [rows, setRows] = useState<Org[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [add, setAdd] = useState({ name: "", code: "" });
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<Org[]>("/orgs?type=county").then((r) => { setRows(r); setNames(Object.fromEntries(r.map((o) => [o.id, o.name]))); }).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  async function rename(o: Org) { setErr(null); try { await api(`/orgs/${o.id}`, { method: "PUT", body: { name: names[o.id] } }); toast("Renamed"); load(); } catch (x) { setErr(x); } }
  async function create() {
    setErr(null);
    try {
      const country = (await get<Org[]>("/orgs?type=country"))[0];
      await post("/orgs", { type: "county", name: add.name, code: add.code.toUpperCase(), parent_id: country?.id ?? null }); setAdd({ name: "", code: "" }); toast("County added"); load();
    } catch (x) { setErr(x); }
  }
  return (
    <div className="card"><h2>Counties</h2>
      <p className="small muted">The seed creates the pilot counties of the sampled schools (Makueni, Embu, Isiolo). Add further counties here before importing their schools. You can rename a county; its code never changes, so everything linked stays linked.</p>
      <ErrorBox error={err} />
      <div className="tablewrap"><table><tbody>{rows.map((o) => <tr key={o.id}><td className="small muted">{o.code}</td>
        <td><input className="btn" style={{ fontWeight: 400, width: "100%" }} aria-label={`Name of ${o.code}`} value={names[o.id] ?? ""} onChange={(e) => setNames({ ...names, [o.id]: e.target.value })} /></td>
        <td className="r"><button className="btn sm" disabled={names[o.id] === o.name} onClick={() => rename(o)}>Save</button></td></tr>)}</tbody></table></div>
      <div className="row" style={{ marginTop: 8 }}><input className="btn" style={{ fontWeight: 400 }} placeholder="New county name" aria-label="New county name" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} />
        <input className="btn" style={{ fontWeight: 400, width: 140 }} placeholder="Code, e.g. KE-047" aria-label="New county code" value={add.code} onChange={(e) => setAdd({ ...add, code: e.target.value })} />
        <button className="btn" disabled={add.name.length < 2 || add.code.length < 2} onClick={create}>Add county</button></div>
      {node}
    </div>
  );
}

function Importer({ kind, title, help }: { kind: "schools" | "users" | "prices"; title: string; help: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  async function send(commit: boolean) {
    if (!file) return; setErr(null);
    const fd = new FormData(); fd.append("file", file);
    try { const r = await api<Preview>(`/system/import/${kind}?commit=${commit}`, { method: "POST", body: fd }); setPv(r); if (r.committed) toast("Imported"); }
    catch (x) { setErr(x); if (x instanceof ApiError && x.code === "IMPORT_ERRORS") setPv(null); }
  }
  const tpl = `data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATES[kind])}`;
  return (
    <div className="card">
      <div className="row"><h2>{title}</h2><span className="spacer" /><a className="btn sm" href={tpl} download={`lishebora_${kind}_template.csv`}>Template</a></div>
      <p className="small muted">{help}</p>
      <div className="row"><input type="file" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label={`${kind} file`} onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPv(null); }} />
        <button className="btn" disabled={!file} onClick={() => send(false)}>Check file</button>
        <button className="btn primary" disabled={!pv || pv.errors > 0 || pv.committed} onClick={() => send(true)}>Import {pv ? pv.rows : ""} rows</button></div>
      <ErrorBox error={err} />
      {pv && <div style={{ marginTop: 10 }}>
        <p className="small"><b>{pv.committed ? "Imported." : "Preview, nothing saved yet."}</b> {pv.create} new · {pv.update ?? pv.add_role ?? 0} {kind === "users" ? "extra roles" : "updated"} · {pv.errors} with errors</p>
        <div className="tablewrap"><table><tbody>{pv.lines.map((l) => <tr key={l.line}><td className="small">Line {l.line}</td>
          <td className="small">{String(l.school_name ?? l.full_name ?? l.name ?? "")}{l.price ? ` · KES ${String(l.price)}` : ""} {l.school_code ? `(${String(l.school_code)})` : ""}{l.role ? ` · ${String(l.role)}` : ""}{l.org ? ` · ${String(l.org)}` : ""}</td>
          <td><Pill status={l.action === "error" ? "rejected" : "approved"} label={human(l.action)} /></td><td className="small">{l.errors.join("; ")}</td></tr>)}</tbody></table></div>
      </div>}
      {node}
    </div>
  );
}

export default function SystemPage() {
  const { can } = useAuth();
  const [s, setS] = useState<Status | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const { toast, node } = useToast();
  const load = useCallback(() => get<Status>("/system/status").then(setS).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  async function run(task: string) {
    setBusy(task); setErr(null);
    try { const r = await post<Record<string, number>>(`/system/jobs/${task}/run`); toast(`${human(task)}: ${JSON.stringify(r)}`); load(); } catch (x) { setErr(x); } finally { setBusy(""); }
  }
  async function retry(id: string) { try { const r = await post<{ sent: boolean; error: string }>(`/system/outbox/${id}/retry`); toast(r.sent ? "Sent" : `Still failing: ${r.error}`); load(); } catch (x) { setErr(x); } }
  const flag = (ok: boolean, yes: string, no: string) => <Pill status={ok ? "approved" : "submitted"} label={ok ? yes : no} />;
  return (
    <>
      <PageHead crumb="Administration" title="System & onboarding" sub="Health of the platform, background jobs, the SMS/email outbox, and bulk import of schools and staff for the pilot." />
      <ErrorBox error={err} />
      {s && <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Environment</div><div className="v" style={{ fontSize: 20 }}>{human(s.env)}</div><div className="small muted">{s.database} database</div></div>
        <div className="card kpi leaf"><div className="l">SMS / email</div><div className="v" style={{ fontSize: 20 }}>{human(s.notify_backend)} / {s.email}</div>
          <div className="small muted">{s.outbox.sent} sent · {s.outbox.queued} queued · {s.outbox.failed} failed</div></div>
        <div className="card kpi gold"><div className="l">Protection</div><div className="small" style={{ marginTop: 6 }}>{flag(s.https_cookies, "HTTPS cookies", "HTTP cookies (dev)")} {flag(s.rate_limits, "Rate limits on", "Rate limits off")}</div></div>
        <div className="card kpi purple"><div className="l">Records</div><div className="v" style={{ fontSize: 20 }}>{s.counts.schools} schools</div><div className="small muted">{s.counts.users} user accounts</div></div>
      </div>}
      {s && <div className="grid g2" style={{ alignItems: "start", marginBottom: 16 }}>
        <div className="card"><h2>Background jobs</h2>
          <p className="small muted">In production the worker runs these automatically. You can run one now.</p>
          <div className="tablewrap"><table><tbody>{JOBS.map(([k, l]) => { const j = s.jobs[k]; return <tr key={k}><td><b>{l}</b>
            <div className="small muted">{j ? `Last run ${fmtDateTime(j.at)}` : "Not run yet"}{j?.error ? ` · error: ${j.error}` : j?.result ? ` · ${Object.entries(j.result).map(([a, b]) => `${human(a)} ${b}`).join(", ")}` : ""}</div></td>
            <td className="r"><button className="btn sm" disabled={!!busy} onClick={() => run(k)}>{busy === k ? "Running…" : "Run now"}</button></td></tr>; })}</tbody></table></div></div>
        <div className="card"><h2>Messages that could not be sent ({s.failed_messages.length})</h2>
          <div className="tablewrap"><table><tbody>{s.failed_messages.map((m) => <tr key={m.id}><td className="small">{m.channel.toUpperCase()} → {m.to}<div className="muted">{m.subject}</div></td>
            <td className="small">{m.attempts} attempts<div className="muted">{m.error}</div></td><td className="r"><button className="btn sm" onClick={() => retry(m.id)}>Retry</button></td></tr>)}
            {!s.failed_messages.length && <tr><td className="muted">None. All messages delivered or waiting to send.</td></tr>}</tbody></table></div></div>
      </div>}
      <div className="card" style={{ marginBottom: 16 }}><div className="row"><div><h2>Pilot data workbook</h2>
        <p className="small muted" style={{ margin: 0 }}>An Excel file with the schools, foods, role codes and organisation codes already filled in. Complete the shaded cells, then upload the same file to each import below (CSV files also work).</p></div>
        <span className="spacer" /><a className="btn primary" href="/api/v1/system/workbook">Download workbook</a><Link className="btn" href="/app/readiness">Pilot readiness</Link></div></div>
      <div className="stack">
        {can("md:edit") && <Counties />}
        {can("md:create") && <Importer kind="schools" title="Import schools" help="One row per school: county, sub_county, school_code, school_name, and optionally cluster, enrolment, lat, lng, nemis_code. Counties must already exist; sub-counties and clusters are created when missing. Re-importing a school code updates it (for example to add enrolment or GPS). Nothing is saved until the file checks out with no errors." />}
        {can("md:edit") && <Importer kind="prices" title="Import reference prices" help="Columns: code and reference_price (KES per kg, litre or tray), from the county market survey. Blank prices are left unchanged. Used for budget estimates and price checks on bids." />}
        {can("iam:create") && <Importer kind="users" title="Import staff accounts" help="One row per person and role. New users get a temporary password by SMS or email and must change it when they first sign in. Suppliers register themselves on the website. Segregation-of-duties conflicts are refused." />}
      </div>
      {node}
    </>
  );
}
