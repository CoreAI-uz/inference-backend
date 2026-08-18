import type { Metadata } from "next";

import { GoogleRegistrationForm } from "@/components/auth/GoogleRegistrationForm";
import { ProductHeader } from "@/components/auth/ProductHeader";
import { safeReturnPath } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Complete your account — CoreAI",
  robots: { index: false, follow: false },
};

export default async function GoogleRegistrationPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const next = safeReturnPath((await searchParams).next);
  return (
    <>
      <ProductHeader />
      <GoogleRegistrationForm next={next} />
    </>
  );
}
