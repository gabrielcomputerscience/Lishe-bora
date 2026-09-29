"use client";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { del, get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";

type Sess = { id: string; user_agent: string; ip: string; created_at: string; last_used_at: string; current: boolean };
export default function Profile() {
  const { me, reload } = useAuth();
  const [name, setName] = useState(me?.full_name ?? "");
  const [lang, setLang] = useState(me?.preferred_language ?? "en");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const { toast, node } = useToast();
  const loadS = useCallback(() => get<Sess[]>("/auth/sessions").then(setSessions).catch(() => {}), []);
  useEffect(() => { loadS(); }, [loadS]);
  if (!me) return null;
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); try { await fn(); toast(ok); } catch (e) { setErr(e); } };
  return (
    <>
      <PageHead crumb="Account" title="My profile & security" sub={me.email ?? me.phone ?? ""} />
      <ErrorBox error={err} />
      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card"><h3>Profile</h3>
          <Field label="Full name"><input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Preferred language"><select value={lang} onChange={(e) => setLang(e.target.value)}><option value="en">English</option><option value="sw">Kiswahili</option></select></Field>
          <button className="btn primary" onClick={() => run(async () => { await patch("/auth/me", { full_name: name, preferred_language: lang }); await reload(); }, "Profile updated")}>Save</button>
          <p className="small muted" style={{ marginTop: 14 }}>Two-step verification: <b>{me.mfa_enabled ? "On (SMS)" : "Off"}</b>{me.mfa_enabled ? " — required for your role." : ""}</p></div>
        <div className="card"><h3>Change password</h3>
          <Field label="Current password"><input type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
          <Field label="New password" hint="At least 10 characters, with upper- and lower-case letters and a number."><input type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
          <button className="btn primary" onClick={() => run(async () => { await post("/auth/password/change", pw); setPw({ current_password: "", new_password: "" }); }, "Password changed")}>Change password</button></div>
      </div>
      <div className="card" style={{ marginTop: 16 }}><h3>Where you are signed in</h3>
        <div className="tablewrap"><table><thead><tr><th>Device</th><th>IP</th><th>Last active</th><th /></tr></thead>
          <tbody>{sessions.map((s) => <tr key={s.id}><td className="small">{s.user_agent.slice(0, 80) || "Unknown device"}{s.current && <b> · this device</b>}</td><td className="small">{s.ip}</td>
            <td className="small">{fmtDateTime(s.last_used_at)}</td><td className="r">{!s.current && <button className="btn sm danger" onClick={() => run(async () => { await del(`/auth/sessions/${s.id}`); await loadS(); }, "Signed out that device")}>Sign out</button>}</td></tr>)}</tbody></table></div></div>
      {node}
    </>
  );
}
