import type { Metadata } from "next";

import { ChatApp } from "@/components/chat/ChatApp";

export const metadata: Metadata = {
  title: "CoreAI Chat",
  description: "Chat with open models for writing, translation, analysis, reasoning, and code.",
  robots: { index: false, follow: false },
};

export default function ChatPage() {
  return <ChatApp />;
}
