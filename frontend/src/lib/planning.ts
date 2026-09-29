export type Flag = { code: string; severity: "error" | "warning"; message: string };
export type DLine = { commodity: string; name: string; unit: string; grams_per_learner_cycle: number; gross_qty: number; stock_qty: number;
  net_qty: number; override_qty: number | null; override_reason: string; final_qty: number };
export type Demand = {
  id: string; reference: string; school_id: string; school: string; term_id: string; term: string; menu_id: string | null; menu: string | null;
  enrolment: number; attendance_pct: number; feeding_days: number; wastage_pct: number; storage_capacity_kg: number | null;
  preferred_delivery: string; notes: string; status: string; flags: Flag[]; total_kg: number; updated_at: string; plan_id: string | null;
  nutrition?: { group_count: number; minimum: number; meets_minimum: boolean; missing_groups: string[]; food_groups: Record<string, number> };
  lines?: DLine[]; workflow?: import("@/components/Workflow").WF | null; history?: import("@/components/Workflow").WF["history"];
};
export const kg = (n: number | string | null | undefined, unit = "kg") =>
  n == null ? "—" : `${Number(n).toLocaleString("en-KE", { maximumFractionDigits: 1 })} ${unit}`;
export const ksh = (n: number | string | null | undefined) =>
  n == null ? "—" : `KSh ${Number(n).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
