"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

export function ThemeToggle() {
  const t = useTranslations("common");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const t = (document.documentElement.getAttribute("data-theme") as "dark" | "light") || "dark";
    setTheme(t);
  }, []);

  function apply(t: "dark" | "light") {
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem("ca-theme", t);
    } catch {
      /* ignore */
    }
    setTheme(t);
  }

  const btn = (active: boolean) =>
    ({
      display: "inline-flex",
      padding: "6px",
      borderRadius: "999px",
      border: "none",
      cursor: "pointer",
      background: active ? "var(--bg-elevated-2)" : "transparent",
      color: active ? "var(--fg-primary)" : "var(--fg-tertiary)",
    }) as const;

  return (
    <div className="inline-flex items-center gap-[2px] rounded-full border border-line-subtle bg-elevated p-[3px]">
      <button onClick={() => apply("dark")} title={t("darkMode")} aria-label={t("darkMode")} style={btn(theme === "dark")}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      </button>
      <button onClick={() => apply("light")} title={t("lightMode")} aria-label={t("lightMode")} style={btn(theme === "light")}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" />
        </svg>
      </button>
    </div>
  );
}
