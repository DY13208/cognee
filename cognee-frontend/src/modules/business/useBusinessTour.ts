"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import type { ZoomTransform } from "d3";
import type { BusinessCanvasHandle } from "./canvas/BusinessCanvas";
import type { BrainState } from "./sceneTypes";

const STEP_DWELL_MS = 5000;

export interface BusinessTour {
  isPlaying: boolean;
  start: () => void;
  stop: () => void;
}

// A scripted flythrough of all four altimeter levels, narrating each one —
// new in this port (no source equivalent), meant to carry an unattended
// demo through the model: press play and the camera + narration do the
// presenting. goToAltimeterLevel's own transform already dispatches a d3
// zoom event on the canvas (see useBusinessCamera's applyTransform), which
// resets the idle timer other features (auto-insights, the pending-search
// chip) key off of — so the tour naturally keeps them quiet while it plays,
// with no explicit coordination needed here.
export function useBusinessTour(
  canvasRef: RefObject<BusinessCanvasHandle | null>,
  narrate: (text: string, color?: string) => void,
  brainState: BrainState | null,
): BusinessTour {
  const t = useTranslations("knowledgeGraph");
  const [isPlaying, setIsPlaying] = useState(false);
  const cancelledRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preTourTransformRef = useRef<ZoomTransform | null>(null);

  // Stopping must feel instantaneous — the blur drops on this render and
  // the camera snaps straight back to wherever the user left it before the
  // tour, no animation, no waiting on whatever transition was in flight.
  const stop = useCallback(() => {
    cancelledRef.current = true;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setIsPlaying(false);
    const preTour = preTourTransformRef.current;
    preTourTransformRef.current = null;
    if (preTour) canvasRef.current?.setTransformNow(preTour);
  }, [canvasRef]);

  const start = useCallback(() => {
    cancelledRef.current = false;
    preTourTransformRef.current = canvasRef.current?.getTransform() ?? null;
    setIsPlaying(true);
    const texts = [
      brainState
        ? t("intro", { kindCount: brainState.typeNodes.length, sourceCount: brainState.sourceNames.length })
        : t("tourIntroFallback"),
      t("tourZoom"),
      t("tourLines"),
      t("tourDeep"),
    ];
    const runStep = (index: number): void => {
      if (cancelledRef.current || index >= texts.length) {
        // Finished (or already cancelled): the snapshot is only for
        // interruptions — a completed tour stays where it ended.
        preTourTransformRef.current = null;
        setIsPlaying(false);
        return;
      }
      canvasRef.current?.goToAltimeterLevel(index);
      narrate(texts[index], "#43D9E8");
      timeoutRef.current = setTimeout(() => runStep(index + 1), STEP_DWELL_MS);
    };
    runStep(0);
  }, [canvasRef, narrate, brainState, t]);

  useEffect(() => () => {
    cancelledRef.current = true;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  return { isPlaying, start, stop };
}
