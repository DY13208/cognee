import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "@/i18n/getMessages";
import { getRequestLocale } from "@/i18n/getRequestLocale";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// RuntimeConfigScript below reads COGNEE_BACKEND_URL at render time. Without
// this, the pages that Next can prerender would bake the value in at build
// time and ignore whatever the container was started with.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Cognee",
  description: "Build AI memory with knowledge graphs.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getRequestLocale();
  const messages = getMessages(locale);

  return (
    <html lang={locale} className="h-full" {...mantineHtmlProps}>
      <head>
        <RuntimeConfigScript />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased h-full`}
      >
        <QueryProvider>
          <NextIntlClientProvider locale={locale} messages={messages}>
            <MantineProvider theme={theme}>
              <Notifications position="top-right" zIndex={10001} />
              <OsPreferenceProvider>
                {children}
              </OsPreferenceProvider>
            </MantineProvider>
          </NextIntlClientProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
