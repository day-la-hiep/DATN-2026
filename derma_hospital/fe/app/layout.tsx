import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
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
