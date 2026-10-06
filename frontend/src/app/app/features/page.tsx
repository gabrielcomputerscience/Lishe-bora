"use client";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ErrorBox, PageHead, Pill, useToast } from "@/components/ui";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Cat = { page: string; label: string; group: string; permissions: string[]; audience: string };
type RoleRow = { key: string; name: string; pages: string[]; customised: boolean; possible: string[] };
type UserPage = { page: string; label: string; group: string; status: "default" | "added" | "removed" | "available" | "needs_role"; shown: boolean;
  needs: string[]; note: string };
type UserFeat = { user: { id: string; full_name: string; email: string | null; roles: string[] }; pages: UserPage[]; menu: string[] };
type U = { id: string; full_name: string; email: string | null; phone: string | null; roles: { role_name: string; org_name: string | null }[] };

const STATUS: Record<UserPage["status"] | "other_type", [string, string]> = {
  default: ["approved", "From role"], added: ["submitted", "Added for this person"], removed: ["rejected", "Hidden for this person"],
  available: ["draft", "Can be added"], needs_role: ["draft", "Needs another role"], other_type: ["draft", "Not for this account"],
};

function groupBy<T extends { group: string }>(rows: T[]) {
  const out: [string, T[]][] = [];
  rows.forEach((r) => { const g = out.find(([k]) => k === r.group); if (g) g[1].push(r); else out.push([r.group, [r]]); });
  return out;
}

function ByRole({ onToast }: { onToast: (m: string) => void }) {
  const [d, setD] = useState<{ catalog: Cat[]; roles: RoleRow[] } | null>(null);
  const [key, setKey] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => get<{ catalog: Cat[]; roles: RoleRow[] }>("/features").then((x) => { setD(x); setKey((k) => k || x.roles[0]?.key || ""); }).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  const role = d?.roles.find((r) => r.key === key);
  useEffect(() => { if (role) setSel(new Set(role.pages)); }, [role]);
  if (!d) return <ErrorBox error={err} />;
  async function save() {
    try { await put(`/features/roles/${key}`, { pages: [...sel] }); onToast("Menu saved for this role"); load(); } catch (x) { setErr(x); }
  }
  async function reset() {
    try { await post(`/features/roles/${key}/reset`); onToast("Back to the standard menu"); load(); } catch (x) { setErr(x); }
  }
  return (
    <div className="card">
      <ErrorBox error={err} />
      <div className="row" style={{ marginBottom: 12 }}>
        <label className="small"><b>Role</b>{" "}
          <select className="btn" value={key} onChange={(e) => setKey(e.target.value)} aria-label="Role">
            {d.roles.map((r) => <option key={r.key} value={r.key}>{r.name}{r.customised ? " (changed)" : ""}</option>)}</select></label>
        {role?.customised && <Pill status="submitted" label="Changed from standard" />}
        <span className="spacer" />
        {role?.customised && <button className="btn" onClick={reset}>Reset to standard</button>}
        <button className="btn primary" onClick={save}>Save for everyone with this role</button>
      </div>
      <p className="small muted">Tick the pages people with this role should see. Pages greyed out need a permission this role does not have.
        Dashboard, Notifications and My profile are always shown.</p>
      {groupBy(d.catalog).map(([g, rows]) => (
        <div key={g} style={{ marginBottom: 10 }}><div className="small" style={{ fontWeight: 700, color: "var(--gold)", textTransform: "uppercase", letterSpacing: ".05em" }}>{g}</div>
          <div className="grid g3" style={{ gap: 6 }}>{rows.map((c) => {
            const ok = !!role?.possible.includes(c.page);
            return <label key={c.page} className="row small" style={{ gap: 8, opacity: ok ? 1 : 0.45 }} title={ok ? "" : `Needs: ${c.permissions.join(" or ") || c.audience}`}>
              <input type="checkbox" disabled={!ok} checked={sel.has(c.page)}
                     onChange={(e) => { const n = new Set(sel); if (e.target.checked) n.add(c.page); else n.delete(c.page); setSel(n); }} />{c.label}</label>;
          })}</div></div>))}
    </div>
  );
}

