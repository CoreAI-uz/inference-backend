// Per-domain API modules (models, conversations, auth), all over the typed client.

import { api } from "./client";
import type {
  ApiKeyInfo,
  AuthProviders,
  AuthMethods,
  ConversationDetail,
  ConversationListItem,
  CreatedApiKey,
  DeveloperUsage,
  GoogleAuthResult,
  GooglePendingRegistration,
  IntendedUseCode,
  Me,
  ModelInfo,
  RoleCode,
  UserProfile,
} from "./types";

export const getModels = () => api<ModelInfo[]>("/api/models");

export const getMe = () => api<Me>("/api/auth/me");

export const getAuthProviders = () => api<AuthProviders>("/api/auth/providers");

export const authenticateWithGoogle = (credential: string) =>
  api<GoogleAuthResult>("/api/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });

export const getPendingGoogleRegistration = () =>
  api<GooglePendingRegistration>("/api/auth/google/pending");

export const getAuthMethods = () => api<AuthMethods>("/api/auth/identities");

export const linkGoogleIdentity = (credential: string) =>
  api<{ provider: string; email: string }>("/api/auth/identities/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });

export const unlinkGoogleIdentity = () =>
  api<void>("/api/auth/identities/google", { method: "DELETE" });

export const completeGoogleRegistration = (
  displayName: string,
  locale: string,
  legalTermsAccepted: boolean,
) =>
  api<Me>("/api/auth/google/complete-registration", {
    method: "POST",
    body: JSON.stringify({
      display_name: displayName,
      locale,
      legal_terms_accepted: legalTermsAccepted,
    }),
  });

export const register = (
  displayName: string,
  email: string,
  password: string,
  locale: string,
  legalTermsAccepted: boolean,
) =>
  api<Me>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      display_name: displayName,
      email,
      password,
      locale,
      legal_terms_accepted: legalTermsAccepted,
    }),
  });

export const login = (email: string, password: string) =>
  api<Me>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const logout = () => api<void>("/api/auth/logout", { method: "POST" });

export const getProfile = () => api<UserProfile>("/api/auth/profile");

export const completeOnboarding = (
  role: RoleCode,
  intendedUses: IntendedUseCode[],
  organizationName: string | null,
) =>
  api<UserProfile>("/api/auth/onboarding", {
    method: "POST",
    body: JSON.stringify({
      role,
      intended_uses: intendedUses,
      organization_name: organizationName,
    }),
  });

export const skipOnboarding = () =>
  api<UserProfile>("/api/auth/onboarding/skip", { method: "POST" });

export const updateProfile = (profile: {
  display_name: string;
  role?: RoleCode;
  intended_uses?: IntendedUseCode[];
  organization_name?: string | null;
}) =>
  api<UserProfile>("/api/auth/profile", {
    method: "PATCH",
    body: JSON.stringify(profile),
  });

export const acceptLegalTerms = () =>
  api<{ accepted: boolean; policy_version: string }>("/api/auth/legal-acceptance", {
    method: "POST",
    body: JSON.stringify({ accepted: true }),
  });

export const listApiKeys = () => api<ApiKeyInfo[]>("/api/developer/keys");

export const createApiKey = (name: string) =>
  api<CreatedApiKey>("/api/developer/keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const revokeApiKey = (id: string) =>
  api<void>(`/api/developer/keys/${id}`, { method: "DELETE" });

export const getDeveloperUsage = () => api<DeveloperUsage>("/api/developer/usage");

export const listConversations = () => api<ConversationListItem[]>("/api/conversations");

export const getConversation = (id: string) =>
  api<ConversationDetail>(`/api/conversations/${id}`);

export const renameConversation = (id: string, title: string) =>
  api<ConversationDetail>(`/api/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export const deleteConversation = (id: string) =>
  api<void>(`/api/conversations/${id}`, { method: "DELETE" });

// Persist a branch switch so the selected version survives a reload.
export const selectVersion = (id: string, messageId: string) =>
  api<void>(`/api/conversations/${id}/select`, {
    method: "POST",
    body: JSON.stringify({ message_id: messageId }),
  });

// Delete a message version and its subtree.
export const deleteMessage = (id: string, messageId: string) =>
  api<void>(`/api/conversations/${id}/messages/${messageId}`, { method: "DELETE" });
