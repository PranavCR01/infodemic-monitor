import type { Metadata } from "next";
import { Brand } from "@/components/shell/Brand";
import { safeNext } from "@/lib/auth/roles";
import { CALLBACK_ERRORS } from "@/lib/auth/messages";
import { SignInForm } from "./SignInForm";

export const metadata: Metadata = { title: "Sign in · WHO Infodemic Monitor" };

// SignIn.dc.html: navy brand panel on the left, a 400 px form on the right.
export default function SignInPage({ searchParams }: { searchParams: { next?: string; error?: string } }) {
  const next = safeNext(searchParams.next);
  const notice = searchParams.error ? CALLBACK_ERRORS[searchParams.error] ?? null : null;
  return (
    <div className="flex min-h-screen flex-wrap">
      <section className="flex min-h-[320px] flex-[1_1_480px] flex-col justify-between gap-12 bg-[#14213D] px-6 py-12 text-[#E8ECF3] md:px-14">
        <Brand inverted />
        <div className="flex max-w-[520px] flex-col gap-4">
          <h1 className="font-serif text-[32px] font-semibold leading-[40px] text-white md:text-[40px] md:leading-[48px]">
            Check what health videos claim, against what the evidence shows.
          </h1>
          <p className="text-[16px] leading-[26px] text-[#C9D2E3]">
            Every label links back to the claim, the speaker&apos;s exact words and the published sources behind it.
          </p>
        </div>
        <p className="text-small text-[#A9B3C6]">A research tool used with the World Health Organization. Access is by invitation.</p>
      </section>
      <main className="grid flex-[1_1_520px] place-items-center px-6 py-12">
        <SignInForm next={next} notice={notice} />
      </main>
    </div>
  );
}
