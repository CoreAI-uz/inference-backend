import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ApiDocs } from "@/components/docs/ApiDocs";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("docs");

  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: true, follow: true },
  };
}

export default function DocsPage() {
  return <ApiDocs />;
}
