/** Portal menu. Each account sees only the pages it needs: the server sends the list (role defaults, adjusted by the
 *  Super Administrator under Features & menus), and a page is also only shown when the account holds the permission
 *  behind it. The server still enforces every permission – this keeps menus short and relevant. */
import type { Me } from "./types";

type Can = (...p: string[]) => boolean;
export type MenuItem = { href: string; label: string; group: string; hint: string; show: (can: Can, hasSupplier: boolean) => boolean };

export const NAV: MenuItem[] = [
  { href: "/app", label: "Dashboard", group: "Overview", hint: "", show: () => true },
  { href: "/app/approvals", label: "My approvals", group: "Overview", hint: "Items waiting for you and what you submitted", show: () => true },
  { href: "/app/my-supplier", label: "My supplier profile", group: "Supplier", hint: "Your details, documents and payment details", show: (_c, s) => s },
  { href: "/app/demand", label: "School demand", group: "Plan", hint: "Food needs per school and term", show: (c) => c("dem:view") },
  { href: "/app/locations", label: "School locations", group: "Plan", hint: "GPS position of schools", show: (c, s) => c("md:edit", "inv:create", "agg:create", "log:approve") && !s },
  { href: "/app/menus", label: "Menus & terms", group: "Plan", hint: "Term menus and school calendar", show: (c, s) => c("dem:view", "md:view") && !s },
  { href: "/app/plans", label: "Procurement plans", group: "Plan", hint: "County plans built from approved demand", show: (c, s) => c("src:view", "bud:view", "dem:approve") && !s },
  { href: "/app/budgets", label: "Budgets", group: "Plan", hint: "Budget lines, commitments and spend", show: (c) => c("bud:view") },
  { href: "/app/opportunities", label: "Opportunities", group: "Supplier", hint: "Open tenders and your bids", show: (_c, s) => s },
  { href: "/app/orders", label: "My contracts & orders", group: "Supplier", hint: "Awards, contracts and purchase orders", show: (_c, s) => s },
  { href: "/app/suppliers", label: "Supplier registry", group: "Source", hint: "Applications, vetting and prequalification", show: (c, s) => c("sup:view") && !s },
  { href: "/app/sourcing", label: "Sourcing events", group: "Source", hint: "Tenders, bids, evaluation and awards", show: (c, s) => c("src:view") && !s },
  { href: "/app/evaluations", label: "My evaluations", group: "Source", hint: "Bids you are asked to score", show: (c) => c("eva:evaluate") },
  { href: "/app/contracts", label: "Contracts & POs", group: "Source", hint: "Contracts and purchase orders", show: (c, s) => c("con:view") && !s },
  { href: "/app/aggregation", label: "Aggregation & intake", group: "Fulfil", hint: "Farmer intake and batches", show: (c) => c("agg:create", "agg:submit") },
  { href: "/app/quality", label: "Quality inspection", group: "Fulfil", hint: "Batches waiting for inspection", show: (c) => c("agg:verify") },
  { href: "/app/inventory", label: "Inventory", group: "Fulfil", hint: "Stock, use, transfers and counts", show: (c) => c("inv:view") },
  { href: "/app/dispatch", label: "Dispatch", group: "Fulfil", hint: "Plan and send delivery trips", show: (c) => c("log:create") },
  { href: "/app/deliveries", label: "Deliveries", group: "Fulfil", hint: "Trips on the way and delivery confirmation", show: (c) => c("log:view") },
  { href: "/app/trace", label: "Traceability", group: "Fulfil", hint: "Follow a batch from farm to school; recalls", show: (c) => c("agg:view", "log:view", "meal:view") },
  { href: "/app/invoices", label: "Invoices & payments", group: "Performance & finance", hint: "Invoices, matching and payments", show: (c) => c("fin:view") },
  { href: "/app/complaints", label: "Complaints", group: "Performance & finance", hint: "Raise and follow up complaints", show: (c) => c("cmp:view", "cmp:create") },
  { href: "/app/performance", label: "Supplier performance", group: "Performance & finance", hint: "Supplier scorecards", show: (c) => c("sup:view", "cmp:view", "meal:view") },
  { href: "/app/integrations", label: "Payment integrations", group: "Performance & finance", hint: "Payment details, payment files, statements, IFMIS", show: (c, s) => c("fin:verify", "fin:pay", "fin:export") && !s },
  { href: "/app/insights", label: "Forecasts & prices", group: "Performance & finance", hint: "Stock outlook and price intelligence", show: (c, s) => c("inv:view", "meal:view") && !s },
  { href: "/app/map", label: "Programme map", group: "Performance & finance", hint: "Schools, stores and trips on the map", show: (c, s) => c("meal:view", "log:view", "rsk:view") && !s },
  { href: "/app/meal", label: "MEAL dashboard", group: "Performance & finance", hint: "Reach, sourcing and finance results", show: (c, s) => c("meal:view") && !s },
  { href: "/app/admin", label: "Admin console", group: "Administration", hint: "Overview for administrators", show: (c) => c("iam:edit", "cms:approve") },
  { href: "/app/readiness", label: "Pilot readiness", group: "Administration", hint: "What is still needed before go-live", show: (c) => c("iam:edit", "md:edit") },
  { href: "/app/users", label: "Users & roles", group: "Administration", hint: "Accounts and role assignments", show: (c) => c("iam:view") },
  { href: "/app/features", label: "Features & menus", group: "Administration", hint: "Choose which pages each role and person sees", show: (c) => c("iam:edit") },
  { href: "/app/master-data", label: "Master data", group: "Administration", hint: "Counties, schools and foods", show: (c) => c("md:edit") },
  { href: "/app/system", label: "System & onboarding", group: "Administration", hint: "Imports, messages and jobs", show: (c) => c("iam:edit", "md:edit") },
  { href: "/app/website", label: "Website content", group: "Administration", hint: "Pages, news and homepage", show: (c) => c("cms:view") },
  { href: "/app/exceptions", label: "Exceptions", group: "Oversight", hint: "Delivery, quality and payment cases", show: (c) => c("rsk:view") },
  { href: "/app/risk", label: "Risk dashboard", group: "Oversight", hint: "Risk flags and rules", show: (c, s) => c("rsk:view") && !s },
  { href: "/app/audit", label: "Audit trail", group: "Oversight", hint: "Who did what and when", show: (c) => c("aud:view") },
  { href: "/app/notifications", label: "Notifications", group: "Account", hint: "", show: () => true },
  { href: "/app/profile", label: "My profile & security", group: "Account", hint: "", show: () => true },
];

