"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "@/lib/api/client";
import { login as apiLogin, register as apiRegister } from "@/lib/api/resources";
import { trackSignupConversion } from "@/lib/google-ads";
import { authPath } from "@/lib/navigation";

import { GoogleSignInButton } from "./GoogleSignInButton";

export function AuthForm({ mode, next = "/" }: { mode: "login" | "register"; next?: string }) {
  const t = useTranslations("auth");
  const locale = useLocale();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [legalTermsAccepted, setLegalTermsAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (mode === "register" && !legalTermsAccepted) return;
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await apiRegister(displayName, email, password, locale, legalTermsAccepted);
        trackSignupConversion();
        const onboardingPath = next === "/" ? "/onboarding" : `/onboarding?next=${encodeURIComponent(next)}`;
        router.push(onboardingPath);
      } else {
        await apiLogin(email, password);
        router.push(next);
      }
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "email_taken") setError(t("errorTaken"));
        else if (err.status === 401) setError(t("errorInvalid"));
        else setError(err.message || t("errorGeneric"));
      } else {
        setError(t("errorGeneric"));
      }
    } finally {
      setBusy(false);
    }
  }

  const isRegister = mode === "register";
  const legalBase = `https://coreai.uz${locale === "ru" ? "" : `/${locale}`}`;

  return (
    <div className="mx-auto w-full max-w-[420px] px-6 py-16">
      <h1 className="m-0 mb-2" style={{ fontFamily: "var(--font-display)", fontWeight: 400, fontSize: 38, lineHeight: 1.1, letterSpacing: "-0.01em" }}>
        {isRegister ? t("registerTitle") : t("loginTitle")}
      </h1>
      <p className="mb-8 mt-0 text-[15px] leading-relaxed text-fg-secondary">{isRegister ? t("registerSub") : t("loginSub")}</p>

      <GoogleSignInButton next={next} />

      <form onSubmit={submit} className="flex flex-col gap-4">
        {isRegister && (
          <label className="flex flex-col gap-[6px]">
            <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("displayName")}</span>
            <input type="text" required maxLength={80} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={t("displayNamePh")} autoComplete="name" className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-primary outline-none focus:border-orange" />
          </label>
        )}

        <label className="flex flex-col gap-[6px]">
          <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("email")}</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("emailPh")} autoComplete="email" className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-primary outline-none focus:border-orange" />
        </label>

        <label className="flex flex-col gap-[6px]">
          <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("password")}</span>
          <input type="password" required minLength={isRegister ? 8 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("passwordPh")} autoComplete={isRegister ? "new-password" : "current-password"} className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-primary outline-none focus:border-orange" />
        </label>

        {isRegister && (
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line-subtle bg-inset px-4 py-3">
            <input
              type="checkbox"
              required
              checked={legalTermsAccepted}
              onChange={(event) => setLegalTermsAccepted(event.target.checked)}
              className="mt-0.5 h-4 w-4 accent-orange"
            />
            <span className="text-[12.5px] leading-relaxed text-fg-secondary">
              {t("legalPrefix")} <a href={`${legalBase}/terms/`} className="text-orange-hi">{t("terms")}</a> {t("legalJoin")} <a href={`${legalBase}/privacy/`} className="text-orange-hi">{t("privacy")}</a>.
            </span>
          </label>
        )}

        {error && <div className="text-[13.5px]" style={{ color: "var(--status-info)" }}>{error}</div>}

        <button type="submit" disabled={busy || (isRegister && !legalTermsAccepted)} className="mt-2 inline-flex items-center justify-center rounded-full border-none px-6 py-[13px] text-[15px] font-medium text-white disabled:opacity-60" style={{ background: "var(--brand-orange)", cursor: busy ? "default" : "pointer" }}>
          {busy ? "…" : isRegister ? t("register") : t("login")}
        </button>
      </form>

      <div className="mt-6 text-[14px] text-fg-tertiary">
        {isRegister ? (
          <>{t("haveAccount")} <Link href={authPath("/login", next)} className="text-orange-hi">{t("loginLink")}</Link></>
        ) : (
          <>{t("noAccount")} <Link href={authPath("/register", next)} className="text-orange-hi">{t("signUpLink")}</Link></>
        )}
      </div>
      <div className="mt-2 text-[14px] text-fg-tertiary">
        {t("orTryFirst")} — <Link href="/" className="text-orange-hi">{t("guestChat")}</Link>
      </div>

      <p className="mt-10 text-[12.5px] leading-relaxed text-fg-quaternary">{t("privacyNote")}</p>
    </div>
  );
}
