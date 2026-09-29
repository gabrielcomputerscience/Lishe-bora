import { publicGet } from "@/lib/server";
import { SchoolMealScene } from "./SchoolMealScene";

export type Bg = { url: string; overlay: number; position: string; kind: "image" | "video"; alt?: string; hidden?: boolean };
export type Bgs = Record<string, Bg>;

export const getBackgrounds = async () => (await publicGet<Bgs>("/backgrounds")) ?? {};

/** Inline style for a section with an admin-chosen background image. Dark sections get a green veil, light ones a cream veil,
 *  so text stays readable whatever the photo. */
export function bgStyle(b: Bg | undefined, dark: boolean): React.CSSProperties | undefined {
  if (!b || b.hidden || b.kind === "video") return undefined;
  const a = (b.overlay ?? 55) / 100;
  const veil = dark ? `rgba(47,69,32,${a})` : `rgba(247,246,241,${a})`;
  return { backgroundImage: `linear-gradient(${veil},${veil}),url(${b.url})`, backgroundSize: "cover", backgroundPosition: b.position || "center" };
}

/** A muted, looping background video behind a section or page banner, under the same readability veil as images. */
export function BgVideo({ b, dark }: { b?: Bg; dark: boolean }) {
  if (!b || b.hidden || b.kind !== "video") return null;
  const a = (b.overlay ?? 55) / 100;
  return (
    <div className="bgvid" aria-hidden="true">
      <video src={b.url} autoPlay muted loop playsInline preload="metadata" style={{ objectPosition: b.position || "center" }} />
      <div className="veil" style={{ background: dark ? `rgba(47,69,32,${a})` : `rgba(247,246,241,${a})` }} />
    </div>
  );
}

/** The picture beside the homepage headline: an uploaded video or photo, or the built-in animation. */
export function HeroMedia({ m }: { m?: Bg }) {
  if (m?.hidden) return null;     // administrator chose "None"
  return (
    <div className="hero-media">
      {m?.kind === "video" ? (
        <video src={m.url} autoPlay muted loop playsInline preload="metadata" aria-label={m.alt || "Pupils enjoying a school meal"} />
      ) : m ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={m.url} alt={m.alt || ""} style={{ objectPosition: m.position }} />
      ) : <SchoolMealScene />}
    </div>
  );
}
