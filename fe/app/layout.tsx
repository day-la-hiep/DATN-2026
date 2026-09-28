import type { Metadata } from "next";
import { Calistoga, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const calistoga = Calistoga({
  variable: "--font-calistoga",
  weight: "400",
  subsets: ["latin"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin", "vietnamese"],
});

export const metadata: Metadata = {
  title: "Trợ lý Da liễu AI | Derma AI",
  description: "Hệ thống Trợ lý Tư vấn và Chăm sóc Da liễu AI",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      suppressHydrationWarning
      className={`${inter.variable} ${calistoga.variable} ${mono.variable} h-full antialiased font-sans`}
    >
      <head>
        {/* chống FOUC: gắn data-theme (brand) trước khi paint */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var b=localStorage.getItem("derma-ai-brand");if(b==="emerald"||b==="violet"||b==="red"){document.documentElement.dataset.theme=b}}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
