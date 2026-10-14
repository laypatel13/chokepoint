import { test } from "@playwright/test";

// Reference screenshots for side-by-side visual review (not assertions).
// SCREENS=<dir> npx playwright test screens
const dir = process.env.SCREENS;

test.describe("screens", () => {
  test.skip(!dir, "set SCREENS=<dir> to capture");

  test("story page", async ({ page }, info) => {
    test.skip(info.project.name !== "hosted");
    await page.goto("/");
    await page.waitForTimeout(3500);
    await page.screenshot({ path: `${dir}/landing-hero.png` });
    for (const id of ["incident", "timeline", "how", "real", "cli"]) {
      await page.locator(`#${id}`).scrollIntoViewIfNeeded();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${dir}/landing-${id}.png` });
    }
  });

  test("app", async ({ page }, info) => {
    test.skip(info.project.name !== "hosted");
    await page.goto("/app?project=webpack/webpack-dev-server@fa9195c");
    await page.waitForTimeout(4000);
    await page.screenshot({ path: `${dir}/app-replay-0.png` });
    await page.locator('#stops [data-stop="2"]').click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${dir}/app-replay-2.png` });
    await page.locator("#project").selectOption("mochajs/mocha");
    await page.waitForTimeout(4000);
    await page.screenshot({ path: `${dir}/app-mocha.png` });
  });

  test("map", async ({ page }, info) => {
    test.skip(info.project.name !== "local");
    await page.goto("/");
    await page.waitForTimeout(3500);
    await page.screenshot({ path: `${dir}/map.png`, fullPage: true });
  });
});
