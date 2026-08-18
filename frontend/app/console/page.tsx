import type { Metadata } from "next";

import { DeveloperConsole } from "@/components/developer/DeveloperConsole";

export const metadata: Metadata = {
  title: "API console — CoreAI",
  description: "Manage CoreAI API keys and inspect account usage.",
  robots: { index: false, follow: false },
};

export default function DeveloperPage() {
  return <DeveloperConsole />;
}
