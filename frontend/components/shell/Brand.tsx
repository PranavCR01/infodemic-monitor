import Link from "next/link";

export function Brand({ inverted = false, href = "/" }: { inverted?: boolean; href?: string }) {
  return (
    <Link href={href} className={`flex items-center gap-2.5 font-semibold no-underline ${inverted ? "text-[#E8ECF3]" : "text-ink"}`}>
      <span
        aria-hidden="true"
        className={`grid h-7 w-7 place-items-center rounded-md font-serif text-[15px] font-bold ${
          inverted ? "bg-bg text-[#14213D]" : "bg-ink text-bg"
        }`}
      >
        IM
      </span>
      <span>
        Infodemic Monitor{" "}
        <span className={`font-normal ${inverted ? "text-[#A9B3C6]" : "text-ink-3"}`}>· WHO research</span>
      </span>
    </Link>
  );
}
