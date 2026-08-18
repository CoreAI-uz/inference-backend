import type { Metadata } from "next";

import { ChatApp } from "@/components/chat/ChatApp";

export const metadata: Metadata = {
  title: "CoreAI Chat",
  description: "Chat with open models running on CoreAI infrastructure in Uzbekistan.",
  robots: { index: false, follow: false },
};

export default function ChatPage() {
  return <ChatApp />;
}
