"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { ArcLogo, Wordmark } from "@/components/brand/Arc";
import { LocaleSwitcher } from "@/components/ui/LocaleSwitcher";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

export function ProductHeader() {
  const t = useTranslations("developer");

  return (
    <header className="border-b border-line-subtle bg-page/95">
      <div className="mx-auto flex h-16 max-w-[1180px] items-center justify-between gap-4 px-5 lg:px-8">
        <Link href="/" className="flex items-center gap-2 text-fg-primary no-underline" aria-label="CoreAI Chat">
          <ArcLogo size={35} />
          <Wordmark size={18} />
        </Link>
        <div className="flex items-center gap-2">
          <Link href="/docs" className="hidden rounded-lg px-3 py-2 text-sm text-fg-secondary no-underline hover:bg-elevated hover:text-fg-primary sm:block">
            {t("apiDocs")}
          </Link>
          <ThemeToggle />
          <div className="hidden md:block"><LocaleSwitcher /></div>
        </div>
      </div>
    </header>
  );
}
