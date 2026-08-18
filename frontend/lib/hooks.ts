"use client";

import { useCallback, useEffect, useState } from "react";

import { getMe, getModels, listConversations } from "./api/resources";
import type { ConversationListItem, Me, ModelInfo } from "./api/types";

export function useMe() {
  const [me, setMe] = useState<Me | null>(null);
  const refresh = useCallback(async () => {
    try {
      setMe(await getMe());
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { me, refresh };
}

export function useModels() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  useEffect(() => {
    getModels()
      .then(setModels)
      .catch(() => {});
  }, []);
  return models;
}

export function useConversations(enabled: boolean) {
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const refresh = useCallback(async () => {
    if (!enabled) {
      setConversations([]);
      return;
    }
    try {
      setConversations(await listConversations());
    } catch {
      /* ignore */
    }
  }, [enabled]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return { conversations, refresh };
}
