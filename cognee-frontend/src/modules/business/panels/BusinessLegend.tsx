"use client";

import { useState } from "react";
import { useBusinessLanguage } from "../BusinessLanguageContext";

// The view piles up visual conventions (rings, colors, moving dots) that a
// first-time viewer has no way to decode — this is the decoder card, the
// same role Mindmap's bottom-left legend plays. Collapsed by default so it
// never competes with the scene it explains.
function Glyph({ kind }: { kind: string }) {
  const base = "inline-block h-3 w-3 flex-none rounded-full";
  switch (kind) {
    case "size":
      return (
        <span className="flex w-3 flex-none items-end justify-center gap-[1px]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#8A7BD8]" />
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#8A7BD8]" />
        </span>
      );
    case "color":
      return <span className={`${base}`} style={{ background: "linear-gradient(135deg, #56DB7D 50%, #A456DB 50%)" }} />;
    case "amber":
      return <span className={`${base} border-2 border-[#F5A83C]`} />;
    case "answered":
      return <span className={`${base} border border-dashed border-[#43D9E8]`} />;
    case "double":
      return <span className={`${base} border border-[#E9EEF6] ring-1 ring-[#F5A83C] ring-offset-1 ring-offset-[#1A2438]`} />;
    case "path":
      return <span className={`${base} border-2 border-[#56DB7D]`} />;
    case "orphan":
      return <span className={`${base} border border-dashed border-[#7E8CA6]`} />;
    default:
      return <span className="inline-block h-1 w-1 flex-none rounded-full bg-[#43D9E8]" />;
  }
}

const LEGEND_ITEMS = [
  { kind: "size", en: "size = importance", zh: "大小代表重要程度" },
  { kind: "color", en: "color = which source it came from", zh: "颜色代表数据来源" },
  { kind: "amber", en: "amber ring = part of the live answer", zh: "橙色环代表当前回答引用的内容" },
  { kind: "answered", en: "dashed ring = answered questions before", zh: "虚线环代表曾用于回答问题" },
  { kind: "double", en: "double ring = spans sources / agent memory", zh: "双环代表跨来源或代理记忆" },
  { kind: "path", en: "green ring = shortest path between two records", zh: "绿色环代表两条记录间的最短路径" },
  { kind: "orphan", en: "faint dashed gray = no connections yet", zh: "浅灰虚线代表暂无连接" },
  { kind: "dot", en: "drifting dots = relationships at work", zh: "流动光点代表活跃关系" },
];

export default function BusinessLegend() {
  const { language } = useBusinessLanguage();
  const [open, setOpen] = useState(false);

  return (
    <div className="absolute bottom-3 left-3 z-10">
      {open && (
        <div className="mb-1.5 w-[248px] rounded-[10px] border border-[#2A3652] bg-[#1A2438] p-2.5 text-[10.5px] text-[#7E8CA6]">
          {LEGEND_ITEMS.map((item) => (
            <div key={item.kind} className="mb-1.5 flex items-center gap-2 last:mb-0">
              <Glyph kind={item.kind} />
              <span>{item[language]}</span>
            </div>
          ))}
          <div className="mt-1.5 border-t border-[#2A3652] pt-1.5">
            {language === "zh" ? "点击记录可查看邻近节点；按住 Shift 再点另一条记录可追踪两者间的路径" : "click a record to focus its neighborhood · shift+click a second to trace the path between them"}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`rounded-[8px] border px-2.5 py-[3px] ${
          open ? "border-[#43D9E8] text-[#43D9E8]" : "border-[#2A3652] text-[#7E8CA6] hover:text-[#E9EEF6]"
        }`}
      >
        {open ? language === "zh" ? "✕ 图例" : "✕ legend" : language === "zh" ? "? 图例" : "? legend"}
      </button>
    </div>
  );
}
