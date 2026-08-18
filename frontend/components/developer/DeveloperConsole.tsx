"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { ArcLogo } from "@/components/brand/Arc";
import { DeveloperHeader } from "@/components/developer/DeveloperHeader";
import { ApiError } from "@/lib/api/client";
import {
  acceptLegalTerms,
  createApiKey,
  getDeveloperUsage,
  getMe,
  listApiKeys,
  revokeApiKey,
} from "@/lib/api/resources";
import type {
  ApiKeyInfo,
  CreatedApiKey,
  DeveloperUsage,
  Me,
} from "@/lib/api/types";

const card = "rounded-2xl border border-line-subtle bg-elevated shadow-sm";

function KeyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="8" cy="15" r="4" /><path d="m11 12 8-8M15 8l3 3M17 6l2 2" />
    </svg>
  );
}

export function DeveloperConsole() {
  const t = useTranslations("developer");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [me, setMe] = useState<Me | null>(null);
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [usage, setUsage] = useState<DeveloperUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptingLegalTerms, setAcceptingLegalTerms] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const identity = await getMe();
        setMe(identity);
        if (identity.user) {
          const [keyRows, usageSummary] = await Promise.all([
            listApiKeys(),
            getDeveloperUsage(),
          ]);
          setKeys(keyRows);
          setUsage(usageSummary);
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : t("errorGeneric"));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]);

  const number = (value: number) => new Intl.NumberFormat(locale).format(value);
  const date = (value: string | null) =>
    value ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : t("never");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const result = await createApiKey(name.trim());
      setKeys((current) => [result, ...current]);
      setCreated(result);
      setName("");
      setCopied(false);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("errorGeneric"));
    } finally {
      setCreating(false);
    }
  }

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  async function acceptCurrentLegalTerms() {
    if (!me?.user || acceptingLegalTerms) return;
    setAcceptingLegalTerms(true);
    setError(null);
    try {
      await acceptLegalTerms();
      setMe((current) => current ? { ...current, legal_terms_accepted: true } : current);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("errorGeneric"));
    } finally {
      setAcceptingLegalTerms(false);
    }
  }

  async function revoke(key: ApiKeyInfo) {
    if (!window.confirm(t("revokeConfirm", { name: key.name }))) return;
    setRevoking(key.id);
    setError(null);
    try {
      await revokeApiKey(key.id);
      setKeys((current) => current.filter((row) => row.id !== key.id));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("errorGeneric"));
    } finally {
      setRevoking(null);
    }
  }

  if (loading) {
    return <main className="flex min-h-screen items-center justify-center bg-page text-sm text-fg-secondary">{tc("loading")}</main>;
  }

  if (!me?.user) {
    return (
      <main className="min-h-screen bg-page text-fg-primary">
        <DeveloperHeader active="console" />
        <div className="flex min-h-[calc(100vh-64px)] items-center justify-center px-6 py-12">
          <div className={`${card} max-w-md p-8 text-center`}>
            <div className="mb-5 flex justify-center"><ArcLogo size={58} /></div>
            <h1 className="m-0 text-2xl font-medium">{t("loginTitle")}</h1>
            <p className="mt-3 text-sm leading-6 text-fg-secondary">{t("loginBody")}</p>
            <div className="mt-6 flex justify-center gap-3">
              <Link href="/login?next=/console" className="rounded-xl border border-line-strong px-4 py-2.5 text-sm text-fg-primary no-underline">{t("login")}</Link>
              <Link href="/register?next=/console" className="rounded-xl bg-orange px-4 py-2.5 text-sm font-medium text-white no-underline">{t("createAccount")}</Link>
            </div>
          </div>
        </div>
      </main>
    );
  }

  const remaining = me.limits.chat_remaining;
  const cap = me.limits.chat_cap;
  const usedPercent = cap > 0 ? Math.max(0, Math.min(100, ((cap - remaining) / cap) * 100)) : 0;
  const legalBase = `https://coreai.uz${locale === "ru" ? "" : `/${locale}`}`;

  return (
    <main className="min-h-screen bg-page text-fg-primary">
      <DeveloperHeader active="console" email={me.user.email} />

      <div className="mx-auto max-w-[1180px] px-5 py-10 lg:px-8 lg:py-14">
        <div className="mb-9 flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div><div className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-orange-hi">{t("eyebrow")}</div><h1 className="m-0 text-3xl font-medium tracking-tight md:text-4xl">{t("title")}</h1><p className="mb-0 mt-3 max-w-2xl text-sm leading-6 text-fg-secondary">{t("subtitle")}</p></div>
          <Link href="/docs" className="text-sm text-orange-hi no-underline hover:underline">{t("readDocs")} →</Link>
        </div>

        {error && <div role="alert" className="mb-6 rounded-xl border border-red-400/25 bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</div>}

        {!me.legal_terms_accepted && (
          <section className={`${card} mb-7 flex flex-col items-start justify-between gap-4 p-5 sm:flex-row sm:items-center md:p-6`}>
            <div>
              <h2 className="m-0 text-base font-medium">{t("legalTitle")}</h2>
              <p className="mb-0 mt-2 max-w-3xl text-sm leading-6 text-fg-secondary">{t.rich("legalBody", {
                terms: (chunks) => <a href={`${legalBase}/terms/`} className="text-orange-hi">{chunks}</a>,
                privacy: (chunks) => <a href={`${legalBase}/privacy/`} className="text-orange-hi">{chunks}</a>,
              })}</p>
            </div>
            <button
              type="button"
              disabled={acceptingLegalTerms}
              onClick={() => void acceptCurrentLegalTerms()}
              className="shrink-0 rounded-xl bg-orange px-5 py-3 text-sm font-medium text-white disabled:opacity-50"
            >
              {acceptingLegalTerms ? t("acceptingLegalTerms") : t("acceptLegalTerms")}
            </button>
          </section>
        )}

        {created && (
          <section role="alert" className="mb-7 rounded-2xl border border-orange/40 bg-orange-tint p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4"><div><h2 className="m-0 text-base font-medium">{t("keyCreated")}</h2><p className="mb-0 mt-1 text-sm text-fg-secondary">{t("keyCreatedBody")}</p></div><button onClick={() => setCreated(null)} aria-label={tc("close")} className="border-none bg-transparent text-xl text-fg-tertiary hover:text-fg-primary">×</button></div>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row"><code className="min-w-0 flex-1 overflow-x-auto rounded-xl border border-line-subtle bg-inset px-4 py-3 font-mono text-sm text-fg-primary">{created.key}</code><button onClick={() => void copy(created.key)} className="rounded-xl border border-line-strong bg-elevated px-4 py-3 text-sm text-fg-primary hover:bg-elevated-2">{copied ? tc("copied") : tc("copy")}</button></div>
          </section>
        )}

        <div className="grid gap-7 lg:grid-cols-[1.05fr_.95fr]">
          <section className={`${card} p-5 md:p-6`}>
            <div className="flex items-start justify-between gap-4"><div><h2 className="m-0 flex items-center gap-2 text-lg font-medium"><span className="text-orange-hi"><KeyIcon /></span>{t("keysTitle")}</h2><p className="mb-0 mt-2 text-sm text-fg-secondary">{t("keysBody")}</p></div><span className="rounded-full bg-elevated-2 px-2.5 py-1 text-xs text-fg-tertiary">{keys.length}/3</span></div>
            <form onSubmit={submit} className="mt-5 flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor="key-name">{t("keyName")}</label><input id="key-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={80} placeholder={t("keyPlaceholder")} disabled={!me.legal_terms_accepted || keys.length >= 3 || creating} className="min-w-0 flex-1 rounded-xl border border-line-default bg-inset px-4 py-3 text-sm text-fg-primary outline-none placeholder:text-fg-quaternary focus:border-line-strong disabled:opacity-50" /><button type="submit" disabled={!me.legal_terms_accepted || !name.trim() || keys.length >= 3 || creating} className="rounded-xl bg-orange px-5 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-45">{creating ? t("creating") : t("createKey")}</button></form>
            {keys.length >= 3 && <p className="mb-0 mt-2 text-xs text-fg-tertiary">{t("keyLimit")}</p>}
            <div className="mt-5 divide-y divide-line-subtle border-t border-line-subtle">
              {keys.length === 0 ? <div className="py-8 text-center text-sm text-fg-tertiary">{t("noKeys")}</div> : keys.map((key) => (
                <div key={key.id} className="flex items-center gap-3 py-4"><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{key.name}</div><code className="mt-1 block text-xs text-fg-tertiary">{key.prefix}_••••{key.last_four}</code><div className="mt-1 text-[11px] text-fg-quaternary">{t("createdAt", { date: date(key.created_at) })} · {t("lastUsed", { date: date(key.last_used_at) })}</div></div><button onClick={() => void revoke(key)} disabled={revoking === key.id} className="rounded-lg border border-line-default bg-transparent px-3 py-2 text-xs text-fg-secondary hover:border-red-400/30 hover:text-red-300 disabled:opacity-50">{revoking === key.id ? t("revoking") : t("revoke")}</button></div>
              ))}
            </div>
          </section>

          <section className={`${card} p-5 md:p-6`}>
            <h2 className="m-0 text-lg font-medium">{t("allowanceTitle")}</h2><p className="mb-0 mt-2 text-sm leading-6 text-fg-secondary">{t("allowanceBody")}</p>
            <div className="mt-7 flex items-end justify-between"><div><span className="text-4xl font-medium">{number(remaining)}</span><span className="ml-2 text-sm text-fg-tertiary">/ {number(cap)}</span></div><span className="text-xs text-fg-tertiary">{t("requestsRemaining")}</span></div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-inset"><div className="h-full rounded-full bg-orange transition-all" style={{ width: `${usedPercent}%` }} /></div>
            <p className="mb-0 mt-3 text-xs text-fg-tertiary">{remaining === 0 && me.limits.next_message_in > 0 ? t("availableIn", { seconds: Math.ceil(me.limits.next_message_in) }) : t("sharedLimit")}</p>
            <div className="mt-7 border-t border-line-subtle pt-5"><div className="text-xs font-medium uppercase tracking-[0.09em] text-fg-tertiary">{t("last24")}</div><div className="mt-3 grid grid-cols-3 gap-3"><MiniStat label={t("requests")} value={number(usage?.last_24_hours.requests ?? 0)} /><MiniStat label={t("inputTokens")} value={number(usage?.last_24_hours.input_tokens ?? 0)} /><MiniStat label={t("outputTokens")} value={number(usage?.last_24_hours.output_tokens ?? 0)} /></div></div>
          </section>
        </div>

        <section className={`${card} mt-7 p-5 md:p-6`}>
          <div><h2 className="m-0 text-lg font-medium">{t("usageTitle")}</h2><p className="mb-0 mt-2 text-sm text-fg-secondary">{t("usageBody")}</p></div>
          <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5"><Stat label={t("requests")} value={number(usage?.lifetime.requests ?? 0)} /><Stat label={t("inputTokens")} value={number(usage?.lifetime.input_tokens ?? 0)} /><Stat label={t("outputTokens")} value={number(usage?.lifetime.output_tokens ?? 0)} /><Stat label={t("cachedTokens")} value={number(usage?.lifetime.cached_input_tokens ?? 0)} /><Stat label={t("reasoningTokens")} value={number(usage?.lifetime.reasoning_tokens ?? 0)} /></div>
          <div className="mt-7 grid gap-6 border-t border-line-subtle pt-6 md:grid-cols-2"><UsageTable title={t("bySource")} labelTitle={t("source")} rows={(usage?.by_source ?? []).map((row) => ({ label: row.source === "api" ? t("sourceApi") : t("sourceChat"), requests: row.requests, tokens: row.input_tokens + row.output_tokens }))} number={number} empty={t("noUsage")} t={t} /><UsageTable title={t("byModel")} labelTitle={t("model")} rows={(usage?.by_model ?? []).map((row) => ({ label: row.model, requests: row.requests, tokens: row.input_tokens + row.output_tokens }))} number={number} empty={t("noUsage")} t={t} /></div>
        </section>

      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-inset p-4"><div className="text-xs text-fg-tertiary">{label}</div><div className="mt-2 text-xl font-medium tabular-nums">{value}</div></div>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return <div><div className="text-lg font-medium tabular-nums">{value}</div><div className="mt-1 text-[11px] text-fg-tertiary">{label}</div></div>;
}

function UsageTable({ title, labelTitle, rows, number, empty, t }: { title: string; labelTitle: string; rows: { label: string; requests: number; tokens: number }[]; number: (value: number) => string; empty: string; t: (key: string) => string }) {
  return <div><h3 className="m-0 text-sm font-medium">{title}</h3>{rows.length === 0 ? <p className="text-sm text-fg-tertiary">{empty}</p> : <div className="mt-3 overflow-hidden rounded-xl border border-line-subtle"><div className="grid grid-cols-[1fr_auto_auto] gap-3 bg-inset px-3 py-2 text-[11px] uppercase tracking-wide text-fg-tertiary"><span>{labelTitle}</span><span>{t("requests")}</span><span>{t("tokens")}</span></div>{rows.map((row) => <div key={row.label} className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-5 border-t border-line-subtle px-3 py-3 text-xs"><span className="truncate text-fg-secondary">{row.label}</span><span className="tabular-nums">{number(row.requests)}</span><span className="tabular-nums">{number(row.tokens)}</span></div>)}</div>}</div>;
}
