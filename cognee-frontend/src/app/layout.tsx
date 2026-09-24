import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import "tailwindcss";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import { mantineHtmlProps, MantineProvider } from "@mantine/core";
import theme from "@/ui/theme/theme";
import { Notifications } from "@mantine/notifications";
import { OsPreferenceProvider } from "@/ui/layout/OsPreferenceContext";
import QueryProvider from "@/modules/query/QueryProvider";
import RuntimeConfigScript from "@/modules/config/RuntimeConfigScript";
import { BusinessLanguageProvider } from "@/modules/business/BusinessLanguageContext";

// Local Geist files (via the `geist` package) — no Google Fonts fetch at
// build time, so Docker builds work offline / behind a firewall.

// RuntimeConfigScript below reads COGNEE_BACKEND_URL at render time. Without
// this, the pages that Next can prerender would bake the value in at build
// time and ignore whatever the container was started with.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Cognee",
  description: "Build AI memory with knowledge graphs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" {...mantineHtmlProps}>
      <head>
        <RuntimeConfigScript />
      </head>
      <body
        className={`${GeistSans.variable} ${GeistMono.variable} antialiased h-full`}
      >
        <QueryProvider>
          <MantineProvider theme={theme}>
            <Notifications position="top-right" zIndex={10001} />
            <BusinessLanguageProvider>
              <OsPreferenceProvider>
                {children}
              </OsPreferenceProvider>
            </BusinessLanguageProvider>
          </MantineProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
