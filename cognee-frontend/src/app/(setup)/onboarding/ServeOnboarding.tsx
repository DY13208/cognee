"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useUser } from "@/modules/users/UserContext";
import searchDataset from "@/modules/datasets/searchDataset";
import { TrackPageView } from "@/modules/analytics";
import { completeOnboardingAndNavigate } from "./completeOnboardingAndNavigate";
import { useOnboardingTrackEvent } from "./useOnboardingTrackEvent";
import { StepBadge, StepDots } from "./partials/Shared";

const darkPage: React.CSSProperties = {
  backgroundColor: "#000000",
  backgroundImage: "linear-gradient(rgba(244,244,244,0.10) 1px, transparent 1px), linear-gradient(90deg, rgba(244,244,244,0.10) 1px, transparent 1px)",
  backgroundSize: "33px 33px",
};

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");
  return (
    <div style={{ position: "relative", background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "16px 20px", width: "100%", maxWidth: 520 }}>
      <pre style={{ margin: 0, fontSize: 13, color: "#E4E4E7", overflowX: "auto", whiteSpace: "pre-wrap" }}>
        <code>{code}</code>
      </pre>
      <button
        onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); track({ pageName: "Onboarding Serve", eventName: "serve_code_copied", additionalProperties: { snippet: code.slice(0, 30) } }); }}
        className="cursor-pointer"
        style={{ position: "absolute", top: 8, right: 8, background: "#27272A", border: "1px solid #3F3F46", borderRadius: 4, padding: "4px 8px", fontSize: 11, color: "rgba(237,236,234,0.65)" }}
      >
        {copied ? t("copied") : t("copy")}
      </button>
    </div>
  );
}

