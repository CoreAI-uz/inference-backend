"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

const LOCALES: { code: string; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "ru", label: "RU" },
  { code: "uz", label: "UZ" },
];

export function LocaleSwitcher() {
  const locale = useLocale();
  const router = useRouter();
  const [, startTransition] = useTransition();

  function set(code: string) {
    document.cookie = `NEXT_LOCALE=${code};path=/;max-age=31536000;samesite=lax`;
    startTransition(() => router.refresh());
  }

  return (
    <div
      className="inline-flex items-center gap-1 rounded-full border border-line bg-elevated py-[3px] pl-[10px] pr-1"
      title="Language / Тил / Til"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="1.5" strokeLinecap="round" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18" />
        <path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z" />
      </svg>
      {LOCALES.map((l) => {
        const active = l.code === locale;
        return (
          <button
            key={l.code}
            onClick={() => set(l.code)}
            className="rounded-full px-3 py-[5px] text-xs transition-colors"
            style={{
              fontFamily: "var(--font-body)",
              letterSpacing: "0.03em",
              fontWeight: active ? 500 : 400,
              background: active ? "var(--brand-orange)" : "transparent",
              color: active ? "#fff" : "var(--fg-secondary)",
            }}
          >
            {l.label}
          </button>
        );
      })}
    </div>
  );
}
