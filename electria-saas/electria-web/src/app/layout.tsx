import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: {
    default: "ELECTRIA - Inteligencia Artificial para el Mercado Eléctrico",
    template: "%s | ELECTRIA",
  },
  description:
    "Toda la inteligencia del mercado eléctrico chileno, al alcance de cualquier empresa. Chat IA, dashboards, alertas y más.",
  keywords: [
    "mercado eléctrico",
    "Chile",
    "inteligencia artificial",
    "costos marginales",
    "energía",
    "SEN",
    "normativa eléctrica",
  ],
  authors: [{ name: "ELECTRIA" }],
  openGraph: {
    type: "website",
    locale: "es_CL",
    url: "https://electria.cl",
    siteName: "ELECTRIA",
    title: "ELECTRIA - Inteligencia Artificial para el Mercado Eléctrico",
    description:
      "Toda la inteligencia del mercado eléctrico chileno, al alcance de cualquier empresa.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "ELECTRIA",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ELECTRIA - IA para el Mercado Eléctrico",
    description:
      "Toda la inteligencia del mercado eléctrico chileno, al alcance de cualquier empresa.",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
