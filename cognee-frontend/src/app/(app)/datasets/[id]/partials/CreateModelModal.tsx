"use client";

import type { ReactElement } from "react";
import { Loader } from "@mantine/core";
import { useTranslations } from "next-intl";
import ModalShell from "@/ui/elements/ModalShell";

export default function CreateModelModal({
  inferring,
  filesCount,
  onInfer,
  onBlank,
  onCancel,
}: {
  inferring: boolean;
  filesCount: number;
  onInfer: () => void;
  onBlank: () => void;
  onCancel: () => void;
}): ReactElement {
  const t = useTranslations("datasets");
  return (
    <ModalShell width={440} onClose={() => { if (!inferring) onCancel(); }}>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: "#EDECEA", margin: 0 }}>{t("createModel.title")}</h2>
      {inferring ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "24px 0" }}>
          <Loader size={24} color="#6510F4" />
          <span style={{ fontSize: 14, color: "#6510F4", fontWeight: 500 }}>{t("createModel.inferring")}</span>
          <span style={{ fontSize: 12, color: "rgba(237,236,234,0.55)" }}>{t("createModel.wait")}</span>
        </div>
      ) : (
        <>
          <p style={{ fontSize: 13, color: "rgba(237,236,234,0.55)", margin: 0, lineHeight: "20px" }}>
            {t("createModel.description")}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button
              onClick={onInfer}
              disabled={filesCount === 0}
              className="cursor-pointer hover:bg-white/10"
              style={{ display: "flex", alignItems: "center", gap: 12, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "14px 16px", textAlign: "left", fontFamily: "inherit", opacity: filesCount === 0 ? 0.5 : 1 }}
            >
              <div style={{ width: 36, height: 36, background: "rgba(188,155,255,0.20)", border: "1px solid rgba(188,155,255,0.35)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6510F4" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 500, color: "#EDECEA" }}>{t("createModel.inferFromData")}</span>
                <span style={{ fontSize: 12, color: "rgba(237,236,234,0.55)" }}>
                  {filesCount === 0 ? t("createModel.noFiles") : t("createModel.analyzeFiles", { count: filesCount })}
                </span>
              </div>
            </button>
            <button
              onClick={onBlank}
              className="cursor-pointer hover:bg-white/10"
              style={{ display: "flex", alignItems: "center", gap: 12, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "14px 16px", textAlign: "left", fontFamily: "inherit" }}
            >
              <div style={{ width: 36, height: 36, background: "rgba(255,255,255,0.06)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(237,236,234,0.55)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 500, color: "#EDECEA" }}>{t("createModel.startBlank")}</span>
                <span style={{ fontSize: 12, color: "rgba(237,236,234,0.55)" }}>{t("createModel.startBlankHint")}</span>
              </div>
            </button>
          </div>
          <button
            onClick={onCancel}
            className="cursor-pointer"
            style={{ background: "none", border: "none", fontSize: 13, color: "rgba(237,236,234,0.55)", fontFamily: "inherit", padding: "4px 0" }}
          >
            {t("common.cancel")}
          </button>
        </>
      )}
    </ModalShell>
  );
}
