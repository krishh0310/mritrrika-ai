import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Noto_Serif_Devanagari } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

/**
 * Three faces, three jobs (see globals.css for the reasoning).
 *
 * Noto Serif Devanagari is loaded for the Devanagari subset specifically: the
 * records are in that script, and letting it fall back to whatever the OS
 * offers puts owner names in a different weight and baseline from the Latin
 * beside them.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const notoDevanagari = Noto_Serif_Devanagari({
  subsets: ["devanagari", "latin"],
  weight: ["400", "500", "600"],
  variable: "--font-noto-devanagari",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Mrittika AI",
    template: "%s · Mrittika AI",
  },
  description:
    "Intelligent digitization for India's land records. All data in this deployment is synthetic demo data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${notoDevanagari.variable} ${jetbrains.variable}`}
    >
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-navy-800 focus:px-4 focus:py-2 focus:text-sm focus:text-white"
        >
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
