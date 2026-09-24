import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { BusinessLanguageProvider, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import AppPageTranslator from "../AppPageTranslator";

jest.mock("next/navigation", () => ({ usePathname: () => "/datasets" }));

function Page() {
  const { setLanguage } = useBusinessLanguage();
  const [message, setMessage] = useState("No brains yet");
  return (
    <main data-app-page>
      <AppPageTranslator />
      <h1>Brain</h1>
      <p>{message}</p>
      {/* User-authored content that must not be rewritten by ambiguous-key rules */}
      <div data-testid="user-name">Name</div>
      <button type="button">Name</button>
      <input placeholder="Search files..." />
      <button onClick={() => setMessage("No documents yet")}>Change message</button>
      <button onClick={() => setLanguage("en")}>English</button>
    </main>
  );
}

it("translates fixed page copy, observes updates, and restores English", async () => {
  window.localStorage.removeItem("cognee-language");
  window.localStorage.removeItem("cognee-business-language");
  render(<BusinessLanguageProvider><Page /></BusinessLanguageProvider>);
  expect(screen.getByRole("heading", { name: "脑库" })).toBeInTheDocument();
  expect(screen.getByText("暂无脑库")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("搜索文件...")).toBeInTheDocument();
  // Ambiguous "Name" in free content stays English; chrome button is translated.
  expect(screen.getByTestId("user-name")).toHaveTextContent("Name");
  expect(screen.getByRole("button", { name: "名称" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Change message" }));
  await waitFor(() => expect(screen.getByText("暂无文档")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "English" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Brain" })).toBeInTheDocument());
  expect(screen.getByText("No documents yet")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Search files...")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Name" })).toBeInTheDocument();
});
