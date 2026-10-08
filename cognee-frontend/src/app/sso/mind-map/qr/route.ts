import { proxyMindMapSso } from "@/modules/users/mindMapSsoProxy";

export const dynamic = "force-dynamic";
export function GET(request: Request) {
  return proxyMindMapSso(request, "qr");
}