function ByPerson({ initial, onToast }: { initial: string | null; onToast: (m: string) => void }) {
  const [q, setQ] = useState("");
  const [list, setList] = useState<U[]>([]);
  const [uid, setUid] = useState<string | null>(initial);
  const [f, setF] = useState<UserFeat | null>(null);
  const [add, setAdd] = useState<Set<string>>(new Set());
  const [rem, setRem] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { const t = setTimeout(() => get<{ items: U[] }>(`/users?size=20&q=${encodeURIComponent(q)}`).then((r) => setList(r.items)).catch(setErr), 250); return () => clearTimeout(t); }, [q]);
  const loadUser = useCallback((id: string) => get<UserFeat>(`/users/${id}/features`).then((x) => {
    setF(x); setAdd(new Set(x.pages.filter((p) => p.status === "added").map((p) => p.page))); setRem(new Set(x.pages.filter((p) => p.status === "removed").map((p) => p.page)));
  }).catch(setErr), []);
  useEffect(() => { if (uid) loadUser(uid); }, [uid, loadUser]);
  const shownCount = useMemo(() => f?.pages.filter((p) => p.status !== "needs_role" && !rem.has(p.page) && (p.status === "default" || p.status === "removed" || add.has(p.page))).length ?? 0, [f, add, rem]);
  async function save() {
    try { await put(`/users/${uid}/features`, { add: [...add], remove: [...rem] }); onToast("Saved. The person sees the change next time a page loads."); loadUser(uid!); }
    catch (x) { setErr(x); }
  }
  function toggle(p: UserPage, on: boolean) {
    const a = new Set(add), r = new Set(rem);
    const fromRole = p.status === "default" || p.status === "removed";
    if (fromRole) { if (on) r.delete(p.page); else r.add(p.page); } else { if (on) a.add(p.page); else a.delete(p.page); }
    setAdd(a); setRem(r);
  }
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(220px,300px) 1fr", alignItems: "start" }}>
      <div className="card">
        <input placeholder="Search name, email or phone" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" style={{ width: "100%" }} />
        <div style={{ marginTop: 8, maxHeight: 520, overflowY: "auto" }}>{list.map((u) => (
          <button key={u.id} className="btn" onClick={() => setUid(u.id)} style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6, fontWeight: 400,
            borderColor: u.id === uid ? "var(--gold)" : undefined }}>
            <b>{u.full_name}</b><div className="small muted">{u.roles.map((r) => r.role_name).join(", ") || "No role"}</div></button>))}</div>
      </div>
      <div className="card">
        <ErrorBox error={err} />
        {!f && <p className="muted">Choose a person to see and change the pages in their menu.</p>}
        {f && <>
          <div className="row"><h2 style={{ margin: 0 }}>{f.user.full_name}</h2><span className="small muted">{f.user.email}</span><span className="spacer" />
            <span className="small">{shownCount} page(s) in menu</span><button className="btn primary" onClick={save}>Save</button></div>
          <p className="small muted">Tick to show a page, untick to hide it. Adding a page never gives new rights: a page marked “needs another role” requires
            assigning one of the listed roles under Users &amp; roles first.</p>
          {groupBy(f.pages).map(([g, rows]) => (
            <div key={g} style={{ marginBottom: 10 }}><div className="small" style={{ fontWeight: 700, color: "var(--gold)", textTransform: "uppercase", letterSpacing: ".05em" }}>{g}</div>
              <div className="tablewrap"><table style={{ tableLayout: "fixed" }}><tbody>{rows.map((p) => {
                const fromRole = p.status === "default" || p.status === "removed";
                const checked = p.status === "needs_role" ? false : fromRole ? !rem.has(p.page) : add.has(p.page);
                const st = p.status === "needs_role" && p.note ? "other_type" : p.status === "needs_role" ? "needs_role" : fromRole ? (rem.has(p.page) ? "removed" : "default") : add.has(p.page) ? "added" : "available";
                return <tr key={p.page}>
                  <td style={{ width: 30 }}><input type="checkbox" aria-label={p.label} disabled={p.status === "needs_role"} checked={checked} onChange={(e) => toggle(p, e.target.checked)} /></td>
                  <td style={{ width: 230 }}><b>{p.label}</b></td>
                  <td style={{ width: 210 }}><Pill status={STATUS[st][0]} label={STATUS[st][1]} /></td>
                  <td className="small muted">{p.status === "needs_role" ? (p.note || (p.needs.length ? `Assign one of: ${p.needs.join(", ")}` : "")) : ""}</td></tr>;
              })}</tbody></table></div></div>))}
        </>}
      </div>
    </div>
  );
}

export default function FeaturesPage() {
  return <Suspense fallback={<div className="muted">Loading…</div>}><Features /></Suspense>;
}

function Features() {
  const { me } = useAuth();
  const params = useSearchParams();
  const initialUser = params.get("user");
  const [tab, setTab] = useState<"person" | "role">(initialUser ? "person" : "role");
  const { toast, node } = useToast();
  if (me && !me.is_super_admin) return <div className="card"><h2>Super Administrator only</h2><p className="muted">Only the Super Administrator can change features and menus.</p></div>;
  return (
    <>
      <PageHead crumb="Administration" title="Features & menus"
                sub="Each person sees only the pages their role needs. Change the standard menu of a role, or add and hide pages for one person." />
      <div className="tabs">{([["role", "By role"], ["person", "By person"]] as const).map(([k, l]) =>
        <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "role" ? <ByRole onToast={toast} /> : <ByPerson initial={initialUser} onToast={toast} />}
      {node}
    </>
  );
}
