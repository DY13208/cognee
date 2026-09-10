"use client";

import { useCallback, useEffect, useState, type ReactElement } from "react";
import Link from "next/link";
import { Loader } from "@mantine/core";
import { useTranslations } from "next-intl";
import getConnectionStatus from "@/modules/integrations/getConnectionStatus";
import linkSlackAccount from "@/modules/integrations/linkSlackAccount";
import { useTenant } from "@/modules/tenant/TenantContext";
import { teamIdFromLinkCode } from "@/modules/integrations/teamIdFromLinkCode";

const CARD = "rounded-xl border border-white/10 bg-white/[0.06] p-6";
const PRIMARY =
  "cursor-pointer rounded-lg border-none bg-cognee-purple px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-cognee-purple-hover disabled:cursor-default disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cognee-lavender/70 focus-visible:ring-offset-2 focus-visible:ring-offset-black";
const LINK = "text-cognee-lavender underline underline-offset-2";

type Phase = "checking" | "ready" | "wrongWorkspace" | "notConnected" | "linking" | "done";

interface LinkSlackPageProps {
  /** The signed code from /cognee-link; empty when the page was opened directly. */
  code: string;
}

/**
 * Confirmation step for `/cognee-link` (CLO-390). Slack sends the member here
 * because a browser session is what proves who they are; the code only says
 * which Slack member is asking.
 *
 * The workspace is checked before offering the button: the backend takes
 * `tenant_id` from this request without verifying it owns the Slack install the
 * code came from, so confirming under the wrong active workspace would mint a
 * key against a workspace that has nothing to do with that Slack team.
 */
export default function LinkSlackPage({ code }: LinkSlackPageProps): ReactElement {
  const t = useTranslations("integrations.linkSlack");
  const { tenant, availableTenants } = useTenant();
  const tenantId = tenant?.tenant_id ?? null;
  // Same derivation the top bar uses: the tenant list carries the display name,
  // and the active tenant's own name is the fallback before that list resolves.
  const workspaceName =
    availableTenants.find((item) => item.id === tenantId)?.name ?? tenant?.tenant_name ?? t("thisWorkspace");
  const [phase, setPhase] = useState<Phase>("checking");
  const [failed, setFailed] = useState(false);

  const codeTeamId = teamIdFromLinkCode(code);

  useEffect(() => {
    if (!tenantId || !codeTeamId) return;
    let cancelled = false;
    void (async () => {
      const status = await getConnectionStatus("slack", tenantId);
      if (cancelled) return;
      if (!status.connected) setPhase("notConnected");
      else if (status.accountId !== codeTeamId) setPhase("wrongWorkspace");
      else setPhase("ready");
    })();
    return () => {
      cancelled = true;
    };
  }, [tenantId, codeTeamId]);

  const confirm = useCallback(async () => {
    if (!tenantId) return;
    setPhase("linking");
    setFailed(false);
    const result = await linkSlackAccount(tenantId, code);
    if (result.success) {
      setPhase("done");
      return;
    }
    setFailed(true);
    setPhase("ready");
  }, [tenantId, code]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-[560px] px-8 pt-10 pb-10">
        <div className={CARD}>
          <h1 className="m-0 mb-2 text-[18px] font-bold tracking-[-0.01em] text-[var(--color-cognee-fg,#EDECEA)]">
            {t("title")}
          </h1>

          {!codeTeamId ? (
            <p className="m-0 text-[13px] leading-[1.6] text-[var(--color-cognee-fg,#EDECEA)]/55">
              {t("invalid")}
            </p>
          ) : phase === "done" ? (
            <div>
              <p className="m-0 mb-4 text-[13px] leading-[1.6] text-[var(--color-cognee-fg,#EDECEA)]/55">
                Done. <code>/cognee-recall</code> in Slack now answers as you, from what your Cognee
                account can see.
              </p>
              <Link href="/integrations" className={LINK}>
                {t("back")}
              </Link>
            </div>
          ) : phase === "checking" ? (
            <p className="m-0 flex items-center gap-2 text-[13px] text-[var(--color-cognee-fg,#EDECEA)]/55">
              <Loader size={14} color="#BC9BFF" />
              {t("checking")}
            </p>
          ) : phase === "notConnected" ? (
            <p className="m-0 text-[13px] leading-[1.6] text-[var(--color-cognee-fg,#EDECEA)]/55">
              {t("notConnected")}
            </p>
          ) : phase === "wrongWorkspace" ? (
            <p className="m-0 text-[13px] leading-[1.6] text-[var(--color-cognee-warning,#F59E0B)]">
              {t("wrongWorkspace")}
            </p>
          ) : (
            <div>
              <p className="m-0 mb-4 text-[13px] leading-[1.6] text-[var(--color-cognee-fg,#EDECEA)]/55">
                This connects your Slack member account to your Cognee account in{" "}
                <strong className="font-semibold text-[var(--color-cognee-fg,#EDECEA)]">{workspaceName}</strong>. After that,{" "}
                <code>/cognee-recall</code> answers as you and only from what your account can see.
                Nobody else in Slack can use your link.
              </p>
              {failed && <p className="m-0 mb-3 text-[13px] text-[var(--color-cognee-danger-fg,#FF8A8A)]">{t("failed")}</p>}
              <button onClick={() => void confirm()} disabled={phase === "linking"} className={PRIMARY}>
                {phase === "linking" ? t("connecting") : t("connectMine")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
