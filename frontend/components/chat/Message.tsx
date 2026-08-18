"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ArcMark, ArcThinking } from "../brand/Arc";

export type ChatMsg = {
  role: "user" | "assistant";
  content: string;
  model?: string | null;
};

export interface VersionNavProps {
  index: number;
  count: number;
  onPrev?: () => void;
  onNext?: () => void;
  onDelete?: () => void;
}

// `< 2/3 >` switcher between sibling versions (edits of a message, or regenerations),
// with an optional delete control (armed via an inline Delete/Cancel confirm).
export function VersionNav({ index, count, onPrev, onNext, onDelete }: VersionNavProps) {
  const t = useTranslations("common");
  const [confirming, setConfirming] = useState(false);
  if (count <= 1) return null;
  const arrow =
    "inline-flex h-[18px] w-[18px] items-center justify-center rounded text-fg-tertiary hover:text-fg-primary hover:bg-elevated-2 disabled:opacity-30 disabled:hover:bg-transparent";
  return (
    <span
      className="inline-flex select-none items-center gap-[3px] text-[11.5px] text-fg-tertiary"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <button onClick={onPrev} disabled={!onPrev} aria-label="Previous version" className={arrow} style={{ cursor: onPrev ? "pointer" : "default" }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
      </button>
      {index + 1}/{count}
      <button onClick={onNext} disabled={!onNext} aria-label="Next version" className={arrow} style={{ cursor: onNext ? "pointer" : "default" }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
      </button>
      {onDelete &&
        (confirming ? (
          <span className="ml-1 inline-flex items-center gap-1">
            <button
              onClick={() => { setConfirming(false); onDelete(); }}
              className="rounded px-[6px] py-[1px] text-[11px] hover:bg-elevated-2"
              style={{ color: "var(--status-info)", cursor: "pointer" }}
            >
              {t("delete")}
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="rounded px-[6px] py-[1px] text-[11px] text-fg-tertiary hover:bg-elevated-2 hover:text-fg-primary"
              style={{ cursor: "pointer" }}
            >
              {t("cancel")}
            </button>
          </span>
        ) : (
          <button onClick={() => setConfirming(true)} aria-label="Delete version" className={`${arrow} hover:!text-[var(--status-info)]`} style={{ cursor: "pointer" }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg>
          </button>
        ))}
    </span>
  );
}

const mdComponents: Components = {
  p: ({ children }) => <p style={{ margin: "0 0 12px" }}>{children}</p>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: "var(--brand-orange-hi)" }}>
      {children}
    </a>
  ),
  ul: ({ children }) => <ul style={{ margin: "0 0 12px", paddingLeft: 22 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: "0 0 12px", paddingLeft: 22 }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
  h1: ({ children }) => <h3 style={{ fontSize: 20, fontWeight: 500, margin: "8px 0 10px" }}>{children}</h3>,
  h2: ({ children }) => <h3 style={{ fontSize: 18, fontWeight: 500, margin: "8px 0 10px" }}>{children}</h3>,
  h3: ({ children }) => <h4 style={{ fontSize: 16, fontWeight: 500, margin: "8px 0 8px" }}>{children}</h4>,
  pre: ({ children }) => (
    <pre
      className="ca-scroll"
      style={{
        margin: "12px 0",
        padding: "14px 16px",
        background: "var(--bg-inset)",
        border: "1px solid var(--border-default)",
        borderRadius: 12,
        overflowX: "auto",
        fontFamily: "var(--font-mono)",
        fontSize: 12.5,
        lineHeight: 1.6,
        color: "var(--fg-secondary)",
      }}
    >
      {children}
    </pre>
  ),
  code: ({ className, children }) => {
    const block = /language-/.test(className ?? "");
    if (block) return <code style={{ fontFamily: "var(--font-mono)", fontSize: 12.5 }}>{children}</code>;
    return (
      <code
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.9em",
          background: "var(--bg-inset)",
          padding: "1px 5px",
          borderRadius: 5,
          color: "var(--fg-primary)",
        }}
      >
        {children}
      </code>
    );
  },
  // GFM tables: scroll on overflow, real cell padding + row rules so columns never collide.
  table: ({ children }) => (
    <div className="ca-scroll" style={{ overflowX: "auto", margin: "14px 0" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14, lineHeight: 1.5 }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ textAlign: "left", padding: "8px 14px", borderBottom: "1px solid var(--border-strong)", fontWeight: 600, color: "var(--fg-primary)", whiteSpace: "nowrap" }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ padding: "8px 14px", borderBottom: "1px solid var(--border-subtle)", color: "var(--fg-secondary)", verticalAlign: "top" }}>{children}</td>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{ margin: "0 0 12px", paddingLeft: 14, borderLeft: "3px solid var(--border-default)", color: "var(--fg-secondary)" }}>{children}</blockquote>
  ),
  hr: () => <hr style={{ border: "none", borderTop: "1px solid var(--border-subtle)", margin: "16px 0" }} />,
};

