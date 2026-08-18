import type { Config } from "tailwindcss";

// Colors reference CSS variables (defined in globals.css) so light/dark theming is a
// single [data-theme] swap on <html>. Values come from the CoreAI design system.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--bg-page)",
        elevated: "var(--bg-elevated)",
        "elevated-2": "var(--bg-elevated-2)",
        inset: "var(--bg-inset)",
        fg: {
          DEFAULT: "var(--fg-primary)",
          primary: "var(--fg-primary)",
          secondary: "var(--fg-secondary)",
          tertiary: "var(--fg-tertiary)",
          quaternary: "var(--fg-quaternary)",
        },
        orange: {
          DEFAULT: "var(--brand-orange)",
          hi: "var(--brand-orange-hi)",
          deep: "var(--brand-orange-deep)",
          tint: "var(--brand-orange-tint)",
        },
        line: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
        },
        status: {
          info: "var(--status-info)",
          online: "var(--status-online)",
        },
        logo: "var(--ca-logo)",
      },
      fontFamily: {
        body: "var(--font-body)",
        display: "var(--font-display)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
        xl: "18px",
        "2xl": "24px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
      },
      maxWidth: {
        chat: "760px",
      },
      keyframes: {
        blink: { "0%,49%": { opacity: "1" }, "50%,100%": { opacity: "0" } },
        fadeup: { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "none" } },
        sheetup: { from: { transform: "translateY(100%)" }, to: { transform: "none" } },
      },
      animation: {
        blink: "blink 1s step-end infinite",
        fadeup: "fadeup 320ms cubic-bezier(0.16,1,0.3,1)",
        sheetup: "sheetup 240ms cubic-bezier(0.16,1,0.3,1)",
      },
    },
  },
  plugins: [],
};

export default config;
