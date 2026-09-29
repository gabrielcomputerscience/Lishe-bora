"use client";
import { useEffect, useRef, useState } from "react";

type Detector = { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> };
declare global { interface Window { BarcodeDetector?: new (o: { formats: string[] }) => Detector } }

/** Scans a batch QR label with the phone camera (where the browser supports it) and returns the batch code. */
export function QrScan({ onCode }: { onCode: (code: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [on, setOn] = useState(false);
  const [msg, setMsg] = useState("");
  const supported = typeof window !== "undefined" && !!window.BarcodeDetector && !!navigator.mediaDevices?.getUserMedia;
  useEffect(() => {
    if (!on) return;
    let stream: MediaStream | null = null, stop = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (!video.current) return;
        video.current.srcObject = stream; await video.current.play();
        const det = new window.BarcodeDetector!({ formats: ["qr_code", "code_128"] });
        while (!stop) {
          const found = await det.detect(video.current).catch(() => []);
          const raw = found[0]?.rawValue;
          const m = raw?.match(/BATCH-\d{4}-\d{6}/i);
          if (m) { onCode(m[0].toUpperCase()); setOn(false); break; }
          await new Promise((r) => setTimeout(r, 250));
        }
      } catch { setMsg("Camera not available. Type the code instead."); setOn(false); }
    })();
    return () => { stop = true; stream?.getTracks().forEach((t) => t.stop()); };
  }, [on, onCode]);
  if (!supported) return <p className="small muted">Scanning needs a phone browser with camera support; you can type the code printed under the QR label.</p>;
  return (
    <div>
      {on ? <><video ref={video} muted playsInline style={{ width: "100%", maxWidth: 360, borderRadius: 8, background: "#000" }} />
        <div><button type="button" className="btn sm" onClick={() => setOn(false)}>Stop camera</button></div></>
        : <button type="button" className="btn" onClick={() => { setMsg(""); setOn(true); }}>Scan QR label</button>}
      {msg && <p className="small muted">{msg}</p>}
    </div>
  );
}
