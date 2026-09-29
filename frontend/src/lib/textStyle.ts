// Text styles an editor can set on homepage text (Website content → Homepage). Kept in the block's data.styles
// and validated on the server (backend/app/api/v1/cms.py → clean_styles).
export type TextStyle = { color?: string; bg?: string; bold?: boolean; italic?: boolean; size?: number; font?: string };

// Brand fonts first (AATF manual: Aleo headings, Myriad/Source Sans body), then a few Google fonts.
export const FONTS: Record<string, { label: string; css: string; google?: string }> = {
  aleo: { label: "Aleo (brand headings)", css: "var(--serif)" },
  sans: { label: "Source Sans 3 (brand body)", css: "var(--sans)" },
  lato: { label: "Lato", css: "'Lato',sans-serif", google: "Lato:ital,wght@0,400;0,700;1,400;1,700" },
  montserrat: { label: "Montserrat", css: "'Montserrat',sans-serif", google: "Montserrat:ital,wght@0,400;0,700;0,800;1,400;1,700" },
  oswald: { label: "Oswald (condensed)", css: "'Oswald',sans-serif", google: "Oswald:wght@400;600;700" },
  merriweather: { label: "Merriweather", css: "'Merriweather',serif", google: "Merriweather:ital,wght@0,400;0,700;1,400;1,700" },
  poppins: { label: "Poppins", css: "'Poppins',sans-serif", google: "Poppins:ital,wght@0,400;0,600;0,700;1,400;1,700" },
};

// AATF Brand Manual palette (p.10) plus white and dark ink.
export const SWATCHES = [["#507435", "Green"], ["#2F4520", "Dark green"], ["#AB822D", "Gold"], ["#F9B916", "Amber"],
  ["#75BA43", "Leaf"], ["#912E91", "Purple"], ["#FFFFFF", "White"], ["#1E2A17", "Ink"]] as const;

export function styleOf(t?: TextStyle): React.CSSProperties | undefined {
  if (!t) return undefined;
  const s: React.CSSProperties = {};
  if (t.color) s.color = t.color;
  if (t.bg) { s.background = t.bg; s.borderColor = t.bg; }
  if (t.bold !== undefined) s.fontWeight = t.bold ? 700 : 400;
  if (t.italic !== undefined) s.fontStyle = t.italic ? "italic" : "normal";
  if (t.size) s.fontSize = `${t.size}px`;
  if (t.font && FONTS[t.font]) s.fontFamily = FONTS[t.font].css;
  return Object.keys(s).length ? s : undefined;
}

/** Google Fonts stylesheet for the non-brand fonts in use (brand fonts are already loaded by the layout). */
export function fontsHref(styles: Record<string, TextStyle | undefined>): string | null {
  const fams = Array.from(new Set(Object.values(styles).map((t) => t?.font).filter((f): f is string => !!f && !!FONTS[f]?.google)));
  return fams.length ? `https://fonts.googleapis.com/css2?${fams.map((f) => `family=${FONTS[f].google}`).join("&")}&display=swap` : null;
}
