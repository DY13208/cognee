/**
 * Maps backend's stable, public error codes to product copy. Raw backend
 * details deliberately never reach normal UI: they may be technical or
 * contain information intended only for administrators.
 */
export const LOCALIZED_ERROR_KEYS = {
  LOGIN_BAD_CREDENTIALS: "invalidCredentials",
  LOGIN_USER_NOT_VERIFIED: "unverified",
} as const;

export type LocalizedErrorCode = keyof typeof LOCALIZED_ERROR_KEYS;

export function getLocalizedErrorKey(code: unknown): string {
  return typeof code === "string" && code in LOCALIZED_ERROR_KEYS
    ? LOCALIZED_ERROR_KEYS[code as LocalizedErrorCode]
    : "loginFailed";
}
