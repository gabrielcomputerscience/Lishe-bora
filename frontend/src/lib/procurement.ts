import type { WF } from "@/components/Workflow";
export type Lot = { id: string; lot_no: number; name: string; commodity_code: string; commodity: string; category: string; unit: string;
  quantity: number; specification: string; delivery_window: string; schools: { name: string; qty: string }[] };
export type Criterion = { key: string; label: string; max: number; auto: boolean };
export type ResultBid = { bid_id: string; supplier: string; unit_price: string; quantity: string; value: string; responsive: boolean; issues: string[];
  technical: Record<string, number>; technical_total: number; financial: number; total: number; rank: number | null };
export type Results = { lots: { lot_id: string; lot_no: number; name: string; quantity: string; unit: string; bids: ResultBid[]; recommended: string | null }[];
  evaluators: string[]; recommended_total: string; unawarded_lots: number[] };
export type Event = {
  id: string; reference: string; title: string; method: string; county: string | null; plan_id: string | null; description: string; eligibility: string;
  categories: string[]; closes_at: string; clarification_deadline: string | null; status: string; is_public: boolean; technical_weight: number;
  financial_weight: number; criteria: Criterion[]; required_docs: string[]; contract_start: string | null; contract_end: string | null;
  estimated_value?: number | null; opened_at: string | null; bids_received: number; lots: Lot[]; awarded_to: string; awarded_value: number | null;
  results?: Results | null; workflow?: WF | null; history?: WF["history"]; lot_count?: number;
};
export function countdown(iso: string, now = Date.now()) {
  const ms = new Date(iso).getTime() - now;
  if (ms <= 0) return "closed";
  const d = Math.floor(ms / 864e5), h = Math.floor((ms % 864e5) / 36e5), m = Math.floor((ms % 36e5) / 6e4);
  return d ? `${d}d ${h}h left` : h ? `${h}h ${m}m left` : `${m}m left`;
}
export const toLocalInput = (iso: string) => { const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
