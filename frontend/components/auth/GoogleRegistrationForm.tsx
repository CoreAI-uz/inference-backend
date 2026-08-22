"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  completeGoogleRegistration,
  getPendingGoogleRegistration,
} from "@/lib/api/resources";
import { trackSignupConversion } from "@/lib/google-ads";
import { authPath } from "@/lib/navigation";

export function GoogleRegistrationForm({ next = "/" }: { next?: string }) {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [legalTermsAccepted, setLegalTermsAccepted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getPendingGoogleRegistration()
      .then((pending) => {
        setEmail(pending.email);
        setDisplayName(pending.display_name);
      })
      .catch(() => setExpired(true))
      .finally(() => setLoading(false));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!legalTermsAccepted) return;
    setBusy(true);
    setError(null);
    try {
      await completeGoogleRegistration(
        displayName,
        locale,
        legalTermsAccepted,
      );
      trackSignupConversion();
      const onboardingPath =
        next === "/" ? "/onboarding" : `/onboarding?next=${encodeURIComponent(next)}`;
      router.push(onboardingPath);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.code === "pending_registration_expired") {
        setExpired(true);
      } else if (err instanceof ApiError && err.code === "account_link_required") {
        setError(t("googleExistingAccount"));
      } else {
        setError(t("errorGeneric"));
      }
      setBusy(false);
    }
  }

  const legalBase = `https://coreai.uz${locale === "ru" ? "" : `/${locale}`}`;

  if (loading) {
    return <main className="mx-auto w-full max-w-[420px] px-6 py-16 text-fg-tertiary">{t("googleLoading")}</main>;
  }

  if (expired) {
    return (
      <main className="mx-auto w-full max-w-[420px] px-6 py-16">
        <h1 className="m-0 mb-3 text-[38px] leading-tight" style={{ fontFamily: "var(--font-display)", fontWeight: 400 }}>{t("googleExpiredTitle")}</h1>
        <p className="mb-6 mt-0 text-[15px] leading-relaxed text-fg-secondary">{t("googleExpiredBody")}</p>
        <Link href={authPath("/register", next)} className="inline-flex rounded-full bg-orange px-6 py-3 text-[14px] font-medium text-white no-underline">{t("googleStartAgain")}</Link>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-[420px] px-6 py-16">
      <h1 className="m-0 mb-2 text-[38px] leading-tight" style={{ fontFamily: "var(--font-display)", fontWeight: 400 }}>{t("googleCompleteTitle")}</h1>
      <p className="mb-8 mt-0 text-[15px] leading-relaxed text-fg-secondary">{t("googleCompleteSub")}</p>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-[6px]">
          <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("displayName")}</span>
          <input type="text" required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-primary outline-none focus:border-orange" />
        </label>

        <label className="flex flex-col gap-[6px]">
          <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("email")}</span>
          <input type="email" readOnly value={email} className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-tertiary outline-none" />
        </label>

        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line-subtle bg-inset px-4 py-3">
          <input type="checkbox" required checked={legalTermsAccepted} onChange={(event) => setLegalTermsAccepted(event.target.checked)} className="mt-0.5 h-4 w-4 accent-orange" />
          <span className="text-[12.5px] leading-relaxed text-fg-secondary">
            {t("legalPrefix")} <a href={`${legalBase}/terms/`} className="text-orange-hi">{t("terms")}</a> {t("legalJoin")} <a href={`${legalBase}/privacy/`} className="text-orange-hi">{t("privacy")}</a>.
          </span>
        </label>

        {error && <div role="alert" className="text-[13.5px]" style={{ color: "var(--status-info)" }}>{error}</div>}

        <button type="submit" disabled={busy || !legalTermsAccepted || !displayName.trim()} className="mt-2 rounded-full border-0 bg-orange px-6 py-[13px] text-[15px] font-medium text-white disabled:opacity-60">
          {busy ? "…" : t("googleCreateAccount")}
        </button>
      </form>
    </main>
  );
}
