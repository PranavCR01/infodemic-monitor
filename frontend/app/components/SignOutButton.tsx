"use client";

import { useRouter } from "next/navigation";
import { getBrowserClient } from "../../lib/supabase";

export function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    const supabase = getBrowserClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <button
      onClick={handleSignOut}
      className="text-sm text-gray-500 hover:text-gray-900 transition-colors"
    >
      Sign out
    </button>
  );
}
