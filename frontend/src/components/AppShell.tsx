"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Logo, Vein } from "./Brand";

type Item = { href: string; label: string; group: string; show: (can: (...p: string[]) => boolean, hasSupplier: boolean) => boolean };
const NAV: Item[] = [
  { href: "/app", label: "Dashboard", group: "Overview", show: () => true },
  { href: "/app/approvals", label: "My approvals", group: "Overview", show: () => true },
  { href: "/app/my-supplier", label: "My supplier profile", group: "Supplier", show: (_c, s) => s },
  { href: "/app/demand", label: "School demand", group: "Plan", show: (c) => c("dem:view") },
  { href: "/app/locations", label: "School locations", group: "Plan", show: (c, s) => c("md:edit", "inv:create", "agg:create", "log:approve") && !s },
  { href: "/app/menus", label: "Menus & terms", group: "Plan", show: (c, s) => c("dem:view", "md:view") && !s },
  { href: "/app/plans", label: "Procurement plans", group: "Plan", show: (c, s) => c("src:view", "bud:view", "dem:approve") && !s },
  { href: "/app/budgets", label: "Budgets", group: "Plan", show: (c) => c("bud:view") },
  { href: "/app/opportunities", label: "Opportunities", group: "Supplier", show: (_c, s) => s },
  { href: "/app/orders", label: "My contracts & orders", group: "Supplier", show: (_c, s) => s },
  { href: "/app/suppliers", label: "Supplier registry", group: "Source", show: (c, s) => c("sup:view") && !s },
  { href: "/app/sourcing", label: "Sourcing events", group: "Source", show: (c, s) => c("src:view") && !s },
  { href: "/app/evaluations", label: "My evaluations", group: "Source", show: (c) => c("eva:evaluate") },
  { href: "/app/contracts", label: "Contracts & POs", group: "Source", show: (c, s) => c("con:view") && !s },
  { href: "/app/aggregation", label: "Aggregation & intake", group: "Fulfil", show: (c) => c("agg:create", "agg:submit") },
  { href: "/app/quality", label: "Quality inspection", group: "Fulfil", show: (c) => c("agg:verify") },
  { href: "/app/inventory", label: "Inventory", group: "Fulfil", show: (c) => c("inv:view") },
  { href: "/app/dispatch", label: "Dispatch", group: "Fulfil", show: (c) => c("log:create") },
  { href: "/app/deliveries", label: "Deliveries", group: "Fulfil", show: (c) => c("log:view") },
  { href: "/app/trace", label: "Traceability", group: "Fulfil", show: (c) => c("agg:view", "log:view", "meal:view") },
  { href: "/app/invoices", label: "Invoices & payments", group: "Performance & finance", show: (c) => c("fin:view") },
  { href: "/app/complaints", label: "Complaints", group: "Performance & finance", show: (c) => c("cmp:view", "cmp:create") },
  { href: "/app/performance", label: "Supplier performance", group: "Performance & finance", show: (c) => c("sup:view", "cmp:view", "meal:view") },
  { href: "/app/integrations", label: "Payment integrations", group: "Performance & finance", show: (c, s) => c("fin:verify", "fin:pay", "fin:export") && !s },
  { href: "/app/insights", label: "Forecasts & prices", group: "Performance & finance", show: (c, s) => c("inv:view", "meal:view") && !s },
  { href: "/app/map", label: "Programme map", group: "Performance & finance", show: (c, s) => c("meal:view", "log:view", "rsk:view") && !s },
  { href: "/app/meal", label: "MEAL dashboard", group: "Performance & finance", show: (c, s) => c("meal:view") && !s },
  { href: "/app/admin", label: "Admin console", group: "Administration", show: (c) => c("iam:edit", "cms:approve") },
  { href: "/app/readiness", label: "Pilot readiness", group: "Administration", show: (c) => c("iam:edit", "md:edit") },
  { href: "/app/users", label: "Users & roles", group: "Administration", show: (c) => c("iam:view") },
  { href: "/app/master-data", label: "Master data", group: "Administration", show: (c) => c("md:edit") },
  { href: "/app/system", label: "System & onboarding", group: "Administration", show: (c) => c("iam:edit", "md:edit") },
  { href: "/app/website", label: "Website content", group: "Administration", show: (c) => c("cms:view") },
  { href: "/app/exceptions", label: "Exceptions", group: "Oversight", show: (c) => c("rsk:view") },
  { href: "/app/risk", label: "Risk dashboard", group: "Oversight", show: (c, s) => c("rsk:view") && !s },
  { href: "/app/audit", label: "Audit trail", group: "Oversight", show: (c) => c("aud:view") },
  { href: "/app/notifications", label: "Notifications", group: "Account", show: () => true },
  { href: "/app/profile", label: "My profile & security", group: "Account", show: () => true },
];

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

  let items = NAV.filter((i) => i.show(can, !!me.supplier_id));
  if (me.is_admin) {   // administrator accounts: administration first, operational pages are read-only views
    items = [...items.filter((i) => i.group === "Administration"), ...items.filter((i) => i.group !== "Administration" && i.href !== "/app" && i.href !== "/app/approvals")];
  }
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
        <main className="main" id="main">{children}</main>
      </div>
    </>
  );
}
