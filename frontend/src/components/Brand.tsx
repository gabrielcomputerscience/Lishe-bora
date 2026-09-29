/* AATF logo (unaltered, from the Brand Manual) and the leaf-vein/circuit visual element (Brand Manual p.11). */
export function Logo({ tagline = false, className = "logo" }: { tagline?: boolean; className?: string }) {
  // Brand rule: below 55 mm the tagline is dropped — use tagline only at large sizes.
  // eslint-disable-next-line @next/next/no-img-element
  return <img className={className} src={tagline ? "/brand/aatf-logo-tagline.png" : "/brand/aatf-logo.png"}
              alt={tagline ? "AATF — Prosperity through technology" : "AATF"} />;
}

export function Vein({ stroke = "#AB822D", width = 10, className = "vein" }: { stroke?: string; width?: number; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 400 520" preserveAspectRatio="xMaxYMid slice" fill="none" stroke={stroke}
         strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M200 520V120" /><path d="M200 380 110 290V200" /><path d="M200 300 290 210V140" />
      <path d="M200 220 140 160V90" /><path d="M200 440 300 340V280" /><path d="M200 160 245 115V70" />
      <circle cx="110" cy="188" r="12" /><circle cx="290" cy="128" r="12" /><circle cx="140" cy="78" r="12" />
      <circle cx="300" cy="268" r="12" /><circle cx="245" cy="58" r="12" /><circle cx="200" cy="108" r="12" />
    </svg>
  );
}
