"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { streamChat, type StreamChatBody } from "@/lib/api/chat-stream";
import {
  deleteConversation as apiDelete,
  deleteMessage as apiDeleteMessage,
  getConversation,
  renameConversation as apiRename,
  selectVersion,
} from "@/lib/api/resources";
import type { ConversationListItem, ModelInfo } from "@/lib/api/types";
import {
  activePath,
  buildTree,
  emptyTree,
  setActiveChild,
  versionsOf,
  type Tree,
  type TreeNode,
} from "@/lib/chat/tree";
import { useConversations, useMe, useModels } from "@/lib/hooks";

import { ArcLogo, ArcThinking, Wordmark } from "../brand/Arc";
import { ThemeToggle } from "../ui/ThemeToggle";
import { LocaleSwitcher } from "../ui/LocaleSwitcher";
import { AssistantMessage, UserMessage } from "./Message";

const iconBtn =
  "inline-flex rounded-lg p-[5px] text-fg-tertiary transition-colors hover:bg-elevated-2 hover:text-fg-primary cursor-pointer";

const genId = () =>
  typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `tmp-${Math.random().toString(36).slice(2)}`;

function groupByDate(items: ConversationListItem[], labels: { today: string; yesterday: string; earlier: string }) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const groups: { label: string; items: ConversationListItem[] }[] = [
    { label: labels.today, items: [] },
    { label: labels.yesterday, items: [] },
    { label: labels.earlier, items: [] },
  ];
  for (const it of items) {
    const t = new Date(it.updated_at).getTime();
    if (t >= startOfToday) groups[0].items.push(it);
    else if (t >= startOfYesterday) groups[1].items.push(it);
    else groups[2].items.push(it);
  }
  return groups.filter((g) => g.items.length > 0);
}

