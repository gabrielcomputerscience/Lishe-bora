"use client";
import { useEffect, useState } from "react";
import { Field, ErrorBox } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";

export function ContactForm() {
  const [f, setF] = useState({ name: "", contact: "", topic: "general", message: "", website: "", county_id: "", category: "food_quality" });
  const [sent, setSent] = useState<string | null>(null);
  const [counties, setCounties] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => { get<{ id: string; name: string }[]>("/public/counties").then(setCounties).catch(() => {}); }, []);
  const [err, setErr] = useState<unknown>(null);
  const [fe, setFe] = useState<Record<string, string>>({});
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setFe({});
    try { const r = await post<{ message: string }>("/public/contact", { ...f, county_id: f.county_id || null }); setSent(r.message); }
    catch (x) { setErr(x); if (x instanceof ApiError) setFe(x.fieldErrors()); }
  }
  return (
    <>
    <section className="wrap sec narrow">
      {sent ? <div className="alert info" role="status">{sent}</div> : (
        <form className="card" onSubmit={submit} noValidate>
          <div className="grid g2">
            <Field label="Name" id="n" error={fe.name}><input id="n" value={f.name} onChange={set("name")} required /></Field>
            <Field label="Phone or email" id="c" error={fe.contact}><input id="c" value={f.contact} onChange={set("contact")} required /></Field>
          </div>
          <Field label="Topic" id="t"><select id="t" value={f.topic} onChange={set("topic")}>
            <option value="general">General question</option><option value="registration">Registration help</option>
            <option value="grievance">Complaint / grievance</option><option value="media">Media</option></select></Field>
          {f.topic === "grievance" && <div className="grid g2">
            <Field label="County" id="gc" hint="So the right county team follows up"><select id="gc" value={f.county_id} onChange={set("county_id")}>
              <option value="">Not sure</option>{counties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="What is it about?" id="gk"><select id="gk" value={f.category} onChange={set("category")}>
              <option value="food_quality">Food quality</option><option value="late_delivery">Late or missed delivery</option><option value="short_delivery">Short delivery</option>
              <option value="supplier_conduct">Supplier conduct</option><option value="staff_conduct">Staff conduct</option><option value="payment">Payment</option>
              <option value="procurement">Fairness of procurement</option><option value="safeguarding">Safeguarding of children</option><option value="fraud">Suspected fraud or corruption</option>
              <option value="other">Something else</option></select></Field>
          </div>}
          <Field label="Message" id="m" error={fe.message}><textarea id="m" rows={5} value={f.message} onChange={set("message")} required /></Field>
          <input className="sr-only" tabIndex={-1} autoComplete="off" aria-hidden="true" value={f.website} onChange={set("website")} />
          <ErrorBox error={err} />
          <button className="btn primary" type="submit">Send message</button>
        </form>)}
    </section></>
  );
}