const ALWAYS = ["/app", "/app/notifications", "/app/profile"];

/** Menu items for this account: pages its roles need, which it also has permission for. */
export function menuFor(me: Me, can: Can): MenuItem[] {
  // me.menu comes from the server: the role defaults plus any pages the Super Administrator added or removed for this person
  const wanted = me.menu ? new Set([...ALWAYS, ...me.menu]) : null;
  const items = NAV.filter((i) => i.show(can, !!me.supplier_id) && (!wanted || wanted.has(i.href)));
  if (me.is_admin) {   // administration first
    return [...items.filter((i) => i.group === "Administration"), ...items.filter((i) => i.group !== "Administration" && i.href !== "/app")];
  }
  return items;
}

/** True when this list page is not part of the account's menu (detail pages under a menu page stay reachable). */
export function outsideMenu(path: string, items: MenuItem[]): boolean {
  const page = NAV.find((i) => !ALWAYS.includes(i.href) && i.href !== "/app/approvals" && (path === i.href || path === i.href + "/"));
  return !!page && !items.some((i) => i.href === page.href);
}

/** Hook-free helper for pages: is this list page part of the account's menu? Use it to hide links to pages the person
 *  does not use. */
export function inMenu(me: Me | null, can: Can, href: string): boolean {
  if (!me) return false;
  const base = "/" + href.split("?")[0].split("/").filter(Boolean).slice(0, 2).join("/");
  if (!NAV.some((i) => i.href === base) || ALWAYS.includes(base) || base === "/app/approvals") return true;
  return menuFor(me, can).some((i) => i.href === base);
}
