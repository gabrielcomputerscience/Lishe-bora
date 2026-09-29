import type { Metadata, Viewport } from "next";
import { PwaRegister } from "@/components/PwaRegister";
import "./globals.css";
import "@fortawesome/fontawesome-svg-core/styles.css";
import { config } from "@fortawesome/fontawesome-svg-core";
config.autoAddCss = false;   // CSS is imported above (no inline style injection)

export const metadata: Metadata = {
  title: { default: "LisheBora — School food e-Sourcing", template: "%s · LisheBora" },
  description: "LisheBora connects schools with qualified local suppliers for nutritious school meals. STEP School Feeding Project.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon-192.png", apple: "/icon-192.png" },
  appleWebApp: { capable: true, title: "LisheBora", statusBarStyle: "default" },
};
export const viewport: Viewport = { themeColor: "#3D5A27" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Aleo = AATF primary serif. Myriad Pro (secondary) is used when installed; Source Sans 3 is the open fallback. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link href="https://fonts.googleapis.com/css2?family=Aleo:wght@400;600;700&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet" />
      </head>
      <body suppressHydrationWarning>{children}<PwaRegister /></body>
    </html>
  );
}
