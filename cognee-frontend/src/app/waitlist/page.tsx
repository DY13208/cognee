import TextLogo from "@/ui/app/logo/TextLogo";
import { getMessages } from "@/i18n/getMessages";
import { getRequestLocale } from "@/i18n/getRequestLocale";

export const dynamic = "force-dynamic";

export default async function WaitlistPage() {
  const locale = await getRequestLocale();
  const waitlist = (getMessages(locale) as typeof import("@/i18n/messages/zh-CN.json")).waitlist;

  return (
    <div
      className="relative h-screen overflow-hidden text-[#EDECEA] flex items-center justify-center"
      style={{
        backgroundColor: "#000000",
        backgroundImage:
          "linear-gradient(rgba(244,244,244,0.10) 1px, transparent 1px), linear-gradient(90deg, rgba(244,244,244,0.10) 1px, transparent 1px)",
        backgroundSize: "33px 33px",
      }}
    >
      <div className="relative z-10 flex flex-col items-center text-center max-w-lg px-8 gap-8">
        <TextLogo width={140} height={39} color="#EDECEA" />

        <div className="flex flex-col gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">{waitlist.title}</h1>
          <p className="text-[#A09F9D] text-base leading-relaxed">
            {waitlist.body}
          </p>
          <p className="text-[#A09F9D] text-base">
            {waitlist.thanks}
          </p>
        </div>

        <a
          href="/api/signout"
          className="text-sm text-[#A09F9D] underline underline-offset-4 hover:text-[#EDECEA] transition-colors"
        >
          {waitlist.signOut}
        </a>
      </div>
    </div>
  );
}
