import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space", display: "swap" });

export const metadata: Metadata = {
  title: "Jubidate AI — Multi-Agent Strategic Intelligence Platform",
  description: "A futuristic multi-agent AI debate and strategic reasoning platform. Watch AI agents argue, train your argumentation skills, and analyze deep analytics.",
  icons: { icon: "/favicon.svg" }
};

const themeScript = `(function(){try{var t=localStorage.getItem("jubidate-theme")||"Dark";if(t==="Light")document.documentElement.classList.add("light");else if(t==="System"&&!window.matchMedia("(prefers-color-scheme:dark)").matches)document.documentElement.classList.add("light")}catch(e){}})()`; 

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} ${spaceGrotesk.variable}`}>{children}</body>
    </html>
  );
}
