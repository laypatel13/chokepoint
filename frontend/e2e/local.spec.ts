import { expect, test } from "./fixtures";

// `chokepoint map`: the app on 127.0.0.1 for your own projects, with the replay kept apart.

test.describe("chokepoint map (local mode)", () => {
  test("opens your project, not the story page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Chokepoint · Map");
    await expect(page.locator(".local-badge")).toBeVisible();
    await expect(page.locator(".back")).toBeHidden();
    await expect(page.locator("#project")).toHaveValue("local:example-app");
    const groups = await page.locator("#project optgroup").evaluateAll((gs) => gs.map((g) => g.getAttribute("label")));
    expect(groups).toEqual(["Your projects", "Replay: Sept 8, 2025 (example)"]);
    await expect(page.locator("#project option:checked")).toHaveText("example-app");
    await expect(page.locator("#project-note")).toContainText("Your lockfile in");
    await expect(page.locator("#answer")).toContainText("TODAY'S MAINTAINER LISTS");
    await expect(page.locator("#timeline")).toBeHidden();
  });

  test("Nightjar's card says it isn't watching yet and how to start it", async ({ page }) => {
    await page.goto("/");
    const nj = page.locator("#nightjar");
    await expect(nj).toBeVisible();
    await expect(nj).toContainText("not watching yet");
    await expect(nj.locator("code.cmd")).toContainText("chokepoint nightjar");
  });

  test("copy buttons copy the command", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    const code = page.locator("#nightjar code.cmd");
    const text = await code.getAttribute("data-copy");
    await code.click();
    await expect(code).toHaveText("copied");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(text);
    await expect(code).toHaveText(text!);
  });

  test("the fix is a command on this machine, never a PR", async ({ page }) => {
    await page.goto("/");
    await page.locator("#key").fill("debug@4.4.2");
    await page.locator("#q1").click();
    await expect(page.locator("#answer")).toContainText("SHIPS TO PROD");
    await expect(page.locator("#answer .chain .node").first()).toHaveText("example-app");
    await page.locator('#answer [data-fix]').click();
    const pr = page.locator("#pr .pr");
    await expect(pr).toContainText("package.json gets:");
    await expect(pr.locator("code.cmd").first()).toContainText("chokepoint fix debug@4.4.2 --write");
    await expect(pr.locator("#open-pr")).toHaveCount(0);
  });

  test("the replay is still there, apart", async ({ page }) => {
    await page.goto("/");
    await page.locator("#project").selectOption("webpack/webpack-dev-server@fa9195c");
    await expect(page.locator("#timeline")).toBeVisible();
    await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
    await expect(page.locator("#nightjar")).toBeHidden();
    await expect(page).toHaveURL(/\/\?project=webpack/);
  });

  test("hosted-only features are off", async ({ request }) => {
    expect((await request.post("/api/scan", { data: { repo: "a/b" } })).status()).toBe(404);
    expect((await request.post("/api/fix/open", { data: { project: "x", key: "a@1", confirm: true } })).status()).toBe(404);
    expect((await (await request.get("/api/config")).json()).mode).toBe("local");
  });
});
