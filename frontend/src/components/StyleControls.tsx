"use client";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBold, faItalic, faRotateLeft } from "@fortawesome/free-solid-svg-icons";
import { FONTS, SWATCHES, styleOf, type TextStyle } from "@/lib/textStyle";

/** A small formatting bar for one piece of homepage text: colour, bold, italic, size and font, with a live preview. */
export function StyleControls({ value, onChange, preview, dark, defaultSize, button }: {
  value?: TextStyle; onChange: (v: TextStyle | undefined) => void; preview: string; dark?: boolean; defaultSize: number; button?: "gold" | "ghost";
}) {
  const v = value ?? {};
  const set = (p: Partial<TextStyle>) => onChange({ ...v, ...p });
  return (
    <div className="stylebar">
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        <button type="button" className={`btn sm ${v.bold ? "primary" : ""}`} aria-pressed={!!v.bold} title="Bold" onClick={() => set({ bold: !v.bold })}><FontAwesomeIcon icon={faBold} /></button>
        <button type="button" className={`btn sm ${v.italic ? "primary" : ""}`} aria-pressed={!!v.italic} title="Italic" onClick={() => set({ italic: !v.italic })}><FontAwesomeIcon icon={faItalic} /></button>
        <select aria-label="Font" value={v.font ?? ""} onChange={(e) => set({ font: e.target.value || undefined })}>
          <option value="">Default font</option>{Object.entries(FONTS).map(([k, f]) => <option key={k} value={k}>{f.label}</option>)}</select>
        <label className="small">Size <input type="number" min={10} max={96} placeholder={String(defaultSize)} value={v.size ?? ""} style={{ width: 64 }}
          onChange={(e) => set({ size: e.target.value ? Number(e.target.value) : undefined })} /> px</label>
        <span className="swatches" role="group" aria-label="Colour">
          {SWATCHES.map(([c, n]) => <button type="button" key={c} title={n} aria-label={n} className={`sw ${v.color === c ? "on" : ""}`} style={{ background: c }} onClick={() => set({ color: c })} />)}
          <input type="color" aria-label="Custom colour" value={v.color ?? "#507435"} onChange={(e) => set({ color: e.target.value.toUpperCase() })} />
        </span>
        <button type="button" className="btn sm" title="Reset to default" onClick={() => onChange(undefined)}><FontAwesomeIcon icon={faRotateLeft} /></button>
      </div>
      {button && <div className="row small" style={{ gap: 6, marginTop: 6 }}><span className="muted">Button colour</span>
        <span className="swatches" role="group" aria-label="Button colour">
          {SWATCHES.map(([c, n]) => <button type="button" key={c} title={n} aria-label={`Button ${n}`} className={`sw ${v.bg === c ? "on" : ""}`} style={{ background: c }} onClick={() => set({ bg: c })} />)}
          <input type="color" aria-label="Custom button colour" value={v.bg ?? "#AB822D"} onChange={(e) => set({ bg: e.target.value.toUpperCase() })} />
          {v.bg && <button type="button" className="btn sm" onClick={() => set({ bg: undefined })}>No fill</button>}</span></div>}
      {button ? <div className="stylepreview dark"><span className={`btn lg ${button}`} style={{ fontSize: defaultSize, ...styleOf(v) }}>{preview || "Button"}</span></div>
        : <div className={`stylepreview ${dark ? "dark" : ""}`} style={{ fontSize: defaultSize, ...styleOf(v) }}>{preview || "Preview"}</div>}
    </div>
  );
}
