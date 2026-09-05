export type ReasoningEffort = "none" | "low" | "medium" | "xhigh";

export interface ModelInfo {
  id: string;
  display_name: string;
  description: string | null;
  tags: string[];
  supports_thinking: boolean;
  reasoning_mode?: "effort" | "toggle";
  supports_tools: boolean;
  reasoning_efforts: ReasoningEffort[];
  default_reasoning_effort: ReasoningEffort;
}

export interface UserOut {
  id: string;
  email: string;
  display_name: string | null;
  locale: string;
  email_verified: boolean;
  onboarding_status: OnboardingStatus;
}

export type OnboardingStatus = "not_started" | "completed" | "skipped";

export type RoleCode =
  | "software_developer"
  | "ml_data_specialist"
  | "researcher"
  | "student"
  | "educator"
  | "business_owner_founder"
  | "product_business"
  | "marketing_content"
  | "government_public_sector"
  | "other";

export type IntendedUseCode =
  | "general_assistant"
  | "writing_translation"
  | "programming"
  | "data_analysis"
  | "research_education"
  | "api_application"
  | "business_workflows"
  | "model_evaluation"
  | "other";

export interface UserProfile {
  display_name: string | null;
  role: RoleCode | null;
  intended_uses: IntendedUseCode[];
  organization_name: string | null;
  onboarding_status: OnboardingStatus;
  onboarding_version: number;
  completed_at: string | null;
  skipped_at: string | null;
}

export interface AuthProviders {
  google: {
    enabled: boolean;
    client_id: string | null;
  };
}

export interface GoogleAuthResult {
  status: "authenticated" | "registration_required";
  me: Me | null;
  email: string | null;
  display_name: string | null;
}

export interface GooglePendingRegistration {
  email: string;
  display_name: string;
}

export interface AuthMethods {
  password_enabled: boolean;
  identities: Array<{
    provider: string;
    email: string | null;
    created_at: string;
  }>;
}

export interface Me {
  user: UserOut | null;
  is_anon: boolean;
  session_id: string;
  usage: { chat_messages: number; tokens_in: number; tokens_out: number };
  limits: {
    chat_cap: number;
    chat_remaining: number;
    next_message_in: number;
    is_registered: boolean;
  };
  legal_terms_accepted: boolean;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  last_four: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
}

export interface CreatedApiKey extends ApiKeyInfo {
  key: string;
}

export interface UsageTotals {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  reasoning_tokens: number;
}

export interface UsageBySource extends UsageTotals {
  source: string;
}

export interface UsageByModel extends UsageTotals {
  model: string;
}

export interface DeveloperUsage {
  period_start: string;
  lifetime: UsageTotals;
  last_24_hours: UsageTotals;
  by_source: UsageBySource[];
  by_model: UsageByModel[];
}

export interface ConversationListItem {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface MessageOut {
  id: string;
  parent_id: string | null;
  active_child_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  reasoning: string | null;
  reasoning_ms: number | null;
  model: string | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  model: string;
  created_at: string;
  updated_at: string;
  active_child_id: string | null;
  messages: MessageOut[];
}

export interface ChatRequestMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

// Named SSE events the backend emits (see backend gateway/events.py).
export type ChatEvent =
  | { type: "delta"; content: string; role?: string }
  | { type: "reasoning"; content: string }
  | { type: "queued"; position?: number; message?: string }
  | { type: "usage"; prompt_tokens: number; completion_tokens: number; total_tokens: number; cached_input_tokens?: number; reasoning_tokens?: number }
  | { type: "title"; conversation_id: string; title: string }
  | { type: "done"; conversation_id?: string | null; message_id?: string | null; finish_reason: string; title?: string | null }
  | { type: "error"; code: string; message: string; retry_after?: number };
