import type { Metadata } from "next";

import { OnboardingForm } from "@/components/auth/OnboardingForm";
import { ProductHeader } from "@/components/auth/ProductHeader";
import { safeReturnPath } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Complete your profile — CoreAI",
  robots: { index: false, follow: false },
};

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const next = safeReturnPath((await searchParams).next);
  return (
    <>
      <ProductHeader />
      <OnboardingForm next={next} />
    </>
  );
}