export function ChatApp({ initialConversationId }: { initialConversationId?: string } = {}) {
  const t = useTranslations("chat");
  const tc = useTranslations("common");
  const locale = useLocale();
  const privacyUrl = `https://coreai.uz${locale === "ru" ? "" : `/${locale}`}/privacy/`;

  const { me, refresh: refreshMe } = useMe();
  const models = useModels();
  const isRegistered = !!me?.user;
  const { conversations, refresh: refreshConversations } = useConversations(isRegistered);

  const [modelId, setModelId] = useState<string>("");
  const [tree, setTree] = useState<Tree>(emptyTree());
  const [pending, setPending] = useState<{ basePath: TreeNode[]; optimisticUser: string | null } | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamReasoning, setStreamReasoning] = useState("");
  const [streamReasonMs, setStreamReasonMs] = useState<number | null>(null);
  const [queued, setQueued] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<null | "anon" | "user">(null);
  const [convId, setConvId] = useState<string | null>(initialConversationId ?? null);
  const [railOpen, setRailOpen] = useState(false);
  const [modelMenu, setModelMenu] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [search, setSearch] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const [composerH, setComposerH] = useState(140);
  const loadedRef = useRef(false);
  // Typewriter reveal: network fills targetRef; a rAF loop reveals it at a steady
  // pace into streamText, so bursty chunks still render as smooth streaming.
  const targetRef = useRef("");
  const revealedRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  function startPump() {
    if (rafRef.current != null) return;
    const tick = () => {
      const target = targetRef.current;
      if (revealedRef.current < target.length) {
        const remaining = target.length - revealedRef.current;
        revealedRef.current += Math.min(remaining, Math.max(2, Math.ceil(remaining / 8)));
        setStreamText(target.slice(0, revealedRef.current));
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }
  function stopPump() {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }

  useEffect(() => {
    if (!modelId && models.length) setModelId(models[0].id);
  }, [models, modelId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [tree, pending, streamText, queued]);

  // The composer floats over the message list; measure its real height (it grows with
  // multi-line input) so the last message always clears it instead of hiding beneath.
  useEffect(() => {
    const el = composerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setComposerH(el.offsetHeight));
    ro.observe(el);
    setComposerH(el.offsetHeight);
    return () => ro.disconnect();
  }, []);

  // Restore the conversation from the URL on load/refresh (/c/[id]).
  useEffect(() => {
    if (initialConversationId && !loadedRef.current) {
      loadedRef.current = true;
      void openConversation(initialConversationId, { updateUrl: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId]);

  const selectedModel: ModelInfo | undefined = useMemo(
    () => models.find((m) => m.id === modelId),
    [models, modelId],
  );

  const filteredConvos = useMemo(
    () => (search ? conversations.filter((c) => (c.title ?? "").toLowerCase().includes(search.toLowerCase())) : conversations),
    [conversations, search],
  );

  // The visible conversation = the tree's active path (follow active_child from root).
  const path = useMemo(() => activePath(tree), [tree]);

  // Run one generation (new turn / edit / regenerate). `base` is the visible path above
  // the streaming turn; `optimisticUser` is the user bubble shown under it (null for
  // regenerate). The tree is reconciled from the server when the stream finishes.
  async function runStream(body: StreamChatBody, base: TreeNode[], optimisticUser: string | null) {
    if (streaming) return;
    setError(null);
    setLimit(null);
    setQueued(false);
    setPending({ basePath: base, optimisticUser });
    setStreaming(true);
    setStreamText("");
    setStreamReasoning("");
    setStreamReasonMs(null);
    targetRef.current = "";
    revealedRef.current = 0;
    startPump();

    const controller = new AbortController();
    abortRef.current = controller;
    let acc = "";
    let accReason = "";
    let reasonStart = 0;          // ms timestamp of the first reasoning token
    let reasonMs: number | null = null;
    let newConvId = convId;
    const assistantModel = selectedModel?.display_name ?? modelId;

    try {
      for await (const ev of streamChat(body, controller.signal)) {
        if (ev.type === "delta") {
          setQueued(false);
          // first answer token → reasoning is done; freeze its duration
          if (reasonStart && reasonMs == null) { reasonMs = Date.now() - reasonStart; setStreamReasonMs(reasonMs); }
          acc += ev.content;
          targetRef.current = acc; // pump reveals it smoothly
        } else if (ev.type === "reasoning") {
          setQueued(false);
          if (!reasonStart) reasonStart = Date.now();
          accReason += ev.content;
          setStreamReasoning(accReason); // shown live in the collapsible block
        } else if (ev.type === "queued") {
          setQueued(true);
        } else if (ev.type === "title") {
          // Auto-generated on the first turn — surface it in the sidebar right away.
          if (isRegistered) void refreshConversations();
        } else if (ev.type === "done") {
          if (ev.conversation_id) newConvId = ev.conversation_id;
        } else if (ev.type === "error") {
          if (ev.code === "rate_limited") setLimit(isRegistered ? "user" : "anon");
          else setError(t("errorGeneric"));
        }
      }
    } catch {
      // aborted (stop) or network — keep whatever we streamed
    } finally {
      // let the reveal catch up to the full text before committing (no end-jump)
      await new Promise<void>((resolve) => {
        const wait = () => (revealedRef.current >= targetRef.current.length ? resolve() : requestAnimationFrame(wait));
        wait();
      });
      stopPump();
      setStreaming(false);
      setQueued(false);
      abortRef.current = null;

      let reconciled = false;
      if (newConvId) {
        try {
          const detail = await getConversation(newConvId);
          setTree(buildTree(detail));
          if (newConvId !== convId) {
            setConvId(newConvId);
            if (typeof window !== "undefined") {
              window.history.replaceState(null, "", `/c/${newConvId}`);
            }
          }
          setPending(null);
          reconciled = true;
        } catch {
          // refetch failed — fall back to an optimistic local commit below
        }
      }
      if (reasonStart && reasonMs == null) reasonMs = Date.now() - reasonStart; // ended during reasoning
      if (!reconciled) {
        if (acc || accReason) optimisticCommit(base, optimisticUser, acc, accReason, reasonMs, assistantModel);
        else setPending(null);
      }
      setStreamText("");
      setStreamReasoning("");
      setStreamReasonMs(null);
      void refreshMe();
      if (isRegistered) void refreshConversations();
    }
  }

  // Append synthetic nodes when the post-stream refetch fails, so the turn isn't lost
  // visually (real ids arrive on the next successful load).
  function optimisticCommit(base: TreeNode[], userText: string | null, assistantText: string, reasoning: string, reasoningMs: number | null, model: string) {
    setTree((prev) => {
      const nodes = { ...prev.nodes };
      let rootId = prev.rootId;
      const leafId = base.length ? base[base.length - 1].id : null;
      const now = new Date().toISOString();
      let assistantParentId = leafId;
      if (userText != null) {
        const uid = genId();
        nodes[uid] = { id: uid, role: "user", content: userText, reasoning: null, reasoning_ms: null, model: null, parent_id: leafId, active_child_id: null, created_at: now };
        if (leafId && nodes[leafId]) nodes[leafId] = { ...nodes[leafId], active_child_id: uid };
        else if (!leafId) rootId = uid;
        assistantParentId = uid;
      }
      const aid = genId();
      nodes[aid] = { id: aid, role: "assistant", content: assistantText, reasoning: reasoning || null, reasoning_ms: reasoningMs, model, parent_id: assistantParentId, active_child_id: null, created_at: now };
      if (assistantParentId && nodes[assistantParentId]) nodes[assistantParentId] = { ...nodes[assistantParentId], active_child_id: aid };
      return { nodes, rootId };
    });
    setPending(null);
  }

  function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || streaming) return;
    setInput("");
    const body: StreamChatBody = { model: modelId, user_content: content, thinking };
    if (convId) body.conversation_id = convId;
    void runStream(body, activePath(tree), content);
  }

  // Edit a user message → a sibling under the same parent + a fresh reply.
  function editMessage(node: TreeNode, text: string) {
    const content = text.trim();
    if (!content || streaming || !convId) return;
    const idx = path.findIndex((x) => x.id === node.id);
    const base = idx >= 0 ? path.slice(0, idx) : path;
    void runStream(
      { model: modelId, conversation_id: convId, parent_id: node.parent_id, user_content: content, thinking },
      base,
      content,
    );
  }

  // Regenerate an assistant reply → a new sibling under its user message.
  function regenerate(node: TreeNode) {
    if (streaming || !convId || node.parent_id == null) return;
    const idx = path.findIndex((x) => x.id === node.id);
    const base = idx >= 0 ? path.slice(0, idx) : path;
    void runStream({ model: modelId, conversation_id: convId, parent_id: node.parent_id, thinking }, base, null);
  }

  // Switch to a sibling version and persist the choice (so a reload restores it).
  async function switchTo(siblingId: string) {
    if (streaming || !convId) return;
    const sib = tree.nodes[siblingId];
    if (!sib) return;
    setTree((prev) => setActiveChild(prev, sib.parent_id, sib.id));
    try {
      await selectVersion(convId, siblingId);
    } catch {
      /* keep the optimistic switch; a reload re-fetches the server truth */
    }
  }

  // Delete a version (and its subtree); reconcile the tree from the server after.
  async function deleteVersion(node: TreeNode) {
    if (streaming || !convId) return;
    try {
      await apiDeleteMessage(convId, node.id);
      const detail = await getConversation(convId);
      setTree(buildTree(detail));
    } catch {
      /* ignore — the tree is unchanged on failure */
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function newChatLocal() {
    setTree(emptyTree());
    setPending(null);
    setConvId(null);
    setStreamText("");
    setStreamReasoning("");
    setStreamReasonMs(null);
    setError(null);
    setLimit(null);
  }

  function newChat() {
    newChatLocal();
    setRailOpen(false);
    if (typeof window !== "undefined") window.history.pushState(null, "", "/");
  }

  async function openConversation(id: string, opts: { updateUrl?: boolean; push?: boolean } = {}) {
    const { updateUrl = true, push = true } = opts;
    setRailOpen(false);
    try {
      const c = await getConversation(id);
      setConvId(c.id);
      if (c.model) setModelId(c.model);
      setTree(buildTree(c));
      setPending(null);
      setStreamText("");
      setStreamReasoning("");
      setStreamReasonMs(null);
      setError(null);
      setLimit(null);
      if (updateUrl && typeof window !== "undefined") {
        const url = `/c/${c.id}`;
        if (push) window.history.pushState(null, "", url);
        else window.history.replaceState(null, "", url);
      }
    } catch {
      // not found / expired / not owned → fall back to a fresh chat
      newChatLocal();
      if (typeof window !== "undefined") window.history.replaceState(null, "", "/");
    }
  }

  async function rename(id: string, current: string | null) {
    const next = window.prompt(tc("rename"), current ?? "");
    if (next && next.trim()) {
      await apiRename(id, next.trim()).catch(() => {});
      void refreshConversations();
    }
  }

  async function remove(id: string) {
    await apiDelete(id).catch(() => {});
    if (convId === id) newChat();
    void refreshConversations();
  }

  function copy(id: string, text: string) {
    void navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1400);
  }

  function logout() {
    void fetch("/api/auth/logout", { method: "POST", credentials: "include" }).then(() => {
      setSettingsOpen(false);
      newChat();
      void refreshMe();
    });
  }

  const isEmpty = path.length === 0 && !streaming && !pending;
  const chips = t.raw("chips") as string[];
  const freeLeft = me?.limits.chat_remaining ?? null;

  return (
    <>
      <main className="relative flex overflow-hidden bg-page text-fg-primary" style={{ height: "100dvh", fontFamily: "var(--font-body)", fontWeight: 300 }}>
      {/* scrim (mobile drawer) */}
      {railOpen && (
        <div onClick={() => setRailOpen(false)} className="fixed inset-0 z-[70] md:hidden" style={{ background: "rgba(0,0,0,0.55)" }} />
      )}

      {/* ============ LEFT RAIL ============ */}
      <aside
        className={`ca-rail !fixed z-[80] flex h-full w-[286px] shrink-0 flex-col overflow-hidden rounded-[16px] border border-line-subtle bg-page shadow-md transition-transform md:!relative md:translate-x-0 md:my-3 md:ml-3 md:h-[calc(100dvh-24px)] ${railOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between px-[18px] pb-3 pt-[18px]">
          <Link href="/" className="flex items-center gap-[9px] no-underline text-fg-primary">
            <ArcLogo size={36} />
            <Wordmark size={18} />
          </Link>
          <button onClick={() => setRailOpen(false)} aria-label="Close" className={`${iconBtn} md:hidden`}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M6 6l12 12M18 6l-12 12" /></svg>
          </button>
        </div>

        <div className="px-[14px] pb-3 pt-[6px]">
          <button onClick={newChat} className="flex w-full items-center justify-center gap-2 rounded-xl border border-line-subtle bg-elevated px-4 py-[10px] text-[13px] font-medium text-fg-primary transition-colors hover:bg-elevated-2">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="var(--brand-orange-hi)" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            {t("newChat")}
          </button>
        </div>

        {isRegistered && (
          <div className="px-[14px] pb-[10px]">
            <div className="flex items-center gap-[9px] rounded-xl border border-line-subtle bg-inset px-3 py-[9px] transition-colors focus-within:border-line-default">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="1.6" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("search")} className="min-w-0 flex-1 border-none bg-transparent text-[13px] text-fg-primary outline-none" />
            </div>
          </div>
        )}

        <div className="ca-scroll flex-1 overflow-y-auto px-2 pb-2 pt-1">
          {isRegistered ? (
            groupByDate(filteredConvos, { today: t("groupToday"), yesterday: t("groupYesterday"), earlier: t("groupEarlier") }).map((g) => (
              <div key={g.label}>
                <div className="px-2 pb-[6px] pt-3 text-[11px] font-medium uppercase tracking-[0.06em] text-fg-tertiary">{g.label}</div>
                {g.items.map((h) => {
                  const active = h.id === convId;
                  return (
                    <div key={h.id} className={`ca-hist group flex items-center gap-1 rounded-lg px-2 py-[7px] transition-colors ${active ? "bg-elevated-2" : "hover:bg-elevated"}`}>
                      <button onClick={() => openConversation(h.id)} className="min-w-0 flex-1 cursor-pointer truncate border-none bg-transparent p-0 text-left text-[13px]" style={{ color: active ? "var(--fg-primary)" : "var(--fg-secondary)" }}>
                        {h.title || t("newChat")}
                      </button>
                      <div className="flex shrink-0 gap-[2px] opacity-0 transition-opacity group-hover:opacity-100">
                        <button onClick={() => rename(h.id, h.title)} aria-label={tc("rename")} className={iconBtn}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
                        </button>
                        <button onClick={() => remove(h.id)} aria-label={tc("delete")} className={iconBtn}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 14h10l1-14" /></svg>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ))
          ) : (
            <div className="px-3 pt-4 text-[12.5px] leading-relaxed text-fg-tertiary">{t("guestPlan")}</div>
          )}
        </div>

        {/* account / settings */}
        <div className="relative border-t border-line-subtle px-[14px] py-3">
          {settingsOpen && (
            <>
              <div onClick={() => setSettingsOpen(false)} className="fixed inset-0 z-30" />
              <div className="absolute bottom-[calc(100%+8px)] left-[14px] right-[14px] z-40 animate-fadeup rounded-xl border border-line-default bg-elevated p-3 shadow-lg">
                <div className="mb-1 px-1 text-[11px] uppercase tracking-[0.08em] text-fg-tertiary">{tc("settings")}</div>
                <div className="flex items-center justify-between px-1 py-2">
                  <span className="text-[13px] text-fg-secondary">{tc("theme")}</span>
                  <ThemeToggle />
                </div>
                <div className="flex items-center justify-between gap-2 px-1 py-2">
                  <span className="text-[13px] text-fg-secondary">{tc("language")}</span>
                  <LocaleSwitcher />
                </div>
                {isRegistered && (
                  <Link href="/account" onClick={() => setSettingsOpen(false)} className="mt-1 flex w-full items-center gap-2 rounded-lg px-1 py-2 text-[13px] text-fg-secondary no-underline hover:bg-elevated-2 hover:text-fg-primary">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
                    {tc("accountSettings")}
                  </Link>
                )}
                {isRegistered && (
                  <Link href="/console" onClick={() => setSettingsOpen(false)} className="mt-1 flex w-full items-center gap-2 rounded-lg px-1 py-2 text-[13px] text-fg-secondary no-underline hover:bg-elevated-2 hover:text-fg-primary">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M7 4v6M17 4v6M6 13h4M6 17h7" /><rect x="3" y="3" width="18" height="18" rx="3" /></svg>
                    {tc("developerConsole")}
                  </Link>
                )}
                {isRegistered && (
                  <button onClick={logout} className="flex w-full cursor-pointer items-center gap-2 rounded-lg border-none bg-transparent px-1 py-2 text-left text-[13px] text-fg-secondary hover:text-fg-primary">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></svg>
                    {tc("logout")}
                  </button>
                )}
                <div className="mt-2 border-t border-line-subtle px-1 pt-2 text-[11.5px] leading-relaxed text-fg-tertiary">
                  {t("privacyNote")}{" "}
                  <a href={privacyUrl} className="text-orange-hi">
                    {t("learnMore")}
                  </a>
                </div>
              </div>
            </>
          )}
          <button onClick={() => setSettingsOpen((v) => !v)} className="flex w-full cursor-pointer items-center gap-[11px] rounded-xl border-none bg-transparent p-2 text-left outline-none transition-colors hover:bg-elevated-2">
            <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full text-[13px] font-semibold" style={{ background: "var(--brand-orange-tint)", color: "var(--brand-orange-hi)" }}>
              {isRegistered ? (me!.user!.display_name?.[0] || me!.user!.email[0] || "U").toUpperCase() : "?"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-fg-primary">{isRegistered ? me!.user!.display_name || me!.user!.email : t("guest")}</div>
              <div className="truncate text-[11.5px] text-fg-tertiary">{isRegistered ? t("memberPlan") : freeLeft !== null ? t("freeLeft", { count: freeLeft }) : t("guestPlan")}</div>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>
          </button>
          {!isRegistered && (
            <Link href="/register" className="mt-[11px] flex w-full items-center justify-center gap-[7px] rounded-[10px] border border-line-strong bg-transparent px-3 py-[9px] text-[13px] font-medium text-fg-primary no-underline">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand-orange-hi)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l2.4 6.9H22l-6 4.3 2.3 7-6.3-4.6L5.7 21 8 14.2 2 9.9h7.6z" /></svg>
              {t("signToSave")}
            </Link>
          )}
        </div>
      </aside>

      {/* ============ MAIN COLUMN ============ */}
      <section className="ca-main relative flex min-w-0 flex-1 flex-col" style={{ height: "100dvh" }}>
        {/* top bar */}
        <div className="relative z-30 flex h-[60px] shrink-0 items-center justify-between gap-3 px-[18px]">
          <div className="flex min-w-0 items-center gap-2">
            <button onClick={() => setRailOpen(true)} aria-label="Menu" className={`${iconBtn} md:hidden`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
            </button>
            {/* model picker lives in the composer now (Claude-style) */}
          </div>
        </div>

        {/* conversation / empty */}
        <div ref={scrollRef} className="ca-scroll relative flex-1 overflow-y-auto">
          {isEmpty ? (
            <div className="flex min-h-full flex-col items-center justify-center px-6 py-10 text-center">
              <div className="w-full max-w-[620px] animate-fadeup">
                <div className="mb-5 flex justify-center"><ArcLogo size={64} /></div>
                <h1 className="m-0 mb-[10px]" style={{ fontFamily: "var(--font-display)", fontWeight: 400, fontSize: 42, lineHeight: 1.1, letterSpacing: "-0.01em", color: "var(--fg-primary)" }}>{me?.user?.display_name ? t("greetNamed", { name: me.user.display_name }) : t("greet")}</h1>
                <p className="mb-[26px] mt-0 text-[15px] text-fg-secondary">{t("greetSub")}</p>
                <div className="flex flex-wrap justify-center gap-[10px]">
                  {chips.map((c) => (
                    <button key={c} onClick={() => send(c)} className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-line-subtle bg-elevated px-4 py-[9px] text-[13.5px] text-fg-secondary transition-colors hover:border-line-strong hover:bg-elevated-2">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--brand-orange-hi)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex max-w-chat flex-col gap-[26px] px-6 pt-7" style={{ paddingBottom: composerH + 28 }}>
              {(pending ? pending.basePath : path).map((n) => {
                const v = versionsOf(tree, n);
                const nav =
                  v.count > 1
                    ? {
                        index: v.index,
                        count: v.count,
                        onPrev: !streaming && v.prevId ? () => switchTo(v.prevId!) : undefined,
                        onNext: !streaming && v.nextId ? () => switchTo(v.nextId!) : undefined,
                        onDelete: !streaming ? () => deleteVersion(n) : undefined,
                      }
                    : undefined;
                return n.role === "user" ? (
                  <UserMessage
                    key={n.id}
                    content={n.content}
                    onEdit={!streaming ? (text) => editMessage(n, text) : undefined}
                    versions={nav}
                  />
                ) : (
                  <AssistantMessage
                    key={n.id}
                    content={n.content}
                    reasoning={n.reasoning}
                    reasoningMs={n.reasoning_ms}
                    model={n.model}
                    versions={nav}
                    actions={
                      <>
                        <button onClick={() => copy(n.id, n.content)} className={`${iconBtn} !px-2 !text-[12px]`} style={{ color: copiedId === n.id ? "var(--brand-orange-hi)" : undefined }}>
                          {copiedId === n.id ? tc("copied") : tc("copy")}
                        </button>
                        {!streaming && (
                          <button onClick={() => regenerate(n)} className={`${iconBtn} !px-2 !text-[12px]`}>
                            {tc("retry")}
                          </button>
                        )}
                      </>
                    }
                  />
                );
              })}

              {pending?.optimisticUser != null && <UserMessage content={pending.optimisticUser} />}

              {queued && (
                <div className="flex items-center gap-[14px]">
                  <ArcThinking size={26} />
                  <span className="text-[14px] text-fg-tertiary">{t("queued")}</span>
                </div>
              )}

              {streaming && !queued && (
                <AssistantMessage content={streamText} reasoning={streamReasoning} reasoningMs={streamReasonMs} model={selectedModel?.display_name ?? modelId} streaming />
              )}

              {error && <div className="text-[14px]" style={{ color: "var(--status-info)" }}>{error}</div>}
            </div>
          )}
        </div>

        {/* composer — floats over the message list; the container's own bottom-fade bg
            blends scrolling messages into it without covering the input card. */}
        <div
          ref={composerRef}
          className={`pointer-events-none inset-x-0 bottom-0 z-20 shrink-0 px-6 pb-4 pt-8 ${isEmpty ? "relative" : "absolute"}`}
          style={{ background: "linear-gradient(to top, var(--bg-page) 60%, transparent)" }}
        >
          {limit && (
            <div className="pointer-events-auto absolute bottom-[calc(100%+4px)] left-1/2 z-20 w-[min(440px,calc(100%-48px))] -translate-x-1/2 animate-fadeup rounded-2xl border bg-elevated p-[22px] shadow-xl" style={{ borderColor: "var(--brand-orange)" }}>
              <div className="flex items-start gap-[13px]">
                <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[10px]" style={{ background: "var(--brand-orange-tint)" }}>
                  <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--brand-orange-hi)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l2.4 6.9H22l-6 4.3 2.3 7-6.3-4.6L5.7 21 8 14.2 2 9.9h7.6z" /></svg>
                </div>
                <div className="flex-1">
                  <div className="mb-[5px] text-[22px] leading-tight text-fg-primary" style={{ fontFamily: "var(--font-display)" }}>{limit === "anon" ? t("limitTitleAnon") : t("limitTitleUser")}</div>
                  <p className="m-0 mb-4 text-[13.5px] leading-[1.55] text-fg-secondary">{limit === "anon" ? t("limitBodyAnon") : t("limitBodyUser")}</p>
                  <div className="flex items-center gap-[10px]">
                    {limit === "anon" && <Link href="/register" className="inline-flex cursor-pointer items-center rounded-full border-none px-[18px] py-[10px] text-[13.5px] font-medium text-white no-underline" style={{ background: "var(--brand-orange)" }}>{t("limitCtaAnon")}</Link>}
                    <button onClick={() => setLimit(null)} className="cursor-pointer border-none bg-transparent px-3 py-[10px] text-[13.5px] text-fg-tertiary">{t("limitLater")}</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="pointer-events-auto mx-auto max-w-chat">
            <div className="border border-line-default bg-elevated p-2 shadow-md" style={{ borderRadius: 20, borderColor: streaming ? "var(--brand-orange)" : undefined }}>
              <textarea
                value={input}
                onChange={(e) => { setInput(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(160, e.target.scrollHeight) + "px"; }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
                placeholder={t("placeholder")}
                rows={1}
                className="ca-scroll w-full resize-none border-none bg-transparent px-3 pb-[6px] pt-[10px] text-[15px] leading-[1.5] text-fg-primary outline-none"
                style={{ minHeight: 30, maxHeight: 160 }}
              />
              <div className="flex items-end justify-between gap-2 px-1 pl-[6px]">
                {/* left: model picker (opens upward) + thinking toggle */}
                <div className="flex min-w-0 items-center gap-1">
                  <div className="relative">
                    <button onClick={() => setModelMenu((v) => !v)} className="flex cursor-pointer items-center gap-[7px] rounded-[9px] px-2 py-[6px] text-[12.5px] text-fg-secondary transition-colors hover:bg-elevated-2">
                      <svg viewBox="0 0 56 56" width="15" height="15"><path d="M 6,38 A 22,22 0 0,1 50,38" fill="none" stroke="var(--ca-logo)" strokeWidth="5" strokeLinecap="round" /><path d="M 15,38 A 13,13 0 0,1 41,38" fill="none" stroke="var(--ca-logo)" strokeWidth="5" strokeLinecap="round" opacity="0.45" /><circle cx="28" cy="38" r="4.5" fill="var(--ca-logo)" /></svg>
                      <span className="max-w-[150px] truncate" style={{ fontFamily: "var(--font-mono)" }}>{selectedModel?.display_name ?? modelId ?? "…"}</span>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--fg-tertiary)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg>
                    </button>
                    {modelMenu && (
                      <>
                        <div onClick={() => setModelMenu(false)} className="fixed inset-0 z-[25]" />
                        <div className="absolute bottom-[calc(100%+8px)] left-0 z-40 w-[320px] animate-fadeup rounded-xl border border-line-default bg-elevated p-[6px] shadow-lg">
                          <div className="px-[10px] pb-[6px] pt-2 text-[11px] uppercase tracking-[0.08em] text-fg-tertiary">{t("modelLabel")}</div>
                          {models.map((m) => (
                            <button key={m.id} onClick={() => { setModelId(m.id); setModelMenu(false); }} className="flex w-full cursor-pointer items-start gap-[10px] rounded-[10px] border-none bg-transparent p-[10px] text-left transition-colors hover:bg-elevated-2">
                              <div className="w-4 shrink-0 pt-[2px]">
                                {m.id === modelId && <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--brand-orange-hi)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[13px] text-fg-primary" style={{ fontFamily: "var(--font-mono)" }}>{m.display_name}</span>
                                  {m.tags[0] && <span className="rounded-full border px-[7px] py-[2px] text-[10px]" style={{ fontFamily: "var(--font-mono)", background: "var(--brand-orange-tint)", color: "var(--brand-orange-hi)", borderColor: "rgba(70,192,136,0.22)" }}>{m.tags[0]}</span>}
                                </div>
                                {m.description && <div className="mt-[3px] text-[12px] leading-[1.4] text-fg-tertiary">{m.description}</div>}
                              </div>
                            </button>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                  {selectedModel?.supports_thinking && (
                    <button
                      onClick={() => setThinking((v) => !v)}
                      title={t("thinking")}
                      aria-pressed={thinking}
                      className="flex shrink-0 cursor-pointer items-center gap-[6px] rounded-[9px] border px-[10px] py-[6px] text-[12.5px] transition-colors"
                      style={thinking
                        ? { borderColor: "var(--brand-orange)", background: "var(--brand-orange-tint)", color: "var(--brand-orange-hi)" }
                        : { borderColor: "var(--border-subtle)", color: "var(--fg-tertiary)" }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.5.5 1 1.2 1 2V16h6v-.5c0-.8.5-1.5 1-2A6 6 0 0 0 12 3z" /></svg>
                      <span>{t("thinking")}</span>
                    </button>
                  )}
                </div>
                {/* right: attach + send/stop */}
                <div className="flex shrink-0 items-center gap-1">
                  <button title={t("attachSoon")} aria-label={t("attach")} disabled className={`${iconBtn} cursor-not-allowed opacity-40`}>
                    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.5L12.5 21a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7L10 18a1.6 1.6 0 0 1-2.3-2.3l7.8-7.8" /></svg>
                  </button>
                  {streaming ? (
                    <button onClick={stop} aria-label={tc("stop")} className="inline-flex h-[38px] w-[38px] items-center justify-center rounded-[11px] border-none" style={{ background: "var(--bg-elevated-2)", color: "var(--fg-primary)", cursor: "pointer" }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
                    </button>
                  ) : (
                    <button onClick={() => void send()} aria-label={tc("send")} disabled={!input.trim()} className="inline-flex h-[38px] w-[38px] items-center justify-center rounded-[11px] transition-colors" style={{ background: input.trim() ? "var(--brand-orange)" : "var(--bg-elevated-2)", color: input.trim() ? "#fff" : "var(--fg-quaternary)", cursor: input.trim() ? "pointer" : "default" }}>
                      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
                    </button>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-[9px] text-center text-[11.5px] text-fg-quaternary">{t("hint")}</div>
          </div>
        </div>
      </section>
      </main>
    </>
  );
}
