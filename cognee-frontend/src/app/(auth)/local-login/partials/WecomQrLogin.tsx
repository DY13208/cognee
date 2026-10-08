"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Flex, Loader, Text } from "@mantine/core";
import { wecomCallbackFromMessage } from "@/modules/users/wecomQrMessage";

type QrLogin = { loginUrl: string; expiresIn: number };
// Leave room for the provider's scanned/cancelled status as well as the QR.
const FRAME_HEIGHT = 420;

export default function WecomQrLogin() {
  const [qr, setQr] = useState<QrLogin | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    let refresh: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const response = await fetch("/sso/mind-map/qr", {
          credentials: "same-origin", cache: "no-store", signal: controller.signal,
        });
        if (!response.ok) throw new Error("qr_unavailable");
        const data: QrLogin = await response.json();
        if (controller.signal.aborted) return;
        if (!data.loginUrl || !Number.isFinite(data.expiresIn) || data.expiresIn <= 0) throw new Error("invalid_qr");
        setQr(data);
        refresh = setTimeout(() => {
          setQr(null);
          setRevision((value) => value + 1);
        }, Math.min(data.expiresIn, 600) * 1000);
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(refresh); };
  }, [revision]);

  useEffect(() => {
    if (!qr) return;
    function receive(event: MessageEvent) {
      const target = wecomCallbackFromMessage(event, frame.current?.contentWindow || null, qr!.loginUrl);
      if (target) window.location.assign(target);
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [qr]);

  function refresh() {
    setError(false);
    setQr(null);
    setRevision((value) => value + 1);
  }

  return (
    <Flex className="w-full flex-col items-center gap-2">
      <div className="relative w-full max-w-[320px] rounded-lg bg-[#0b0b0b]"
        style={{ height: FRAME_HEIGHT }} aria-label="企业微信登录二维码">
        {qr ? (
          <iframe ref={frame} title="企业微信扫码登录" src={qr.loginUrl} scrolling="no"
            referrerPolicy="no-referrer" className="absolute left-0 top-0 border-0"
            style={{ width: "100%", height: FRAME_HEIGHT }}
            onLoad={() => frame.current?.contentWindow?.postMessage("ask_usePostMessage", new URL(qr.loginUrl).origin)} />
        ) : (
          <Flex className="absolute inset-0 flex-col items-center justify-center gap-3 p-4">
            {error ? <Text role="alert" size="sm" c="#EDECEA" ta="center">二维码加载失败，请刷新或切换账号密码登录。</Text>
              : <><Loader size="sm" /><Text size="sm" c="#EDECEA">正在加载二维码…</Text></>}
          </Flex>
        )}
      </div>
      <Flex className="w-full justify-center gap-2 flex-wrap">
        <Button variant="subtle" size="xs" className="!text-[#BC9BFF] hover:!bg-white/10" onClick={refresh}>刷新二维码</Button>
        <Button component="a" href="/sso/mind-map/login" variant="subtle" size="xs" className="!text-[#BC9BFF] hover:!bg-white/10">使用已有登录状态</Button>
      </Flex>
    </Flex>
  );
}
