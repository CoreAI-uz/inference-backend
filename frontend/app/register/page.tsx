import type { Metadata } from "next";

import { AuthForm } from "@/components/auth/AuthForm";
import { ProductHeader } from "@/components/auth/ProductHeader";
import { safeReturnPath } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Create an account — CoreAI",
  robots: { index: false, follow: false },
};

export default async function RegisterPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const next = safeReturnPath((await searchParams).next);
  return (
    <>
      <ProductHeader />
      <AuthForm mode="register" next={next} />
    </>
  );
}