// Step 1: Verify connection
function ServeStep1({ onNext }: { onNext: () => void }) {
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");
  return (
    <div className="flex flex-col items-center gap-8 flex-1" style={{ paddingTop: 48, paddingBottom: 48, paddingInline: 80 }}>
      <div className="flex flex-col items-center gap-2">
        <StepBadge step={1} />
        <h1 style={{ fontSize: 28, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif', letterSpacing: "-0.02em" }}>{t("serve.connectedTitle")}</h1>
        <p style={{ fontSize: 15, color: "rgba(237,236,234,0.55)", margin: 0, textAlign: "center", lineHeight: "22px", maxWidth: 480 }}>
          {t("serve.connectedDescription")}
        </p>
      </div>

      <div style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.35)", borderRadius: 12, padding: "20px 24px", display: "flex", gap: 12, alignItems: "center", maxWidth: 480, width: "100%" }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4" stroke="#22C55E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="12" r="10" stroke="#22C55E" strokeWidth="2"/></svg>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#22C55E" }}>{t("serve.active")}</div>
          <div style={{ fontSize: 13, color: "rgba(34,197,94,0.8)" }}>{t("serve.activeDescription")}</div>
        </div>
      </div>

      <button onClick={() => { track({ pageName: "Onboarding Serve", eventName: "serve_step_completed", additionalProperties: { step: "1" } }); onNext(); }} className="cursor-pointer" style={{ background: "#BC9BFF", border: "none", borderRadius: 8, padding: "10px 24px", fontSize: 14, fontWeight: 500, color: "#1e1e1c" }}>
        {t("continue")}
      </button>
      <StepDots current={1} />
    </div>
  );
}

// Step 2: SDK quickstart
function ServeStep2({ onNext }: { onNext: () => void }) {
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");
  return (
    <div className="flex flex-col items-center gap-6 flex-1" style={{ paddingTop: 48, paddingBottom: 48, paddingInline: 80 }}>
      <div className="flex flex-col items-center gap-2">
        <StepBadge step={2} />
        <h1 style={{ fontSize: 28, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif', letterSpacing: "-0.02em" }}>{t("serve.quickstart")}</h1>
        <p style={{ fontSize: 15, color: "rgba(237,236,234,0.55)", margin: 0, textAlign: "center", lineHeight: "22px" }}>
          {t("serve.quickstartDescription")}
        </p>
      </div>

      <div className="flex flex-col gap-4 w-full items-center">
        <div style={{ width: "100%", maxWidth: 520 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(237,236,234,0.45)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("serve.store")}</div>
          <CodeBlock code={`import cognee\n\nawait cognee.serve()  # Already connected\n\nawait cognee.remember(\n    "Einstein developed general relativity in 1915.",\n    dataset_name="scientists"\n)`} />
        </div>

        <div style={{ width: "100%", maxWidth: 520 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(237,236,234,0.45)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("serve.query")}</div>
          <CodeBlock code={`results = await cognee.recall(\n    "What did Einstein develop?",\n    datasets=["scientists"]\n)\nprint(results)`} />
        </div>

        <div style={{ width: "100%", maxWidth: 520 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(237,236,234,0.45)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("serve.visualize")}</div>
          <CodeBlock code={`await cognee.visualize("graph.html")`} />
        </div>
      </div>

      <button onClick={() => { track({ pageName: "Onboarding Serve", eventName: "serve_step_completed", additionalProperties: { step: "2" } }); onNext(); }} className="cursor-pointer" style={{ background: "#BC9BFF", border: "none", borderRadius: 8, padding: "10px 24px", fontSize: 14, fontWeight: 500, color: "#1e1e1c" }}>
        {t("continue")}
      </button>
      <StepDots current={2} />
    </div>
  );
}

// Step 3: Test from UI
function ServeStep3({ onNext, cogniInstance }: {
  onNext: () => void;
  cogniInstance: NonNullable<ReturnType<typeof useCogniInstance>["cogniInstance"]>;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");
  const suggestions = [
    t("serve.suggestions.entities"),
    t("serve.suggestions.relationships"),
    t("serve.suggestions.summary"),
  ];

  const handleSearch = async (q: string) => {
    if (!q.trim()) return;
    track({ pageName: "Onboarding Serve", eventName: "serve_search_executed", additionalProperties: { query_length: String(q.length) } });
    setQuery(q);
    setIsSearching(true);
    setResults([]);
    try {
      const data = await searchDataset(cogniInstance, { query: q, searchType: "HYBRID_COMPLETION" });
      const texts: string[] = [];
      if (Array.isArray(data)) {
        for (const item of data) {
          if (Array.isArray(item.search_result)) {
            texts.push(...item.search_result);
          }
        }
      }
      setResults(texts.length > 0 ? texts : [t("serve.noResults")]);
    } catch {
      setResults([t("serve.searchFailed")]);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-6 flex-1" style={{ paddingTop: 48, paddingBottom: 48, paddingInline: 80 }}>
      <div className="flex flex-col items-center gap-2">
        <StepBadge step={3} />
        <h1 style={{ fontSize: 28, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif', letterSpacing: "-0.02em" }}>{t("serve.test")}</h1>
        <p style={{ fontSize: 15, color: "rgba(237,236,234,0.55)", margin: 0, textAlign: "center", lineHeight: "22px" }}>
          {t("serve.testDescription")}
        </p>
      </div>

      <div style={{ display: "flex", gap: 8, width: "100%", maxWidth: 520 }}>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSearch(query); }}
          placeholder={t("serve.placeholder")}
          style={{ flex: 1, padding: "10px 14px", border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.06)", color: "#EDECEA", borderRadius: 8, fontSize: 14, outline: "none" }}
        />
        <button onClick={() => handleSearch(query)} disabled={isSearching} className="cursor-pointer" style={{ background: "#BC9BFF", border: "none", borderRadius: 8, padding: "10px 20px", fontSize: 14, fontWeight: 500, color: "#1e1e1c", opacity: isSearching ? 0.6 : 1 }}>
          {isSearching ? "…" : t("serve.search")}
        </button>
      </div>

      <div className="flex gap-2 flex-wrap justify-center">
        {suggestions.map((s) => (
          <button key={s} onClick={() => { track({ pageName: "Onboarding Serve", eventName: "serve_suggestion_clicked", additionalProperties: { suggestion: s } }); handleSearch(s); }} className="cursor-pointer hover:bg-white/10" style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, padding: "6px 12px", fontSize: 12, color: "rgba(237,236,234,0.7)" }}>
            {s}
          </button>
        ))}
      </div>

      {results.length > 0 && (
        <div style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: 16, width: "100%", maxWidth: 520, maxHeight: 200, overflowY: "auto" }}>
          {results.map((r, i) => (
            <p key={i} style={{ margin: i > 0 ? "8px 0 0" : 0, fontSize: 14, color: "rgba(237,236,234,0.8)", lineHeight: 1.5 }}>{r}</p>
          ))}
        </div>
      )}

      <StepDots current={3} />

      <button onClick={() => { track({ pageName: "Onboarding Serve", eventName: "serve_step_completed", additionalProperties: { step: "3" } }); onNext(); }} className="cursor-pointer" style={{ background: "#BC9BFF", border: "none", borderRadius: 8, padding: "10px 24px", fontSize: 14, fontWeight: 500, color: "#1e1e1c" }}>
        {t("continue")}
      </button>
    </div>
  );
}

// Step 4: Done
function ServeStep4() {
  const router = useRouter();
  const { markOnboardingComplete } = useUser();
  const track = useOnboardingTrackEvent();
  const t = useTranslations("Setup");

  const finish = (destination: string): void => {
    track({ pageName: "Onboarding Serve", eventName: "serve_onboarding_completed", additionalProperties: { destination } });
    completeOnboardingAndNavigate(markOnboardingComplete, () => router.push(`/${destination}`));
  };

  return (
    <div className="flex flex-col items-center justify-center gap-6 flex-1" style={{ padding: 48 }}>
      <StepBadge step={4} />
      <h1 style={{ fontSize: 28, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif', letterSpacing: "-0.02em" }}>{t("serve.allSet")}</h1>
      <p style={{ fontSize: 15, color: "rgba(237,236,234,0.55)", margin: 0, textAlign: "center", maxWidth: 480, lineHeight: "22px" }}>
        {t("serve.completeDescription")}
      </p>

      <div className="flex gap-3">
        <button onClick={() => finish("datasets")} className="cursor-pointer" style={{ background: "#BC9BFF", color: "#1e1e1c", borderRadius: 8, padding: "10px 24px", fontSize: 14, fontWeight: 500, border: "none" }}>
          {t("serve.viewDatasets")}
        </button>
      </div>

      <StepDots current={4} />
    </div>
  );
}

export default function ServeOnboarding() {
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { markOnboardingComplete } = useUser();
  const router = useRouter();
  const t = useTranslations("Setup");
  const [step, setStep] = useState(1);

  function skipToDashboard(): void {
    completeOnboardingAndNavigate(markOnboardingComplete, () => router.push("/dashboard"));
  }

  if (isInitializing || !cogniInstance) {
    return (
      <>
        <TrackPageView page="Onboarding Serve" />
        <div className="flex flex-col items-center justify-center h-screen gap-4" style={darkPage}>
          <span style={{ fontSize: 14, color: "rgba(237,236,234,0.65)" }}>{t("stillPreparingMemory")}</span>
          <button
            onClick={skipToDashboard}
            className="cursor-pointer"
            style={{ background: "none", border: "1px solid rgba(255,255,255,0.2)", borderRadius: 8, padding: "8px 18px", fontSize: 13, fontWeight: 500, color: "rgba(237,236,234,0.8)" }}
          >
            {t("skipDashboard")}
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-auto" style={darkPage}>
      {step === 1 && <ServeStep1 onNext={() => setStep(2)} />}
      {step === 2 && <ServeStep2 onNext={() => setStep(3)} />}
      {step === 3 && <ServeStep3 onNext={() => setStep(4)} cogniInstance={cogniInstance} />}
      {step === 4 && <ServeStep4 />}
    </div>
  );
}
