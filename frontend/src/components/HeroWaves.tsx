/** Moving wave band along the bottom of banners, in the AATF brand colours (Brand Manual p.10). On inner pages a "balanced
 *  plate" parade travels along the waves: a few fish together with foods from every group (grains, legumes, vegetables,
 *  fruits, roots, eggs and milk), bobbing and doing the odd somersault. The homepage has the food showcase instead, so it
 *  shows no parade. Pure SVG + CSS; everything stops for reduced motion. */
function wave(width: number, height: number, base: number, amp: number, length: number) {
  let d = `M0 ${base}`;
  for (let x = 0; x < width * 2; x += length) d += ` Q ${x + length / 4} ${base - amp} ${x + length / 2} ${base} T ${x + length} ${base}`;
  return `${d} L ${width * 2} ${height} L 0 ${height} Z`;
}
const W = 1440, H = 120;
const BACK = [
  { color: "#75BA43", base: 40, amp: 14, len: 360, dur: 18, rev: false, op: 0.55 },   // leaf green
  { color: "#AB822D", base: 58, amp: 12, len: 300, dur: 13, rev: true, op: 0.7 },     // gold
  { color: "#F9B916", base: 76, amp: 10, len: 320, dur: 16, rev: false, op: 0.85 },   // amber
];
const FRONT = { color: "var(--bg)", base: 92, amp: 10, len: 280, dur: 11, rev: true, op: 1 };

// Real fish photo (public/fish, cut from the programme's food photo) in several colours. The tail is a separate image
// so it can flap. c = colour variant, w = width in px, swim = seconds to cross, jump = somersault rhythm, b = depth.
const FISH = [
  { c: "silver", w: 92, swim: 34, delay: 0, jump: 6.2, b: 22, left: false },
  { c: "red", w: 60, swim: 30, delay: -18, jump: 4.8, b: 34, left: true },
  { c: "gold", w: 76, swim: 36, delay: -9, jump: 6.8, b: 26, left: false },
  { c: "purple", w: 66, swim: 32, delay: -25, jump: 5.6, b: 30, left: true },
];
// Foods from each group of a balanced school meal (cut-out photos in public/foods), spaced along the same waves.
// h = height in px, flip = somersault rhythm (s). All travel left-to-right at a calm pace, offset by delay.
const FOODS = [
  { n: "maize-flour", alt: "Maize flour", h: 40, swim: 34, delay: -3, flip: 9, b: 30 },
  { n: "beans", alt: "Beans", h: 38, swim: 34, delay: -6.4, flip: 11, b: 28 },
  { n: "sukuma-wiki", alt: "Sukuma wiki", h: 44, swim: 34, delay: -10, flip: 8, b: 26 },
  { n: "carrots", alt: "Carrots", h: 36, swim: 34, delay: -13.5, flip: 10, b: 32 },
  { n: "bananas", alt: "Bananas", h: 42, swim: 34, delay: -17, flip: 12, b: 28 },
  { n: "eggs", alt: "Eggs", h: 40, swim: 34, delay: -20.5, flip: 9.5, b: 30 },
  { n: "milk", alt: "Milk", h: 46, swim: 34, delay: -24, flip: 13, b: 26 },
  { n: "sweet-potatoes", alt: "Sweet potatoes", h: 36, swim: 34, delay: -27.5, flip: 10.5, b: 30 },
  { n: "mangoes", alt: "Mangoes", h: 38, swim: 34, delay: -31, flip: 8.5, b: 28 },
];

function Layer({ l }: { l: typeof FRONT }) {
  return <path d={wave(W, H, l.base, l.amp, l.len)} style={{ fill: l.color, animationDuration: `${l.dur}s` }} opacity={l.op}
               className={`dm-wave ${l.rev ? "rev" : ""}`} />;
}

function Fish({ c }: { c: string }) {
  return (
    <span className="fish-art" aria-hidden="true">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="fish-body" src={`/fish/${c}-body.webp`} alt="" />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="fish-tail2" src={`/fish/${c}-tail.webp`} alt="" />
    </span>
  );
}

export type ShowcaseScene = { label: string; items: string; images: { src: string; alt: string }[] };

/** Food showcase for the homepage: each food category rises out of the water, zooms towards the viewer in 3D, then
 *  sinks back and the next one follows. CSS only; the timing is set by --i (scene number) and --n (number of scenes). */
function Showcase({ scenes }: { scenes: ShowcaseScene[] }) {
  return (
    <div className="showcase" style={{ ["--n" as string]: scenes.length } as React.CSSProperties} aria-label="Foods on school menus">
      {scenes.map((sc, i) => (
        <div key={sc.label} className="sc-scene" style={{ ["--i" as string]: i } as React.CSSProperties}>
          <div className="sc-items">{sc.images.map((im, k) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={im.src} src={im.src} alt={im.alt} className="sc-img" loading="lazy"
                 style={{ ["--k" as string]: k, ["--m" as string]: sc.images.length } as React.CSSProperties} />))}</div>
          <div className="sc-label"><b>{sc.label}</b><span>{sc.items}</span></div>
          <span className="sc-splash" aria-hidden="true" />
        </div>))}
    </div>
  );
}

export function HeroWaveBand({ showcase, parade = true }: { showcase?: ShowcaseScene[]; parade?: boolean } = {}) {
  return (
    <div className="hero-band" aria-hidden="true">
      <svg className="band-layer" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">{BACK.map((l, i) => <Layer key={i} l={l} />)}</svg>
      {!!showcase?.length && <Showcase scenes={showcase} />}
      {parade && <div className="fishes">
        {FOODS.map((f, i) => (
          <div key={f.n} className="fish-swim food-swim" style={{ bottom: f.b, animationDuration: `${f.swim}s`, animationDelay: `${f.delay}s` } as React.CSSProperties}>
            <div className="food-bob" style={{ animationDelay: `${-i * 0.7}s` } as React.CSSProperties}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="food-flip" src={`/foods/${f.n}.webp`} alt="" loading="lazy"
                   style={{ height: f.h, animationDuration: `${f.flip}s`, animationDelay: `${-i * 1.3}s` } as React.CSSProperties} />
            </div>
          </div>))}
        {FISH.map((f, i) => (
          <div key={i} className={`fish-swim ${f.left ? "left" : ""}`}
               style={{ bottom: f.b, animationDuration: `${f.swim}s`, animationDelay: `${f.delay}s` } as React.CSSProperties}>
            <div className="fish-jump" style={{ width: f.w, height: f.w * 0.256, animationDuration: `${f.jump}s`, animationDelay: `${-i * 1.1}s`,
                                                ["--flap" as string]: `${0.26 + (110 - f.w) / 450}s` } as React.CSSProperties}>
              <Fish c={f.c} />
            </div>
          </div>))}
      </div>}
      <svg className="band-layer" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"><Layer l={FRONT} /></svg>
    </div>
  );
}
