declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const SIGNUP_CONVERSION = "AW-18402777257/tL5LCLuxg-YcEKmxkMdE";
const API_KEY_CONVERSION = "AW-18402777257/DMMxCL6xg-YcEKmxkMdE";
const CHAT_STARTED_CONVERSION = "AW-18402777257/G9oACLnXh-YcEKmxkMdE";

function sendConversion(sendTo: string | undefined) {
  if (!sendTo || typeof window === "undefined") return;
  window.gtag?.("event", "conversion", { send_to: sendTo });
}

export function trackSignupConversion() {
  sendConversion(SIGNUP_CONVERSION);
}

export function trackApiKeyConversion() {
  sendConversion(API_KEY_CONVERSION);
}

export function trackChatStartedConversion() {
  sendConversion(CHAT_STARTED_CONVERSION);
}

export {};
