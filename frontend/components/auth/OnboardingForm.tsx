"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError } from "@/lib/api/client";
import { completeOnboarding, skipOnboarding } from "@/lib/api/resources";
import type { IntendedUseCode, RoleCode } from "@/lib/api/types";

const ROLES: RoleCode[] = [
  "software_developer",
  "ml_data_specialist",
  "researcher",
  "student",
  "educator",
  "business_owner_founder",
  "product_business",
  "marketing_content",
  "government_public_sector",
  "other",
];

const USES: IntendedUseCode[] = [
  "general_assistant",
  "writing_translation",
  "programming",
  "data_analysis",
  "research_education",
  "api_application",
  "business_workflows",
  "model_evaluation",
  "other",
];

const WORK_ROLES = new Set<RoleCode>([
  "software_developer",
  "ml_data_specialist",
  "researcher",
  "educator",
  "business_owner_founder",
  "product_business",
  "marketing_content",
  "government_public_sector",
]);

export function OnboardingForm({ next = "/" }: { next?: string }) {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const [role, setRole] = useState<RoleCode | "">("");
  const [intendedUses, setIntendedUses] = useState<IntendedUseCode[]>([]);
  const [organizationName, setOrganizationName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showOrganization =
    (role !== "" && WORK_ROLES.has(role)) ||
    intendedUses.includes("api_application") ||
    intendedUses.includes("business_workflows");

  function toggleUse(value: IntendedUseCode) {
    setIntendedUses((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!role || intendedUses.length === 0) {
      setError(t("selectRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await completeOnboarding(
        role,
        intendedUses,
        showOrganization ? organizationName.trim() || null : null,
      );
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError && err.message ? err.message : t("errorGeneric"));
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setBusy(true);
    setError(null);
    try {
      await skipOnboarding();
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError && err.message ? err.message : t("errorGeneric"));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-[720px] px-6 py-12 sm:py-16">
      <div className="mb-9">
        <p className="mb-2 text-[12px] uppercase tracking-[0.12em] text-orange">{t("eyebrow")}</p>
        <h1 className="m-0 text-[38px] leading-tight tracking-[-0.02em] sm:text-[44px]" style={{ fontFamily: "var(--font-display)", fontWeight: 400 }}>
          {t("title")}
        </h1>
        <p className="mb-0 mt-3 max-w-[560px] text-[15px] leading-relaxed text-fg-secondary">{t("subtitle")}</p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-8">
        <fieldset className="m-0 border-0 p-0">
          <legend className="mb-3 text-[14px] font-medium text-fg-primary">{t("roleQuestion")}</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {ROLES.map((value) => (
              <label key={value} className={`cursor-pointer rounded-xl border px-4 py-3 text-[14px] transition-colors ${role === value ? "border-orange bg-orange/10 text-fg-primary" : "border-line bg-inset text-fg-secondary hover:border-line-strong"}`}>
                <input type="radio" name="role" value={value} checked={role === value} onChange={() => setRole(value)} className="sr-only" />
                {t(`roles.${value}`)}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="m-0 border-0 p-0">
          <legend className="mb-1 text-[14px] font-medium text-fg-primary">{t("usesQuestion")}</legend>
          <p className="mb-3 mt-0 text-[13px] text-fg-tertiary">{t("usesHint")}</p>
          <div className="flex flex-wrap gap-2">
            {USES.map((value) => {
              const selected = intendedUses.includes(value);
              return (
                <label key={value} className={`cursor-pointer rounded-full border px-4 py-2 text-[13px] transition-colors ${selected ? "border-orange bg-orange/10 text-fg-primary" : "border-line bg-inset text-fg-secondary hover:border-line-strong"}`}>
                  <input type="checkbox" value={value} checked={selected} onChange={() => toggleUse(value)} className="sr-only" />
                  {t(`uses.${value}`)}
                </label>
              );
            })}
          </div>
        </fieldset>

        {showOrganization && (
          <label className="flex flex-col gap-[6px]">
            <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("organization")}</span>
            <input type="text" maxLength={160} value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder={t("organizationPh")} autoComplete="organization" className="rounded-[12px] border border-line bg-inset px-4 py-3 text-[15px] text-fg-primary outline-none focus:border-orange" />
          </label>
        )}

        {error && <div role="alert" className="text-[13.5px]" style={{ color: "var(--status-info)" }}>{error}</div>}

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" disabled={busy} onClick={skip} className="rounded-full border border-line bg-transparent px-6 py-3 text-[14px] text-fg-secondary disabled:opacity-50">
            {t("skip")}
          </button>
          <button type="submit" disabled={busy || !role || intendedUses.length === 0} className="rounded-full border-0 bg-orange px-7 py-3 text-[14px] font-medium text-white disabled:opacity-50">
            {busy ? "…" : t("continue")}
          </button>
        </div>
      </form>
    </main>
  );
}
