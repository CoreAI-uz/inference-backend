"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { ArcLogo, Wordmark } from "@/components/brand/Arc";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

type DeveloperSection = "console" | "docs";

type DeveloperHeaderProps = {
  active: DeveloperSection;
  email?: string;
};

const items: { section: DeveloperSection; href: string; label: "apiConsole" | "apiDocs" }[] = [
  { section: "console", href: "/console", label: "apiConsole" },
  { section: "docs", href: "/docs", label: "apiDocs" },
];

export function DeveloperHeader({ active, email }: DeveloperHeaderProps) {
  const t = useTranslations("developer");

  return (
    <header className="sticky top-0 z-30 border-b border-line-subtle bg-page/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1180px] items-center justify-between gap-4 px-5 lg:px-8">
        <div className="flex items-center gap-6">
          <a href="https://coreai.uz" className="flex items-center gap-2 text-fg-primary no-underline" aria-label={t("website")}>
            <ArcLogo size={35} />
            <Wordmark size={18} />
          </a>
          <nav className="hidden items-center gap-1 sm:flex" aria-label={t("developerNav")}>
            {items.map((item) =>
              item.section === active ? (
                <span key={item.section} aria-current="page" className="rounded-lg bg-elevated-2 px-3 py-2 text-sm text-fg-primary">
                  {t(item.label)}
                </span>
              ) : (
                <Link key={item.section} href={item.href} className="rounded-lg px-3 py-2 text-sm text-fg-secondary no-underline hover:bg-elevated hover:text-fg-primary">
                  {t(item.label)}
                </Link>
              ),
            )}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {email && <span className="hidden max-w-52 truncate text-xs text-fg-tertiary lg:block">{email}</span>}
          <Link href="/" className="hidden rounded-lg border border-line-default px-3 py-2 text-sm text-fg-secondary no-underline hover:bg-elevated hover:text-fg-primary sm:block">
            {t("openChat")}
          </Link>
          <ThemeToggle />
          <LocaleSwitcher />
        </div>
      </div>
    </header>
  );
}
