"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Logo, Vein } from "./Brand";
import { menuFor, outsideMenu } from "@/lib/menu";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, loading, can, signOut } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!me) return;
    const f = () => get<{ unread: number }>("/notifications").then((d) => setUnread(d.unread)).catch(() => {});
    f(); const t = setInterval(f, 60000); return () => clearInterval(t);
  }, [me, path]);
  useEffect(() => {
    if (!loading && !me) router.replace(`${path.startsWith("/app/admin") ? "/admin/sign-in" : "/sign-in"}?next=${encodeURIComponent(path)}`);
  }, [loading, me, router, path]);
  useEffect(() => setOpen(false), [path]);
  if (loading || !me) return <div className="wrap sec muted">Loading…</div>;

  const items = menuFor(me, can);
  const hidden = outsideMenu(path, items);
  const initials = me.full_name.split(" ").filter((w) => /^[A-Za-z]/.test(w)).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const primary = me.roles[0];
  let grp = "";
  return (
    <>
      <header className="top">
        <button className="iconbtn menu-toggle" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        <Link href={me.is_admin ? "/app/admin" : "/app"}><Logo /></Link>
        <div className="product"><b>LisheBora</b><span>School food e-Sourcing Platform</span></div>
        {me.is_admin && <span className="adminbadge">{me.is_super_admin ? "Super administrator" : "Administrator"}</span>}
        <span className="spacer" />
        <Link className="btn sm" href="/">Website</Link>
        <Link className="iconbtn" href="/app/notifications" aria-label={`Notifications, ${unread} unread`} style={{ position: "relative", textDecoration: "none" }}>
          🔔{unread > 0 && <span style={{ position: "absolute", top: -4, right: -4, background: "var(--amber)", color: "var(--green-900)", borderRadius: 10, fontSize: 11, fontWeight: 700, padding: "0 6px" }}>{unread}</span>}
        </Link>
        <div className="avatar" title={me.full_name}>{initials}</div>
        <button className="btn sm" onClick={async () => { await signOut(); window.location.assign(me.is_admin ? "/admin/sign-in" : "/"); }}>Sign out</button>
      </header>
      <div className="shell">
        <nav className={`side ${open ? "open" : ""}`} aria-label="Portal">
          {items.map((i) => {
            const head = i.group !== grp ? <div className="grp">{(grp = i.group)}</div> : null;
            const active = i.href === "/app" ? path === "/app" : path.startsWith(i.href);
            return <div key={i.href}>{head}<Link className="nav" href={i.href} aria-current={active ? "page" : undefined}>{i.label}</Link></div>;
          })}
          <div className="grp" style={{ marginTop: 18 }}>Signed in</div>
          <div style={{ padding: "0 12px", fontSize: 13, lineHeight: 1.4, position: "relative", zIndex: 1 }}>
            <b style={{ color: "#fff" }}>{me.full_name}</b><br />
            {me.roles.map((r) => <span key={r.role + r.org_id} style={{ color: "#C9D6BE", display: "block" }}>{r.role_name}{r.org_name ? ` · ${r.org_name}` : ""}</span>)}
            {!primary && <span style={{ color: "#C9D6BE" }}>No role assigned</span>}
          </div>
          <Vein stroke="#F9B916" width={9} />
        </nav>
        <main className="main" id="main">{hidden ? (
          <div className="card" style={{ maxWidth: 560 }}><h2>Not part of your account</h2>
            <p className="muted">This page is not used in your role, so it is not in your menu. If you need it for your work, ask the administrator to add the right role to your account.</p>
            <Link className="btn" href={me.is_admin ? "/app/admin" : "/app"}>Back to my dashboard</Link></div>) : children}</main>
      </div>
    </>
  );
}
