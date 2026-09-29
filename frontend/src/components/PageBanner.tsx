import { BgVideo, bgStyle, getBackgrounds } from "./Backgrounds";
import { HeroWaveBand } from "./HeroWaves";

/** Page header used across the public website: brand gradient (or an admin-chosen photo) and the moving wave band. */
export async function PageBanner({ slot, eyebrow, title, sub, children }: { slot?: string; eyebrow?: string; title: string; sub?: string; children?: React.ReactNode }) {
  const bgs = slot ? await getBackgrounds() : {};
  return (
    <section className="hero pbanner hasbg" style={bgStyle(slot ? bgs[slot] : undefined, true)}>
      <BgVideo b={slot ? bgs[slot] : undefined} dark />
      <div className="wrap hero-in">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
        {children}
      </div>
      <HeroWaveBand />
    </section>
  );
}
