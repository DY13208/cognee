"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

const SECTIONS = [
  { title: "whatReads", body: "whatReadsBody" },
  { title: "switchingOn", body: "switchingOnBody" },
  { title: "whereEnds", body: "whereEndsBody" },
  { title: "whoCanAsk", body: "whoCanAskBody" },
  { title: "howToAsk", body: "howToAskBody" },
  { title: "rememberOne", body: "rememberOneBody" },
  { title: "switchingOff", body: "switchingOffBody" },
  { title: "needsReconnect", body: "needsReconnectBody" },
  { title: "whoControls", body: "whoControlsBody" },
] as const;

export default function SlackGuide(): ReactElement {
  const t = useTranslations("integrations.slackGuide");

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-8 pt-6 pb-10">
        <div>
          <Link href="/integrations" className="text-[13px] text-[var(--color-cognee-fg,#EDECEA)]/55 hover:text-[var(--color-cognee-fg,#EDECEA)]">
            {t("back")}
          </Link>
          <h1 className="mt-3 mb-1 text-[18px] font-bold tracking-[-0.01em] text-[var(--color-cognee-fg,#EDECEA)]">
            {t("title")}
          </h1>
          <p className="m-0 text-[14px] text-[var(--color-cognee-fg,#EDECEA)]/55">
            {t("subtitle")}
          </p>
        </div>

        <div className="flex flex-col gap-4">
          {SECTIONS.map((section) => (
            <section
              key={section.title}
              className="rounded-xl border border-white/10 bg-white/[0.06] p-5"
            >
              <h2 className="m-0 mb-1.5 text-[14px] font-semibold text-[var(--color-cognee-fg,#EDECEA)]">
                {t(section.title)}
              </h2>
              <p className="m-0 text-[13px] leading-[1.6] text-[var(--color-cognee-fg,#EDECEA)]/55">{t(section.body)}</p>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
