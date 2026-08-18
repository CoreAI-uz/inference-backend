"use client";

import Script from "next/script";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  authenticateWithGoogle,
  getAuthProviders,
  linkGoogleIdentity,
} from "@/lib/api/resources";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(options: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
          }): void;
          renderButton(
            element: HTMLElement,
            options: {
              type: "standard";
              theme: "outline";
              size: "large";
              shape: "pill";
              text: "continue_with";
              width: number;
            },
          ): void;
        };
      };
    };
  }
}

export function GoogleSignInButton({
  next = "/",
  intent = "signin",
  onLinked,
}: {
  next?: string;
  intent?: "signin" | "link";
  onLinked?: () => void;
}) {
  const t = useTranslations("auth");
  const router = useRouter();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getAuthProviders()
      .then((providers) => {
        if (active && providers.google.enabled && providers.google.client_id) {
          setClientId(providers.google.client_id);
        }
      })
      .catch(() => {
        // Email/password remains available when the provider configuration cannot load.
      });
    return () => {
      active = false;
    };
  }, []);

  const receiveCredential = useCallback(
    async (response: { credential?: string }) => {
      if (!response.credential || busy) return;
      setBusy(true);
      setError(null);
      setSuccess(null);
      try {
        if (intent === "link") {
          await linkGoogleIdentity(response.credential);
          setSuccess(t("googleConnected"));
          setBusy(false);
          onLinked?.();
          return;
        }
        const result = await authenticateWithGoogle(response.credential);
        if (result.status === "registration_required") {
          const completionPath =
            next === "/"
              ? "/register/google"
              : `/register/google?next=${encodeURIComponent(next)}`;
          router.push(completionPath);
        } else {
          router.push(next);
        }
        router.refresh();
      } catch (err) {
        if (err instanceof ApiError && err.code === "account_link_required") {
          setError(t("googleExistingAccount"));
        } else if (err instanceof ApiError && err.code === "identity_already_linked") {
          setError(t("googleAlreadyConnected"));
        } else {
          setError(t("googleError"));
        }
        setBusy(false);
      }
    },
    [busy, intent, next, onLinked, router, t],
  );

  const renderGoogleButton = useCallback(() => {
    if (!clientId || !buttonRef.current || !window.google) return;
    buttonRef.current.replaceChildren();
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: receiveCredential,
      auto_select: false,
      cancel_on_tap_outside: true,
    });
    window.google.accounts.id.renderButton(buttonRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      shape: "pill",
      text: "continue_with",
      width: Math.min(372, buttonRef.current.clientWidth),
    });
  }, [clientId, receiveCredential]);

  useEffect(() => {
    renderGoogleButton();
  }, [renderGoogleButton]);

  if (!clientId) return null;

  return (
    <div className="mb-5">
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onReady={renderGoogleButton}
        onError={() => setError(t("googleError"))}
      />
      <div className={busy ? "pointer-events-none opacity-60" : undefined}>
        <div ref={buttonRef} className="flex min-h-[44px] w-full justify-center" />
      </div>
      {error && <div role="alert" className="mt-3 text-[13.5px]" style={{ color: "var(--status-info)" }}>{error}</div>}
      {success && <div role="status" className="mt-3 text-[13.5px] text-fg-secondary">{success}</div>}
      {intent === "signin" && (
        <div className="mt-5 flex items-center gap-3 text-[12px] text-fg-quaternary">
          <span className="h-px flex-1 bg-line-subtle" />
          <span>{t("orEmail")}</span>
          <span className="h-px flex-1 bg-line-subtle" />
        </div>
      )}
    </div>
  );
}