// Strip the model's boilerplate reasoning preamble so the trace reads cleanly.
function cleanReasoning(text: string): string {
  return text.replace(/^\s*here['’]?s (?:a|my) thinking process:?\s*/i, "");
}

const LAMP = "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.5.5 1 1.2 1 2V16h6v-.5c0-.8.5-1.5 1-2A6 6 0 0 0 12 3z";

// Chain-of-thought toggle (Claude-style): a dim "💡 Thinking…" label that brightens on
// hover and becomes "Thought for N seconds" when finished. A › chevron appears on
// hover; clicking reveals the full trace inline (no scroll box).
export function ThinkingBlock({ text, busy, seconds }: { text: string; busy?: boolean; seconds?: number | null }) {
  const t = useTranslations("chat");
  const [open, setOpen] = useState(false);
  if (!text) return null;
  const label = seconds != null ? t("thoughtFor", { count: Math.max(1, Math.round(seconds)) }) : t("thoughtDone");
  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex items-center gap-[6px] text-[13px] text-fg-tertiary transition-colors hover:text-fg-secondary"
        style={{ cursor: "pointer" }}
      >
        {busy ? (
          <span className="flex items-center gap-[6px] opacity-70 transition-opacity group-hover:opacity-100">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="animate-pulse">
              <path d={LAMP} />
            </svg>
            <span>{t("thinking")}…</span>
          </span>
        ) : (
          <span className="flex items-center gap-[6px]">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d={LAMP} />
            </svg>
            <span>{label}</span>
          </span>
        )}
        <svg
          width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
          className={`transition-[transform,opacity] duration-150 ${open ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
          style={{ transform: open ? "rotate(90deg)" : "none" }}
        >
          <path d="M9 6l6 6-6 6" />
        </svg>
      </button>
      {open && (
        <div className="mt-2 whitespace-pre-wrap border-l-2 border-line-subtle pl-3 text-[13px] leading-[1.7] text-fg-tertiary">
          {cleanReasoning(text)}
        </div>
      )}
    </div>
  );
}

export function AssistantMessage({
  content,
  reasoning,
  reasoningMs,
  model,
  streaming,
  actions,
  versions,
}: {
  content: string;
  reasoning?: string | null;
  reasoningMs?: number | null;
  model?: string | null;
  streaming?: boolean;
  actions?: React.ReactNode;
  versions?: VersionNavProps;
}) {
  return (
    <div className="ca-msg flex w-full min-w-0 items-start gap-[14px]">
      {streaming ? (
        <ArcThinking size={26} className="mt-[2px] shrink-0" />
      ) : (
        <ArcMark size={26} className="mt-[2px] shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <ThinkingBlock
          text={reasoning ?? ""}
          busy={!!streaming && !content}
          seconds={reasoningMs != null ? reasoningMs / 1000 : null}
        />
        {streaming ? (
          <div style={{ fontSize: 15, lineHeight: 1.7, color: "var(--fg-primary)", whiteSpace: "pre-wrap" }}>
            {content}
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 17,
                background: "var(--brand-orange-hi)",
                verticalAlign: "-2px",
                marginLeft: 2,
              }}
              className="animate-blink"
            />
          </div>
        ) : (
          <div style={{ fontSize: 15, lineHeight: 1.7, color: "var(--fg-primary)" }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {content}
            </ReactMarkdown>
          </div>
        )}
        {(actions || (versions && versions.count > 1)) && (
          <div className="ca-acts mt-3 flex items-center gap-2">
            {model && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-tertiary)" }}>
                {model}
              </span>
            )}
            {versions && <VersionNav {...versions} />}
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}

export function UserMessage({
  content,
  onEdit,
  versions,
}: {
  content: string;
  onEdit?: (text: string) => void;
  versions?: VersionNavProps;
}) {
  const t = useTranslations("common");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);

  function commit() {
    const v = draft.trim();
    if (!v) return;
    setEditing(false);
    if (v !== content) onEdit?.(v);
  }
  function cancel() {
    setEditing(false);
    setDraft(content);
  }

  if (editing) {
    return (
      <div className="ca-msg flex justify-end">
        <div className="w-full max-w-[85%]">
          <div className="rounded-[14px] border bg-elevated p-2" style={{ borderColor: "var(--brand-orange)" }}>
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(220, e.target.scrollHeight) + "px";
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commit(); }
                if (e.key === "Escape") cancel();
              }}
              rows={1}
              className="ca-scroll w-full resize-none border-none bg-transparent px-2 py-1 text-[14px] leading-[1.55] text-fg-primary outline-none"
              style={{ minHeight: 30 }}
            />
          </div>
          <div className="mt-2 flex justify-end gap-2">
            <button onClick={cancel} className="cursor-pointer rounded-lg border-none bg-transparent px-3 py-[6px] text-[13px] text-fg-tertiary hover:text-fg-primary">
              {t("cancel")}
            </button>
            <button onClick={commit} disabled={!draft.trim()} className="rounded-lg border-none px-4 py-[6px] text-[13px] font-medium text-white disabled:opacity-40" style={{ background: "var(--brand-orange)", cursor: draft.trim() ? "pointer" : "default" }}>
              {t("save")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ca-msg group flex flex-col items-end gap-[6px]">
      <div
        className="whitespace-pre-wrap"
        style={{
          maxWidth: "68%",
          background: "var(--bg-elevated-2)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "14px 14px 4px 14px",
          padding: "10px 14px",
          fontSize: 14,
          lineHeight: 1.55,
          color: "var(--fg-primary)",
        }}
      >
        {content}
      </div>
      {(onEdit || (versions && versions.count > 1)) && (
        <div className="flex items-center gap-1 pr-1">
          {versions && <VersionNav {...versions} />}
          {onEdit && (
            <button
              onClick={() => { setDraft(content); setEditing(true); }}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] text-fg-tertiary opacity-0 transition-opacity hover:bg-elevated-2 hover:text-fg-primary group-hover:opacity-100"
              style={{ cursor: "pointer" }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
              {t("edit")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
