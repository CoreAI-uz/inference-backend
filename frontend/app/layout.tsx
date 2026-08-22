import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import { GoogleAdsTag } from "@/components/analytics/GoogleAdsTag";
import { fontVars } from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "CoreAI Chat",
  description: "Chat with open models and build with the CoreAI inference API.",
  icons: { icon: "/favicon.svg" },
};

// Set the saved theme before first paint to avoid a flash. Defaults to dark.
const themeInit = `(function(){try{var t=localStorage.getItem('ca-theme');if(t){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} data-theme="dark" className={fontVars} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
        <GoogleAdsTag />
      </body>
    </html>
  );
}
