import AuthContentSectionCarousel from "@/ui/elements/Auth/ContentSections/AuthContentSectionCarousel";
import AuthPageContainer from "@/ui/elements/Auth/AuthPageContainer";
import LocalSignInForm from "./partials/LocalSignInForm";
import { Center, Flex } from "@mantine/core";
import { isMindMapSsoEnabled } from "@/modules/users/mindMapSsoProxy";

export default async function LocalLoginPage({ searchParams }: {
  searchParams: Promise<{ error?: string }>;
}) {
  const [{ error }, mindMapSsoEnabled] = await Promise.all([searchParams, isMindMapSsoEnabled()]);
  return (
    <AuthPageContainer>
      <Center className="min-w-0 flex-1 flex-col overflow-y-auto !justify-start">
        <Flex className="my-auto shrink-0 flex-col items-center w-full px-6 py-6 lg:w-[50vw] lg:px-0">
          <LocalSignInForm errorCode={error} mindMapSsoEnabled={mindMapSsoEnabled} />
        </Flex>
      </Center>
      <AuthContentSectionCarousel />
    </AuthPageContainer>
  );
}
