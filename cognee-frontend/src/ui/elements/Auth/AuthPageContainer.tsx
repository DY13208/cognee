import { PropsWithChildren } from "react";
import TetrisBackground from "./TetrisBackground";

// Auth pages share the landing hero's look: pure black with the 33px grid
// and the falling-tetromino canvas behind a centered content column.
export default function AuthPageContainer({ children, background = "animated" }: PropsWithChildren<{
  background?: "animated" | "black";
}>) {
  const plain = background === "black";
  return (
    <div
      className={`relative text-[#EDECEA] ${plain ? "min-h-dvh" : "h-screen overflow-hidden"}`}
      style={{
        backgroundColor: "#000000",
        backgroundImage: plain ? "none" :
          "linear-gradient(rgba(244,244,244,0.10) 1px, transparent 1px), linear-gradient(90deg, rgba(244,244,244,0.10) 1px, transparent 1px)",
        backgroundSize: "33px 33px",
      }}
    >
      {!plain && <TetrisBackground />}
      <div className={`relative z-[3] flex w-full flex-row ${plain ? "min-h-dvh" : "h-screen"}`}>{children}</div>
    </div>
  );
}
