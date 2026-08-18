import type { Metadata } from "next";

import { ChatApp } from "@/components/chat/ChatApp";

export const metadata: Metadata = {
  title: "Conversation — CoreAI Chat",
  robots: { index: false, follow: false },
};

export default async function ChatConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ChatApp initialConversationId={id} />;
}
