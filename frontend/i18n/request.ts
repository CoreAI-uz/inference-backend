// next-intl without URL routing: locale comes from the NEXT_LOCALE cookie, falling
// back to Accept-Language, then English. The LocaleSwitcher sets the cookie.
// Locale messages are deep-merged over English, so any key not yet translated
// falls back to the English string instead of erroring.
import type { AbstractIntlMessages } from "next-intl";
import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";

import en from "../messages/en.json";

export const LOCALES = ["en", "ru", "uz"] as const;
export const DEFAULT_LOCALE = "en";

type Dict = Record<string, unknown>;

function deepMerge(base: Dict, over: Dict): Dict {
  const out: Dict = { ...base };
  for (const [k, v] of Object.entries(over)) {
    const b = out[k];
    if (v && typeof v === "object" && !Array.isArray(v) && b && typeof b === "object" && !Array.isArray(b)) {
      out[k] = deepMerge(b as Dict, v as Dict);
    } else {
      out[k] = v;
    }
  }
  return out;
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  let locale = cookieStore.get("NEXT_LOCALE")?.value;

  if (!locale || !LOCALES.includes(locale as (typeof LOCALES)[number])) {
    const accept = (await headers()).get("accept-language")?.toLowerCase() ?? "";
    locale = LOCALES.find((l) => accept.includes(l)) ?? DEFAULT_LOCALE;
  }

  const messages =
    locale === "en"
      ? en
      : deepMerge(en as Dict, (await import(`../messages/${locale}.json`)).default as Dict);

  // next-intl's message type disallows arrays; we read arrays (e.g. chat.chips) via
  // t.raw(), so cast through unknown.
  return { locale, messages: messages as unknown as AbstractIntlMessages };
});
