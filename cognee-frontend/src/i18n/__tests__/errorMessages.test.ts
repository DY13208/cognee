import { getLocalizedErrorKey } from "@/i18n/errorMessages";

describe("getLocalizedErrorKey", () => {
  it("maps stable public backend error codes", () => {
    expect(getLocalizedErrorKey("LOGIN_BAD_CREDENTIALS")).toBe("invalidCredentials");
    expect(getLocalizedErrorKey("LOGIN_USER_NOT_VERIFIED")).toBe("unverified");
  });

  it("does not surface an unmapped backend detail", () => {
    expect(getLocalizedErrorKey("database connection refused")).toBe("loginFailed");
    expect(getLocalizedErrorKey(undefined)).toBe("loginFailed");
  });
});
