"use client";
// Offline capture queue for field work (intake, inspection, proof of delivery).
// Every queued record carries a client_ref generated on the device; the server stores it once, so re-sending is safe.
import { useCallback, useEffect, useState } from "react";
import { ApiError, post } from "./api";

export type QItem = { id: string; path: string; body: Record<string, unknown>; label: string; at: string; error?: string };
const KEY = "lb_offline_queue_v1";
const EVT = "lb-queue";

export const newRef = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export function readQueue(): QItem[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]") as QItem[]; } catch { return []; }
}
function writeQueue(q: QItem[]) {
  try { localStorage.setItem(KEY, JSON.stringify(q)); } catch { /* storage full or blocked */ }
  window.dispatchEvent(new Event(EVT));
}
export function enqueue(path: string, body: Record<string, unknown>, label: string) {
  writeQueue([...readQueue(), { id: newRef(), path, body: { ...body, captured_offline: true }, label, at: new Date().toISOString() }]);
}
export function dropQueued(id: string) { writeQueue(readQueue().filter((q) => q.id !== id)); }

const isNetworkError = (e: unknown) => !(e instanceof ApiError) || e.status >= 500;
// The server already has this record (e.g. the school confirmed on another device): treat as synced, not as a failure.
const ALREADY_DONE = new Set(["ALREADY_CONFIRMED", "ALREADY_RECALLED"]);

/** Send now if possible; if the device is offline (or the network drops mid-request) keep it in the queue. */
export async function submitOrQueue<T>(path: string, body: Record<string, unknown>, label: string): Promise<{ queued: boolean; data?: T }> {
  if (typeof navigator !== "undefined" && !navigator.onLine) { enqueue(path, body, label); return { queued: true }; }
  try { return { queued: false, data: await post<T>(path, body) }; }
  catch (e) { if (isNetworkError(e)) { enqueue(path, body, label); return { queued: true }; } throw e; }
}

let flushing = false;
export async function flushQueue(): Promise<{ sent: number; failed: number }> {
  if (flushing) return { sent: 0, failed: 0 };
  flushing = true;
  let sent = 0, failed = 0;
  try {
    const q = readQueue();
    const keep: QItem[] = [];
    for (let i = 0; i < q.length; i++) {
      const it = q[i];
      try { await post(it.path, it.body); sent++; }
      catch (e) {
        failed++;
        if (isNetworkError(e)) { keep.push(...q.slice(i)); break; }       // still offline: stop, keep the rest
        if (e instanceof ApiError && ALREADY_DONE.has(e.code)) { failed--; sent++; continue; }
        keep.push({ ...it, error: e instanceof Error ? e.message : String(e) });   // rejected by server: keep for review
      }
    }
    writeQueue(keep);
  } finally { flushing = false; }
  return { sent, failed };
}

export function useOfflineQueue(onSynced?: () => void) {
  const [online, setOnline] = useState(true);
  const [items, setItems] = useState<QItem[]>([]);
  const refresh = useCallback(() => setItems(readQueue()), []);
  const sync = useCallback(async () => { const r = await flushQueue(); refresh(); if (r.sent) onSynced?.(); return r; }, [refresh, onSynced]);
  useEffect(() => {
    setOnline(navigator.onLine); refresh();
    const on = () => { setOnline(true); sync(); };
    const off = () => setOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off); window.addEventListener(EVT, refresh);
    if (navigator.onLine && readQueue().length) sync();
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); window.removeEventListener(EVT, refresh); };
  }, [refresh, sync]);
  return { online, items, sync };
}
