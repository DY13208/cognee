import AuthPageContainer from "@/ui/elements/Auth/AuthPageContainer";
import LocalSignInForm from "./partials/LocalSignInForm";
import { isMindMapSsoEnabled } from "@/modules/users/mindMapSsoProxy";

export default async function LocalLoginPage({ searchParams }: {
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ error }, mindMapSsoEnabled] = await Promise.all([searchParams, isMindMapSsoEnabled()]);
  return (
    <AuthPageContainer background="black">
      <main className="flex min-w-0 flex-1 flex-col items-center justify-center px-4 py-6">
        <LocalSignInForm errorCode={error} mindMapSsoEnabled={mindMapSsoEnabled} />
      </main>
    </AuthPageContainer>
  );
}
