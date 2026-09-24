"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ForceGraphMethods, LinkObject, NodeObject } from "react-force-graph-2d";
import type { TeleologyRelationship } from "@/modules/teleology/teleologyApi";

const ForceGraph = dynamic(() => import("react-force-graph-2d"), { ssr: false });

export const REL_COLOR: Record<string, string> = {
  serves: "#60A5FA",
  advances: "#34D399",
  blocks: "#F87171",
};

export type PurposeNodeKind = "goal" | "entity" | "other";

export interface PurposeGraphNode extends NodeObject {
  id: string;
  name: string;
  type?: string;
  kind: PurposeNodeKind;
  dimmed?: boolean;
}

export interface PurposeGraphLink extends LinkObject {
  source: string | PurposeGraphNode;
  target: string | PurposeGraphNode;
  relationship: string;
  color: string;
}

export interface PurposeLensGraphProps {
  nodes: PurposeGraphNode[];
  links: PurposeGraphLink[];
  selectedNodeId?: string | null;
  onSelectNode?: (node: PurposeGraphNode | null) => void;
  className?: string;
}

function linkEnds(link: PurposeGraphLink): { sid: string; tid: string } {
  const s = link.source;
  const t = link.target;
  return {
    sid: typeof s === "object" && s ? String((s as PurposeGraphNode).id) : String(s),
    tid: typeof t === "object" && t ? String((t as PurposeGraphNode).id) : String(t),
  };
}

export default function PurposeLensGraph({
  nodes,
  links,
  selectedNodeId,
  onSelectNode,
  className,
}: PurposeLensGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<ForceGraphMethods<PurposeGraphNode, PurposeGraphLink> | undefined>(
    undefined,
  );
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  const handleResize = useCallback(() => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    setDimensions({ width: clientWidth, height: clientHeight });
  }, []);

  useEffect(() => {
    handleResize();
    const observer = new ResizeObserver(handleResize);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [handleResize]);

  useEffect(() => {
    if (!graphRef.current || dimensions.width === 0) return;
    const timer = setTimeout(() => graphRef.current?.zoomToFit(400, 48), 200);
    return () => clearTimeout(timer);
  }, [nodes, links, dimensions.width, dimensions.height]);

  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  return (
    <div ref={containerRef} className={className} style={{ width: "100%", height: "100%", minHeight: 320 }}>
      {dimensions.width > 0 && dimensions.height > 0 ? (
        <ForceGraph
          ref={graphRef as never}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          backgroundColor="rgba(0,0,0,0)"
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={0.92}
          linkCurvature={0.12}
          cooldownTicks={80}
          onNodeClick={(node) => onSelectNode?.(node as PurposeGraphNode)}
          onBackgroundClick={() => onSelectNode?.(null)}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const n = node as PurposeGraphNode;
            const x = n.x ?? 0;
            const y = n.y ?? 0;
            const selected = selectedNodeId === n.id;
            const dim = Boolean(n.dimmed) && !selected;
            const isGoal = n.kind === "goal";
            const r = isGoal ? 9 : 6;
            const alpha = dim ? 0.22 : 1;

            ctx.save();
            ctx.globalAlpha = alpha;

            if (isGoal) {
              // Target / bullseye style for purpose nodes
              ctx.beginPath();
              ctx.arc(x, y, r + 4, 0, Math.PI * 2);
              ctx.strokeStyle = selected ? "#EDECEA" : "rgba(188,155,255,0.9)";
              ctx.lineWidth = 1.5 / Math.max(globalScale, 0.6);
              ctx.stroke();
              ctx.beginPath();
              ctx.arc(x, y, r, 0, Math.PI * 2);
              ctx.fillStyle = selected ? "#BC9BFF" : "rgba(188,155,255,0.55)";
              ctx.fill();
              ctx.beginPath();
              ctx.arc(x, y, 2.5, 0, Math.PI * 2);
              ctx.fillStyle = "#0B0B0C";
              ctx.fill();
            } else {
              ctx.beginPath();
              ctx.arc(x, y, r, 0, Math.PI * 2);
              ctx.fillStyle = selected ? "#EDECEA" : "rgba(237,236,234,0.75)";
              ctx.fill();
              if (selected) {
                ctx.strokeStyle = "#BC9BFF";
                ctx.lineWidth = 2 / Math.max(globalScale, 0.6);
                ctx.stroke();
              }
            }

            const label = n.name || n.id;
            const fontSize = Math.max(10 / globalScale, 2.8);
            ctx.font = `${isGoal ? 600 : 500} ${fontSize}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = dim ? "rgba(237,236,234,0.35)" : "rgba(237,236,234,0.9)";
            ctx.fillText(label.length > 28 ? `${label.slice(0, 26)}…` : label, x, y + r + 3);
            ctx.restore();
          }}
          nodePointerAreaPaint={(node, color, ctx) => {
            const n = node as PurposeGraphNode;
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, n.kind === "goal" ? 14 : 10, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
          }}
          linkColor={(link) => {
            const l = link as PurposeGraphLink;
            const { sid, tid } = linkEnds(l);
            if (selectedNodeId && sid !== selectedNodeId && tid !== selectedNodeId) {
              // Still show teleology colors but quieter when something else is selected
              return `${l.color}55`;
            }
            return l.color;
          }}
          linkWidth={(link) => {
            const l = link as PurposeGraphLink;
            const { sid, tid } = linkEnds(l);
            if (selectedNodeId && (sid === selectedNodeId || tid === selectedNodeId)) return 2.4;
            return 1.4;
          }}
          linkCanvasObjectMode={() => "after"}
          linkCanvasObject={(link, ctx, globalScale) => {
            const l = link as PurposeGraphLink;
            const src = l.source as PurposeGraphNode;
            const tgt = l.target as PurposeGraphNode;
            if (typeof src !== "object" || typeof tgt !== "object") return;
            if (src.x == null || src.y == null || tgt.x == null || tgt.y == null) return;

            const mx = (src.x + tgt.x) / 2;
            const my = (src.y + tgt.y) / 2;
            const fontSize = Math.max(9 / globalScale, 2.4);
            ctx.save();
            ctx.font = `600 ${fontSize}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = l.color;
            ctx.fillText(String(l.relationship || ""), mx, my - 4);
            ctx.restore();
          }}
        />
      ) : null}
    </div>
  );
}

export function relationshipColor(rel: string | TeleologyRelationship): string {
  return REL_COLOR[String(rel).toLowerCase()] || "#BC9BFF";
}
