// Self-hosted via next/font (downloaded at build, served from our origin — no runtime
// foreign CDN, satisfying the in-country requirement).
//
// Onest is the single brand typeface (display + body). It covers Latin AND Cyrillic in
// one design, so Uzbek/Russian text never mismatches the Latin beside it — the reason we
// moved off Hanken Grotesk, which has no Cyrillic. Onest stays close to Hanken's clean,
// modern grotesk feel. JetBrains Mono stays for data/code.
import { JetBrains_Mono, Onest } from "next/font/google";

export const fontSans = Onest({
  subsets: ["latin", "latin-ext", "cyrillic"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

export const fontMono = JetBrains_Mono({
  subsets: ["latin", "latin-ext", "cyrillic"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const fontVars = `${fontSans.variable} ${fontMono.variable}`;
