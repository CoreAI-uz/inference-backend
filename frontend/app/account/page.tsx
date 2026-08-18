import type { Metadata } from "next";

import { AccountSettings } from "@/components/account/AccountSettings";
import { ProductHeader } from "@/components/auth/ProductHeader";

export const metadata: Metadata = {
  title: "Account settings — CoreAI",
  robots: { index: false, follow: false },
};

export default function AccountPage() {
  return (
    <>
      <ProductHeader />
      <AccountSettings />
    </>
  );
}
