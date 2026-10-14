import { expect, test as base } from "@playwright/test";

// Every test also fails on a JavaScript error or a console error/warning in the page (React
// warnings included). Expected HTTP errors (the tests' own 400s) are allowed.
export const test = base.extend<{ consoleGuard: void }>({
  consoleGuard: [async ({ page }, use) => {
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
    page.on("console", (msg) => {
      if (!["error", "warning"].includes(msg.type())) return;
      if (/Failed to load resource/.test(msg.text())) return;
      // Deliberate: the graph zooms slower than Cytoscape's default (wheelSensitivity 0.25), and
      // Cytoscape warns about any custom value.
      if (/You have set a custom wheel sensitivity/.test(msg.text())) return;
      problems.push(`console ${msg.type()}: ${msg.text()}`);
    });
    await use();
    expect(problems, "the page logged errors").toEqual([]);
  }, { auto: true }],
});

export { expect };
export type { Page } from "@playwright/test";
