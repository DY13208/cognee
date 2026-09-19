import AuthContentSectionCarousel from "@/ui/elements/Auth/ContentSections/AuthContentSectionCarousel";
import AuthPageContainer from "@/ui/elements/Auth/AuthPageContainer";
import LocalSignInForm from "./partials/LocalSignInForm";
import { Center, Flex } from "@mantine/core";

export default async function LocalLoginPage({ searchParams }: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return (
    <AuthPageContainer>
      <Center className="flex-1 flex-col">
        <Flex className="flex-col items-center w-full px-6 lg:w-[50vw] lg:px-0">
          <LocalSignInForm errorCode={error} />
        </Flex>
      </Center>
      <AuthContentSectionCarousel />
    </AuthPageContainer>
  );
}
