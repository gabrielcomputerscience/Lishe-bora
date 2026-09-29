/** Default homepage animation (used until an administrator uploads a photo or video): a boy and a girl in school
 *  uniform enjoying a balanced school meal. Original illustration; pure SVG + CSS, loops like a short clip. */
const SKIN_B = "#7A4A2C", SKIN_G = "#8C5A37", HAIR = "#1E1712", SWEATER = "#507435", SWEATER_D = "#3C5829";

function Kid({ x, skin, girl }: { x: number; skin: string; girl?: boolean }) {
  return (
    <g>
      {/* body: sweater with white shirt V and collar */}
      <path d={`M${x - 72} 336 Q${x - 72} 262 ${x} 252 Q${x + 72} 262 ${x + 72} 336 Z`} fill={SWEATER} />
      <path d={`M${x - 72} 336 Q${x - 70} 300 ${x - 52} 280`} stroke={SWEATER_D} strokeWidth="3" fill="none" opacity=".5" />
      <rect x={x - 11} y={228} width="22" height="30" fill={skin} />
      <path d={`M${x - 19} 254 L${x + 19} 254 L${x} 292 Z`} fill="#fff" />
      <path d={`M${x - 19} 254 L${x} 266 L${x - 4} 276 Z M${x + 19} 254 L${x} 266 L${x + 4} 276 Z`} fill="#ECEFE8" />
      <path d={`M${x - 3} 266 L${x + 3} 266 L${x + 5} 292 L${x} 298 L${x - 5} 292 Z`} fill="#F9B916" />
      {/* head */}
      {girl && <><circle cx={x - 46} cy={150} r="25" fill={HAIR} /><circle cx={x + 46} cy={150} r="25" fill={HAIR} />
        <path d={`M${x - 58} 162 l12 -10 l4 16 Z M${x + 58} 162 l-12 -10 l-4 16 Z`} fill="#F9B916" /></>}
      <circle cx={x} cy={182} r="54" fill={HAIR} />
      <circle cx={x - 50} cy={202} r="10" fill={skin} /><circle cx={x + 50} cy={202} r="10" fill={skin} />
      <ellipse cx={x} cy={199} rx="49" ry="50" fill={skin} />
      {!girl && <path d={`M${x - 46} 180 Q${x} 140 ${x + 46} 180 Q${x + 30} 160 ${x} 158 Q${x - 30} 160 ${x - 46} 180 Z`} fill={HAIR} />}
      {girl && <path d={`M${x - 48} 186 Q${x - 20} 146 ${x + 10} 160 Q${x + 40} 150 ${x + 48} 186 Q${x + 30} 162 ${x} 166 Q${x - 30} 164 ${x - 48} 186 Z`} fill={HAIR} />}
      <g className="mk-blink" style={{ transformOrigin: `${x}px 196px` }}>
        <ellipse cx={x - 17} cy={196} rx="5.5" ry="7" fill="#1B120C" /><ellipse cx={x + 17} cy={196} rx="5.5" ry="7" fill="#1B120C" />
        <circle cx={x - 15} cy={193} r="1.8" fill="#fff" /><circle cx={x + 19} cy={193} r="1.8" fill="#fff" />
      </g>
      <path d={`M${x - 27} 182 q10 -7 20 -1 M${x + 7} 181 q10 -6 20 1`} stroke={HAIR} strokeWidth="3.5" fill="none" strokeLinecap="round" />
      <circle cx={x - 30} cy={214} r="8" fill="#E07A5F" opacity=".35" /><circle cx={x + 30} cy={214} r="8" fill="#E07A5F" opacity=".35" />
      <path d={`M${x - 17} 218 Q${x} 240 ${x + 17} 218 Z`} fill="#6B2320" />
      <path d={`M${x - 13} 219 Q${x} 224 ${x + 13} 219`} stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" />
    </g>
  );
}

function Plate({ x, rice }: { x: number; rice?: boolean }) {
  return (
    <g>
      <ellipse cx={x} cy={352} rx="78" ry="24" fill="#DCE7D2" />
      <ellipse cx={x} cy={347} rx="74" ry="21" fill="#fff" />
      <ellipse cx={x} cy={346} rx="56" ry="14" fill="#F4F6F0" />
      {rice
        ? <ellipse cx={x - 22} cy={340} rx="24" ry="10" fill="#FBF6E6" stroke="#EDE3C4" />
        : <path d={`M${x - 46} 346 Q${x - 44} 324 ${x - 24} 322 Q${x - 4} 324 ${x - 2} 346 Z`} fill="#F6EED3" stroke="#E4D8B0" />}
      {[[8, 340], [16, 336], [22, 342], [12, 345], [28, 338], [4, 335]].map(([dx, y], i) => (
        <ellipse key={i} cx={x + dx} cy={y} rx="5" ry="3.6" fill={i % 2 ? "#8A4B2A" : "#9E5B34"} />))}
      <path d={`M${x + 30} 350 q10 -16 24 -8 q-2 12 -24 8 Z M${x + 22} 352 q6 -14 20 -12 q-4 12 -20 12 Z`} fill="#75BA43" stroke="#507435" strokeWidth="1.5" />
      <path d={`M${x - 10} 356 q20 6 40 -2`} stroke="#F9B916" strokeWidth="7" strokeLinecap="round" fill="none" />
    </g>
  );
}

