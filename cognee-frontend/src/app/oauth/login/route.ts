import { proxyCodeBuddy } from "@/modules/users/codebuddyProxy";

export const dynamic = "force-dynamic";
export function GET(request: Request) {
  return proxyCodeBuddy(request, "login");
}
