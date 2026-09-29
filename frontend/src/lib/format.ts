export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleDateString("en-KE", { day: "2-digit", month: "short", year: "numeric", timeZone: "Africa/Nairobi" }) : "—";
export const fmtDateTime = (s?: string | null) =>
  s ? new Date(s).toLocaleString("en-KE", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Nairobi" }) : "—";
export const fmtBytes = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);
export const human = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const PILL: Record<string, string> = {
  draft: "p-grey", submitted: "p-gold", under_review: "p-purple", in_review: "p-gold", approved: "p-green",
  prequalified: "p-green", active: "p-green", published: "p-green", open: "p-green", verified: "p-green",
  uploaded: "p-grey", suspended: "p-amber", expired: "p-amber", rejected: "p-red", archived: "p-grey",
  closed: "p-grey", awarded: "p-gold", pending_verification: "p-amber", deactivated: "p-grey",
  awaiting_inspection: "p-gold", cleared: "p-green", depleted: "p-grey", accepted: "p-green", partially_accepted: "p-amber", downgraded: "p-amber",
  planned: "p-grey", dispatched: "p-gold", in_transit: "p-purple", delivered: "p-green", cancelled: "p-grey", posted: "p-green",
  pending_approval: "p-amber", in_progress: "p-gold", resolved: "p-green", high: "p-red", medium: "p-amber", low: "p-grey",
  partially_paid: "p-amber", paid: "p-green", returned: "p-amber", investigating: "p-gold", matched: "p-green", variance: "p-red",
  issued: "p-gold", acknowledged: "p-green", partially_fulfilled: "p-amber", fulfilled: "p-green",
};
export const pillClass = (status: string) => PILL[status] ?? "p-grey";