export function SchoolMealScene() {
  return (
    <svg className="meal-scene" viewBox="0 0 640 440" role="img" aria-label="Illustration: a boy and a girl in school uniform happily eating a balanced school meal">
      <rect width="640" height="440" fill="#F7F0E1" />
      <rect x="0" y="300" width="640" height="140" fill="#EFE4CC" />
      {/* chalkboard */}
      <rect x="90" y="14" width="460" height="88" rx="6" fill="#2F4520" /><rect x="90" y="100" width="460" height="6" fill="#AB822D" />
      <text x="112" y="48" fill="#F7F6F1" opacity=".9" fontFamily="Aleo, Georgia, serif" fontSize="22">A balanced plate</text>
      <g stroke="#F7F6F1" strokeWidth="2.5" fill="none" opacity=".75" strokeLinecap="round">
        <circle cx="130" cy="76" r="15" /><path d="M130 61 v30 M115 76 h30" />
        <path d="M170 84 q12 -22 26 -8 q-8 14 -26 8 Z" />
        <path d="M216 76 q10 -10 20 0 q-10 10 -20 0 Z" /><path d="M252 86 q14 -22 26 0" />
      </g>
      <g fontFamily="Source Sans 3, Arial, sans-serif" fontSize="13" fill="#F9B916" opacity=".95">
        <text x="380" y="46">grains · legumes</text><text x="380" y="66">vegetables · fruit</text><text x="380" y="86">milk · water</text>
      </g>
      {/* steam */}
      {[165, 205, 405, 445].map((sx, i) => (
        <path key={sx} className="mk-steam" style={{ animationDelay: `${i * 0.7}s` }}
              d={`M${sx} 318 q-8 -12 0 -24 q8 -12 0 -24`} stroke="#C9B98E" strokeWidth="3" fill="none" strokeLinecap="round" />))}
      <Kid x={200} skin={SKIN_B} />
      <Kid x={440} skin={SKIN_G} girl />
      {/* table */}
      <rect x="0" y="330" width="640" height="110" fill="#C39A4A" />
      <rect x="0" y="330" width="640" height="10" fill="#D4AE5E" />
      <Plate x={200} />
      <Plate x={440} rice />
      {/* cups of milk */}
      {[312, 552].map((cx) => (
        <g key={cx}><path d={`M${cx - 18} 300 L${cx + 18} 300 L${cx + 14} 352 L${cx - 14} 352 Z`} fill="#fff" stroke="#DCE7D2" strokeWidth="2" />
          <rect x={cx - 17} y="312" width="34" height="8" fill="#75BA43" opacity=".8" /></g>))}
      {/* the boy's spoon arm */}
      <g className="mk-arm-b" style={{ transformOrigin: "142px 292px" }}>
        <path d="M142 292 L178 234" stroke={SWEATER} strokeWidth="24" strokeLinecap="round" />
        <circle cx="180" cy="230" r="12" fill={SKIN_B} />
        <path d="M183 230 L200 214" stroke="#B8BFC4" strokeWidth="5" strokeLinecap="round" />
        <ellipse cx="203" cy="211" rx="8" ry="5" fill="#F6EED3" stroke="#B8BFC4" strokeWidth="2" transform="rotate(-40 203 211)" />
      </g>
      {/* the girl's banana arm */}
      <g className="mk-arm-g" style={{ transformOrigin: "498px 292px" }}>
        <path d="M498 292 L462 234" stroke={SWEATER} strokeWidth="24" strokeLinecap="round" />
        <circle cx="460" cy="230" r="12" fill={SKIN_G} />
        <path d="M452 232 q-4 -26 12 -40 q-2 18 4 36 Z" fill="#F9B916" stroke="#AB822D" strokeWidth="2" />
      </g>
      {/* the other hands resting on the table */}
      <circle cx="262" cy="338" r="12" fill={SKIN_B} /><circle cx="378" cy="338" r="12" fill={SKIN_G} />
    </svg>
  );
}
