import handleServerErrors from "../handleServerErrors";

it("treats local 403 as a permission error instead of expiring the session", async () => {
  const response = {
    status: 403, statusText: "Forbidden", ok: false,
    text: async () => JSON.stringify({ detail: "Dataset is private" }),
  } as Response;
  await expect(handleServerErrors(response, null, false)).rejects.toMatchObject({
    status: 403, detail: "Dataset is private",
  });
});
