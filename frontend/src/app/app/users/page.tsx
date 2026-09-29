"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, Pill, useToast } from "@/components/ui";
import { del, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";

type Role = { key: string; name: string; tier: string; default_scope: string; requires_mfa: boolean; permissions: string[] };
type URole = { id: string; role: string; role_name: string; org_id: string | null; org_name: string | null };
type U = { id: string; full_name: string; email: string | null; phone: string | null; status: string; last_login_at: string | null; roles: URole[] };
const ADMIN = ["super_admin", "system_admin"];
const isAdminAcct = (u: { roles: { role: string }[] }) => u.roles.some((r) => ADMIN.includes(r.role));
type Org = { id: string; name: string; type: string };

export default function Users() {
  const { can, me } = useAuth();
  const [roles, setRoles] = useState<Role[]>([]);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [users, setUsers] = useState<U[]>([]);
  const [q, setQ] = useState("");
  const manage = (u: U) => can("iam:edit") && u.id !== me?.id && (!isAdminAcct(u) || !!me?.is_super_admin);
  const [tab, setTab] = useState<"users" | "roles">("users");
  const [inv, setInv] = useState({ full_name: "", email: "", phone: "", role: "", org_id: "" });
  const [assign, setAssign] = useState<{ user: U; role: string; org_id: string } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const load = useCallback(() => get<{ items: U[] }>(`/users?size=100&q=${encodeURIComponent(q)}`).then((d) => setUsers(d.items)).catch(setErr), [q]);
  useEffect(() => { get<Role[]>("/roles").then(setRoles).catch(setErr); get<Org[]>("/orgs").then(setOrgs).catch(() => {}); }, []);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  async function invite(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { await post("/users/invite", { ...inv, email: inv.email || null, phone: inv.phone || null, org_id: inv.org_id || null });
      toast("Invitation sent"); setInv({ full_name: "", email: "", phone: "", role: "", org_id: "" }); load(); }
    catch (x) { setErr(x); }
  }
  async function doAssign() {
    if (!assign) return; setErr(null);
    try { await post(`/users/${assign.user.id}/roles`, { role: assign.role, org_id: assign.org_id || null }); setAssign(null); toast("Role assigned"); load(); }
    catch (x) { setErr(x); }
  }
  async function revoke(u: U, r: URole) {
    if (!confirm(`Remove ${r.role_name} from ${u.full_name}?`)) return;
    try { await del(`/users/${u.id}/roles/${r.id}`); load(); } catch (x) { setErr(x); }
  }
  const orgSel = (v: string, on: (v: string) => void) => (
    <select value={v} onChange={(e) => on(e.target.value)}><option value="">National (no scope limit)</option>
      {orgs.filter((o) => ["county", "sub_county", "school", "school_cluster", "aggregation_centre", "warehouse", "programme"].includes(o.type))
        .map((o) => <option key={o.id} value={o.id}>{o.name} ({o.type.replace("_", " ")})</option>)}</select>);

  return (
    <>
      <PageHead crumb="Administration › Users & roles" title="Users & roles" sub="User → Role → Data scope → Permission" />
      <div className="tabs"><button className={`tab ${tab === "users" ? "on" : ""}`} onClick={() => setTab("users")}>Users</button>
        <button className={`tab ${tab === "roles" ? "on" : ""}`} onClick={() => setTab("roles")}>Roles & permissions</button></div>
      <ErrorBox error={err} />
      {tab === "users" && (<div className="grid" style={{ gridTemplateColumns: "2fr 1fr", alignItems: "start" }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}><input className="btn" style={{ fontWeight: 400 }} placeholder="Search users" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="tablewrap"><table><thead><tr><th>User</th><th>Roles & scope</th><th>Last sign-in</th><th>Status</th><th /></tr></thead>
            <tbody>{users.map((u) => (<tr key={u.id}>
              <td><b>{u.full_name}</b>{isAdminAcct(u) && <> <span className="adminbadge" style={{ fontSize: 10, padding: "1px 6px" }}>Admin account</span></>}<div className="small muted">{u.email ?? u.phone}</div></td>
              <td className="small">{u.roles.map((r) => <div key={r.id}>{r.role_name}{r.org_name ? ` · ${r.org_name}` : " · National"}
                {manage(u) && <button className="btn sm" style={{ padding: "0 6px", marginLeft: 6 }} aria-label="Remove role" onClick={() => revoke(u, r)}>×</button>}</div>)}</td>
              <td className="small">{fmtDateTime(u.last_login_at)}</td><td><Pill status={u.status} /></td>
              <td className="r">{manage(u) && <button className="btn sm" onClick={() => setAssign({ user: u, role: "", org_id: "" })}>+ Role</button>}</td></tr>))}</tbody></table></div>
        </div>
        <div className="stack">
          {assign && <div className="card"><h3>Add role to {assign.user.full_name}</h3>
            <Field label="Role"><select value={assign.role} onChange={(e) => setAssign({ ...assign, role: e.target.value })}><option value="">Choose…</option>
              {roles.filter((r) => (ADMIN.includes(r.key) ? me?.is_super_admin && isAdminAcct(assign.user) : !isAdminAcct(assign.user))).map((r) => <option key={r.key} value={r.key}>{r.name}{r.tier === "optional" ? " (optional)" : ""}</option>)}</select></Field>
            <Field label="Data scope" hint="Users only see records inside this area.">{orgSel(assign.org_id, (v) => setAssign({ ...assign, org_id: v }))}</Field>
            <div className="row"><button className="btn primary" disabled={!assign.role} onClick={doAssign}>Assign</button><button className="btn" onClick={() => setAssign(null)}>Cancel</button></div>
            <p className="small muted">Conflicting role pairs are blocked (segregation of duties). Administrator accounts hold administrator roles only.</p></div>}
          {can("iam:create") && <form className="card" onSubmit={invite}><h3>Invite staff or school user</h3>
            <Field label="Full name"><input value={inv.full_name} onChange={(e) => setInv({ ...inv, full_name: e.target.value })} /></Field>
            <Field label="Email"><input type="email" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} /></Field>
            <Field label="Mobile number"><input value={inv.phone} onChange={(e) => setInv({ ...inv, phone: e.target.value })} /></Field>
            <Field label="Role"><select value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}><option value="">Choose…</option>
              {roles.filter((r) => !["supplier", "farmer_group", "aggregator"].includes(r.key) && (!ADMIN.includes(r.key) || me?.is_super_admin)).map((r) => <option key={r.key} value={r.key}>{r.name}{ADMIN.includes(r.key) ? " (separate administrator account)" : ""}</option>)}</select></Field>
            <Field label="Data scope">{orgSel(inv.org_id, (v) => setInv({ ...inv, org_id: v }))}</Field>
            <button className="btn primary" disabled={!inv.full_name || !inv.role}>Send invitation</button></form>}
        </div></div>)}
      {tab === "roles" && (<div className="card"><div className="tablewrap"><table><thead><tr><th>Role</th><th>Tier</th><th>Default scope</th><th>2-step</th><th>Permissions</th></tr></thead>
        <tbody>{roles.map((r) => <tr key={r.key}><td><b>{r.name}</b></td><td>{r.tier}</td><td>{r.default_scope}</td><td>{r.requires_mfa ? "Required" : "—"}</td>
          <td className="small" style={{ maxWidth: 520 }}>{r.permissions.join(" · ")}</td></tr>)}</tbody></table></div></div>)}
      {node}
    </>
  );
}
