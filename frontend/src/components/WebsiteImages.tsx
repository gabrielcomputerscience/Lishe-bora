"use client";
import { useCallback, useEffect, useState } from "react";
import { FlowButtons } from "@/components/CmsFlow";
import { ErrorBox, Field, Pill, useToast } from "@/components/ui";
import { api, del, get, post, put } from "@/lib/api";
import { fmtBytes } from "@/lib/format";

type Media = { id: string; title: string; alt: string; file_name: string; content_type: string; size_bytes: number };
type Slot = { key: string; label: string };
type Choice = { media_id: string; overlay: number; position: string; hidden?: boolean };
type Block = { key: string; data: Record<string, unknown>; status: string; version: number };
const url = (id: string) => `/api/v1/public/media/${id}`;
const isVideo = (m?: Media) => !!m && m.content_type.startsWith("video/");

/** Website content → Images & backgrounds: an image/video library, and a picker for every section and page. */
export function WebsiteImages({ block, can, onChanged }: { block?: Block; can: (p: string) => boolean; onChanged: () => Promise<void> }) {
  const [media, setMedia] = useState<Media[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [data, setData] = useState<Record<string, Choice>>({});
  const [up, setUp] = useState<{ file: File | null; title: string; alt: string }>({ file: null, title: "", alt: "" });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { toast, node } = useToast();
  const load = useCallback(() => { get<Media[]>("/cms/media").then(setMedia).catch(setErr); get<Slot[]>("/cms/backgrounds/slots").then(setSlots).catch(setErr); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setData((block?.data ?? {}) as Record<string, Choice>); }, [block]);
  const run = async (fn: () => Promise<unknown>, ok: string) => { setErr(null); setBusy(true); try { await fn(); toast(ok); load(); await onChanged(); } catch (e) { setErr(e); } finally { setBusy(false); } };
  async function upload(e: React.FormEvent) {
    e.preventDefault(); if (!up.file) return;
    const fd = new FormData(); fd.append("file", up.file); fd.append("title", up.title); fd.append("alt", up.alt);
    await run(() => api("/cms/media", { method: "POST", body: fd }), "Uploaded");
    setUp({ file: null, title: "", alt: "" });
  }
  const set = (k: string, v: Partial<Choice> | null) => setData((d) => {
    const n = { ...d };
    if (v === null) delete n[k]; else n[k] = { ...({ overlay: 55, position: "center", media_id: "" } as Choice), ...n[k], ...v };
    return n;
  });
  const save = () => run(() => put("/cms/blocks/backgrounds", { data }), "Draft saved");
  if (!block) return <div className="card muted">Run the seed to create the backgrounds block.</div>;
  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1.4fr", alignItems: "start" }}>
      <div className="stack">
        {can("cms:create") && <form className="card" onSubmit={upload}><h3>Upload an image or short video</h3>
          <Field label="File" hint="JPG, PNG or WebP photos; MP4 or WebM video (short, muted loop) for any section or page. Up to 30 MB. Use photos you have the rights to, with consent for any child shown.">
            <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" onChange={(e) => setUp({ ...up, file: e.target.files?.[0] ?? null })} /></Field>
          <Field label="Title"><input value={up.title} onChange={(e) => setUp({ ...up, title: e.target.value })} /></Field>
          <Field label="Description for screen readers" hint="e.g. Two pupils eating lunch at school"><input value={up.alt} onChange={(e) => setUp({ ...up, alt: e.target.value })} /></Field>
          <button className="btn primary" disabled={!up.file || busy}>Upload</button></form>}
        <div className="card"><h3>Library</h3>
          <div className="medgrid">{media.map((m) => (
            <div key={m.id} className="med">
              {isVideo(m) ? <video src={url(m.id)} muted playsInline preload="metadata" /> : /* eslint-disable-next-line @next/next/no-img-element */ <img src={url(m.id)} alt={m.alt} />}
              <div className="small"><b>{m.title}</b><div className="muted">{isVideo(m) ? "Video" : "Image"} · {fmtBytes(m.size_bytes)}</div></div>
              {can("cms:approve") && <button className="btn sm" onClick={() => { if (confirm(`Delete ${m.title}?`)) run(() => del(`/cms/media/${m.id}`), "Deleted"); }}>Delete</button>}
            </div>))}
            {!media.length && <p className="small muted">No images yet.</p>}</div></div>
      </div>
      <div className="card"><div className="row"><h3>Where images appear</h3><span className="spacer" /><Pill status={block.status} /></div>
        <p className="small muted">Pick an image for any section or page. The veil keeps text readable (higher = more colour over the photo). Save, then publish.</p>
        <ErrorBox error={err} />
        <div className="tablewrap"><table><tbody>{slots.map((s) => {
          const ch = data[s.key]; const m = media.find((x) => x.id === ch?.media_id);
          const hero = s.key === "home_hero_media";
          const value = ch?.hidden ? "__none__" : ch?.media_id ?? "";
          return (
            <tr key={s.key}><td style={{ width: 90 }}>{m ? (isVideo(m) ? <video className="thumb" src={url(m.id)} muted /> : /* eslint-disable-next-line @next/next/no-img-element */ <img className="thumb" src={url(m.id)} alt="" />) : <div className="thumb empty">{ch?.hidden ? "None" : hero ? "Animation" : "Colour"}</div>}</td>
              <td><b className="small">{s.label}</b>
                <select value={value} onChange={(e) => {
                  const v = e.target.value;
                  if (v === "__none__") setData((d) => ({ ...d, [s.key]: { media_id: "", overlay: 0, position: "center", hidden: true } }));
                  else set(s.key, v ? { media_id: v, hidden: false } : null);
                }} style={{ display: "block", width: "100%", marginTop: 4 }}>
                  <option value="">{hero ? "Built-in animation (pupils eating a balanced meal)" : "No image (brand colour)"}</option>
                  {hero && <option value="__none__">None: headline only, no picture or video</option>}
                  {media.map((x) => <option key={x.id} value={x.id}>{x.title}{isVideo(x) ? " (video)" : ""}</option>)}</select>
                {ch?.media_id && !hero && <div className="row small" style={{ marginTop: 6, gap: 10 }}>
                  <label>Veil {ch.overlay}% <input type="range" min={0} max={90} step={5} value={ch.overlay} onChange={(e) => set(s.key, { overlay: Number(e.target.value) })} /></label>
                  <label>Focus <select value={ch.position} onChange={(e) => set(s.key, { position: e.target.value })}>{["center", "top", "bottom", "left", "right"].map((p) => <option key={p}>{p}</option>)}</select></label></div>}
              </td></tr>);
        })}</tbody></table></div>
        <div className="row" style={{ marginTop: 10 }}><button className="btn" disabled={!can("cms:edit") || busy} onClick={save}>Save draft</button>
          <FlowButtons republish status={block.status} can={can} onAct={(a) => run(async () => { if (a !== "unpublish") await put("/cms/blocks/backgrounds", { data }); await post("/cms/blocks/backgrounds/workflow", { action: a }); }, `Backgrounds: ${a}`)} /></div>
        {node}
      </div>
    </div>
  );
}
