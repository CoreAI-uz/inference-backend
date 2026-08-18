"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { ApiError } from "@/lib/api/client";
import {
  getAuthMethods,
  getProfile,
  unlinkGoogleIdentity,
  updateProfile,
} from "@/lib/api/resources";
import type {
  AuthMethods,
  IntendedUseCode,
  RoleCode,
} from "@/lib/api/types";

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

export function AccountSettings() {
  const t = useTranslations("account");
  const onboarding = useTranslations("onboarding");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<RoleCode | "">("");
  const [intendedUses, setIntendedUses] = useState<IntendedUseCode[]>([]);
  const [organizationName, setOrganizationName] = useState("");
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);
  const [saving, setSaving] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshMethods = useCallback(async () => {
    setMethods(await getAuthMethods());
  }, []);

  useEffect(() => {
    void Promise.all([getProfile(), getAuthMethods()])
      .then(([profile, authMethods]) => {
        setDisplayName(profile.display_name ?? "");
        setRole(profile.role ?? "");
        setIntendedUses(profile.intended_uses);
        setOrganizationName(profile.organization_name ?? "");
        setMethods(authMethods);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) setUnauthorized(true);
        else setError(t("errorGeneric"));
      })
      .finally(() => setLoading(false));
  }, [t]);

  function toggleUse(value: IntendedUseCode) {
    setIntendedUses((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const answers = role && intendedUses.length > 0
        ? {
            role,
            intended_uses: intendedUses,
            organization_name: organizationName.trim() || null,
          }
        : {};
      await updateProfile({ display_name: displayName, ...answers });
      setNotice(t("saved"));
    } catch {
      setError(t("errorGeneric"));
    } finally {
      setSaving(false);
    }
  }

  async function disconnectGoogle() {
    setDisconnecting(true);
    setError(null);
    setNotice(null);
    try {
      await unlinkGoogleIdentity();
      await refreshMethods();
      setNotice(t("googleDisconnected"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "last_sign_in_method") {
        setError(t("lastMethod"));
      } else {
        setError(t("errorGeneric"));
      }
    } finally {
      setDisconnecting(false);
    }
  }

  if (loading) return <main className="mx-auto max-w-[900px] px-6 py-14 text-fg-tertiary">{t("loading")}</main>;

  if (unauthorized) {
    return (
      <main className="mx-auto max-w-[900px] px-6 py-14">
        <h1 className="m-0 mb-3 text-[40px]" style={{ fontFamily: "var(--font-display)", fontWeight: 400 }}>{t("loginTitle")}</h1>
        <Link href="/login?next=%2Faccount" className="text-orange-hi">{t("login")}</Link>
      </main>
    );
  }

  const googleIdentity = methods?.identities.find((identity) => identity.provider === "google");

  return (
    <main className="mx-auto w-full max-w-[900px] px-6 py-12 sm:py-16">
      <div className="mb-10">
        <p className="mb-2 text-[12px] uppercase tracking-[0.12em] text-orange">{t("eyebrow")}</p>
        <h1 className="m-0 text-[42px] leading-tight" style={{ fontFamily: "var(--font-display)", fontWeight: 400 }}>{t("title")}</h1>
      </div>

      <form onSubmit={save} className="rounded-2xl border border-line bg-elevated p-5 sm:p-7">
        <h2 className="m-0 mb-5 text-[22px] font-medium">{t("profileTitle")}</h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <label className="flex flex-col gap-2">
            <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{t("displayName")}</span>
            <input required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="rounded-xl border border-line bg-inset px-4 py-3 outline-none focus:border-orange" />
          </label>
          <label className="flex flex-col gap-2">
            <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{onboarding("roleQuestion")}</span>
            <select value={role} onChange={(event) => setRole(event.target.value as RoleCode | "")} className="rounded-xl border border-line bg-inset px-4 py-3 outline-none focus:border-orange">
              <option value="">{t("selectRole")}</option>
              {ROLES.map((value) => <option key={value} value={value}>{onboarding(`roles.${value}`)}</option>)}
            </select>
          </label>
        </div>

        <fieldset className="mt-6 border-0 p-0">
          <legend className="mb-3 text-[14px] font-medium">{onboarding("usesQuestion")}</legend>
          <div className="flex flex-wrap gap-2">
            {USES.map((value) => {
              const selected = intendedUses.includes(value);
              return (
                <label key={value} className={`cursor-pointer rounded-full border px-4 py-2 text-[13px] ${selected ? "border-orange bg-orange/10 text-fg-primary" : "border-line bg-inset text-fg-secondary"}`}>
                  <input type="checkbox" checked={selected} onChange={() => toggleUse(value)} className="sr-only" />
                  {onboarding(`uses.${value}`)}
                </label>
              );
            })}
          </div>
        </fieldset>

        <label className="mt-6 flex flex-col gap-2">
          <span className="text-[12px] uppercase tracking-[0.08em] text-fg-tertiary">{onboarding("organization")}</span>
          <input maxLength={160} value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder={onboarding("organizationPh")} className="rounded-xl border border-line bg-inset px-4 py-3 outline-none focus:border-orange" />
        </label>

        <button type="submit" disabled={saving || !displayName.trim()} className="mt-6 rounded-full border-0 bg-orange px-6 py-3 text-[14px] font-medium text-white disabled:opacity-50">{saving ? "…" : t("save")}</button>
      </form>

      <section className="mt-6 rounded-2xl border border-line bg-elevated p-5 sm:p-7">
        <h2 className="m-0 mb-2 text-[22px] font-medium">{t("signInTitle")}</h2>
        <p className="mb-6 mt-0 text-[14px] text-fg-secondary">{t("signInBody")}</p>
        <div className="flex items-center justify-between gap-4 border-b border-line-subtle pb-5">
          <div>
            <div className="text-[14px] font-medium">{t("password")}</div>
            <div className="mt-1 text-[12px] text-fg-tertiary">{methods?.password_enabled ? t("enabled") : t("notSet")}</div>
          </div>
        </div>
        <div className="pt-5">
          <div className="mb-3 flex items-center justify-between gap-4">
            <div>
              <div className="text-[14px] font-medium">Google</div>
              {googleIdentity?.email && <div className="mt-1 text-[12px] text-fg-tertiary">{googleIdentity.email}</div>}
            </div>
            {googleIdentity && (
              <button type="button" onClick={disconnectGoogle} disabled={disconnecting} className="rounded-full border border-line bg-transparent px-4 py-2 text-[13px] text-fg-secondary disabled:opacity-50">{disconnecting ? "…" : t("disconnect")}</button>
            )}
          </div>
          {!googleIdentity && <GoogleSignInButton intent="link" onLinked={refreshMethods} />}
        </div>
      </section>

      {notice && <div role="status" className="mt-5 text-[14px] text-fg-secondary">{notice}</div>}
      {error && <div role="alert" className="mt-5 text-[14px]" style={{ color: "var(--status-info)" }}>{error}</div>}
    </main>
  );
}
