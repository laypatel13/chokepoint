import { expect, test, type Page } from "./fixtures";

const REPLAY = "webpack/webpack-dev-server@fa9195c";
const answer = (page: Page) => page.locator("#answer");

/** Nothing in the sidebar is wider than the sidebar (it must never scroll sideways). */
async function expectSidebarFits(page: Page) {
  expect(await page.locator(".side").evaluate((s) => s.scrollWidth - s.clientWidth)).toBeLessThanOrEqual(0);
}

/** The lifted highlight sits on the selected moment, and dots are lit up to it (not beyond). */
async function expectAt(page: Page, step: number) {
  await expect(page.locator(`#stops [data-stop="${step}"]`)).toHaveAttribute("aria-current", "step");
  await expect.poll(async () => page.evaluate((i) => {
    const glider = document.querySelector("#stops .glider")!.getBoundingClientRect();
    const card = document.querySelector(`#stops [data-stop="${i}"]`)!.closest("li")!.getBoundingClientRect();
    return Math.abs(glider.left - card.left) < 2 && Math.abs(glider.width - card.width) < 2;
  }, step), { message: `highlight on moment ${step}` }).toBe(true);
  const lit = await page.locator("#stops .stop").evaluateAll((lis) => lis.map((li) => (li.classList.contains("past") ? 1 : 0)).join(""));
  expect(lit).toBe("111111".slice(0, step + 1).padEnd(6, "0"));
}

async function openReplay(page: Page) {
  await page.goto(`/app?project=${REPLAY}`);
  await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
}

test.describe("the Sept 8 replay", () => {
  test("opens on the day before, with the project and its numbers", async ({ page }) => {
    await openReplay(page);
    await expect(page).toHaveTitle("Chokepoint · App");
    await expect(page.locator("#project")).toHaveValue(REPLAY);
    await expect(page.locator("#project-note")).toContainText("commit fa9195c");
    await expect(page.locator("#stats .stat b")).toHaveText(["1,423", "90", "685", /\d+/]);
    await expect(page.locator("#timeline")).toBeVisible();
    await expect(page.locator("#stops .stop")).toHaveCount(6);
    await expect(page.locator("#stops .stop .when")).toHaveText(["Sept 7", "13:12", "13:13", "13:20", "14:26", "Today"]);
    await expect(page.locator('#stops [data-stop="2"] .what')).toHaveText("Nightjar raises the alert");
    await expect(page.locator("#panel-scanner")).toContainText("Nothing yet");
    await expect(page.locator("#panel-chokepoint")).toContainText("43 of 90");
    await expect(answer(page).locator(".big")).toContainText("43");
    await expect(answer(page)).toContainText("MAINTAINERS AT INSTALL TIME");
    await expect(page.locator("#tl-prev")).toBeDisabled();
    await expect(page.locator('#stops [data-stop="0"]')).toHaveAttribute("aria-current", "step");
    await expect(page.locator(".replay-note")).toContainText("didn't do anything wrong");
  });

  test("the sidebar fits at every moment: rows stack, safe ranges fold away", async ({ page }) => {
    await openReplay(page);
    await expectSidebarFits(page);
    for (const step of [1, 2, 3, 4, 5]) {
      await page.locator(`#stops [data-stop="${step}"]`).click();
      await expect(page.locator(`#stops [data-stop="${step}"]`)).toHaveAttribute("aria-current", "step");
      await expectSidebarFits(page);
    }
    await page.locator('#stops [data-stop="1"]').click();
    const first = answer(page).locator("ul.req").first().locator(".req-row .pill").first();
    await expect(first).not.toHaveText("safe by range");  // what matters comes first
    const more = answer(page).locator(".req-more");
    await expect(more.locator(".req-row").first()).toBeHidden();
    await more.locator("summary").click();
    await expect(more.locator(".req-row").first()).toBeVisible();
    await expectSidebarFits(page);
  });

  test("the highlight follows the selected moment and the dots light up to it", async ({ page }) => {
    await openReplay(page);
    await expectAt(page, 0);
    await page.locator('#stops [data-stop="2"]').click();
    await expectAt(page, 2);
    await page.locator('#stops [data-stop="4"]').click();
    await expectAt(page, 4);
    await page.locator('#stops [data-stop="1"]').click();  // going back unlights the later moments
    await expectAt(page, 1);
    await page.locator("#tl-next").click();
    await expectAt(page, 2);
    await page.setViewportSize({ width: 1200, height: 900 });  // stays on its card after a resize
    await expectAt(page, 2);
  });

  test("steps forward and back with buttons, clicks and arrow keys", async ({ page }) => {
    await openReplay(page);
    await page.locator("#tl-next").click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Exposed");
    await expect(answer(page)).toContainText("LOCKFILE SAVED YOU");
    await expect(answer(page).locator(".req-row").first()).toBeVisible();

    await page.locator('#stops [data-stop="1"]').focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#panel-chokepoint")).toContainText("Nightjar: ALERT");
    await expect(page.locator('#stops [data-stop="2"]')).toHaveAttribute("aria-current", "step");

    await page.locator('#stops [data-stop="3"]').click();
    await expect(page.locator("#panel-chokepoint")).toContainText("packages exposed");

    await page.locator('#stops [data-stop="4"]').click();
    await expect(page.locator("#panel-chokepoint")).toContainText("min late");
    await expect(page.locator("#panel-chokepoint")).toContainText("Nightjar raised its alert 74 minutes earlier");
    await expect(page.locator("#panel-scanner")).toContainText("flagged");
    await expect(page.locator("#panel-scanner")).toContainText("MAL-2025-46974");

    await page.locator("#tl-next").click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Lockfile held");
    await expect(page.locator("#tl-next")).toBeDisabled();
    await expect(answer(page).locator(".pill.green", { hasText: "PIN" }).first()).toBeVisible();

    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("#panel-chokepoint")).toContainText("min late");
    for (let i = 0; i < 4; i++) await page.locator("#tl-prev").click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
  });

  test("13:13: Nightjar raises the alert, before any advisory", async ({ page }) => {
    await openReplay(page);
    await page.locator('#stops [data-stop="2"]').click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Nightjar: ALERT");
    await expect(page.locator("#panel-chokepoint")).toContainText("chalk@5.6.1");
    await expect(page.locator("#panel-scanner")).toContainText("Nothing yet");
    const card = answer(page).locator(".nj-loop");  // watch → investigate → decide → act → remember
    await expect(card.locator(".lbl")).toHaveText(["Watch", "Investigate", "Decide", "Act", "Remember"]);
    await expect(card).toContainText("chalk@5.6.1 published by @qix at 13:13:05 UTC");
    await expect(card).toContainText("saved as an Alert and a Decision in FalkorDB");
    await expect(card).toContainText("burst: 3 releases from @qix in 54s");
    await expect(card).toContainText("pin chalk to 5.4.1");
    await expect(card.locator("code", { hasText: "npm ci" })).toBeVisible();  // backticks render as code
    expect(await page.locator("body").innerText()).not.toContain("`");
    await expect(answer(page).locator(".req-row")).toHaveCount(3);  // only what had been published by 13:13:05
    await expect(answer(page)).toContainText("74 minutes later");
  });

  test("the fix preview offers a PR (disabled without a token)", async ({ page }) => {
    await openReplay(page);
    await page.locator('#stops [data-stop="5"]').click();
    await answer(page).locator("[data-fix]").first().click();
    const pr = page.locator("#pr .pr");
    await expect(pr.locator(".title")).toContainText("fix(deps): pin");
    await expect(pr).toContainText("branch");
    await expect(pr.locator("#open-pr")).toBeDisabled();
    await expect(pr).toContainText("Opening PRs is switched off on this server.");  // the test server has no token
  });
});

test.describe("questions on a project", () => {
  test("switching project answers Q2 right away", async ({ page }) => {
    await openReplay(page);
    await page.locator("#project").selectOption("mochajs/mocha");
    await expect(page.locator("#timeline")).toBeHidden();
    await expect(page.locator("#project-note")).toContainText("github.com/mochajs/mocha");
    await expect(answer(page)).toContainText("TODAY'S MAINTAINER LISTS");
    await expect(answer(page).locator("table.rank tr").first()).toBeVisible();
    await expect(page).toHaveURL(/project=mochajs%2Fmocha/);
  });

  test("Q1: not installed, then the lockfile check", async ({ page }) => {
    await openReplay(page);
    await page.locator("#key").fill("debug@4.4.2");
    await page.locator("#q1").click();
    await expect(answer(page)).toContainText("NOT INSTALLED");
    await expect(answer(page)).toContainText("lockfile pins");
    await answer(page).locator('[data-run="lockfile_saved_you"]').click();
    await expect(answer(page)).toContainText("LOCKFILE SAVED YOU");
  });

  test("Q1 chips: safe version, blast radius; Q2 chips: advisories, numbers", async ({ page }) => {
    await openReplay(page);
    await page.locator("#key").fill("debug@4.4.2");
    await page.locator('.chip[data-tool="safe_version"]').click();
    await expect(answer(page).locator(".pill.green")).toContainText("PIN debug@");
    await expect(answer(page).locator("pre.code")).toContainText("debug");

    await page.locator("#key").fill("debug@4.4.1");
    await page.locator('.chip[data-tool="blast_radius"]').click();
    await expect(answer(page).locator(".big")).toContainText("direct deps");

    await page.locator('.chip[data-tool="graph_stats"]').click();
    await expect(answer(page).locator("pre.code")).toContainText('"nodes"');

    await page.locator('.chip[data-tool="known_advisories"]').click();
    await expect(answer(page).locator(".chain .node").first()).toBeVisible();
    await answer(page).locator(".chain .node[data-key]").first().click();
    await expect(answer(page)).toContainText(/INSTALLED|AFFECTED/);
    await expect(answer(page)).toContainText("How it gets in");
    await expect(answer(page).locator(".chain svg.flow").first()).toBeVisible();
    expect(await page.locator("body").innerText()).not.toContain("→");  // incl. the API's sentences
  });

  test("Enter in the version box runs Q1", async ({ page }) => {
    await openReplay(page);
    await page.locator("#key").fill("chalk@5.4.1");
    await page.locator("#key").press("Enter");
    await expect(answer(page)).toContainText("How it gets in");
  });

  test("clicking a maintainer in the ranking focuses on them", async ({ page }) => {
    await openReplay(page);
    await page.locator("#q2").click();
    const second = answer(page).locator("table.rank tr").nth(1);
    const who = (await second.getAttribute("data-maintainer"))!;
    await second.click();
    await expect(answer(page).locator("table.rank tr.on")).toHaveAttribute("data-maintainer", who);
    await expect(answer(page)).toContainText(`@${who}`);
  });

  test("Ask can investigate a version and recall what Nightjar flagged", async ({ page }) => {
    await openReplay(page);
    await page.locator("#question").fill("investigate debug@4.4.1");
    await page.locator("#ask button").click();
    await expect(answer(page).locator(".steps li")).toHaveCount(4);
    await expect(answer(page)).toContainText("INSTALLED · SHIPS TO PROD");
    await expect(answer(page)).toContainText("Pin debug to 4.4.3");
    await page.locator("#question").fill("what did Nightjar flag?");
    await page.locator("#ask button").click();
    // remembered only after a `chokepoint replay nightjar` run; a fresh install says how to get one
    await expect(answer(page)).toContainText(/Nightjar remembers \d+ flagged|chokepoint replay nightjar runs it/);
    await expectSidebarFits(page);
  });

  test("the agent takes a second step only when the graph says so, and shows it", async ({ page }) => {
    await openReplay(page);
    await page.getByRole("button", { name: "is debug@4.4.1 in my app and what do I pin?" }).click();
    const trace = answer(page).locator(".agent-trace");
    await expect(trace.locator(".step code")).toHaveText(["explain_path", "safe_version"]);
    await expect(trace).toContainText("debug@4.4.1 is installed, so find the version to pin");
    await expect(answer(page).locator(".step-card")).toContainText("PIN debug@");
    await page.locator("#question").fill("is debug@4.4.2 in my app and what do I pin?");
    await page.locator("#ask button").click();
    await expect(trace.locator(".stop")).toContainText("debug@4.4.2 isn't installed, so there is nothing to pin.");
    await expect(trace.locator(".step code")).toHaveText(["explain_path"]);
    await expectSidebarFits(page);
  });

  test("Ask works without an LLM (keyword routing)", async ({ page }) => {
    await openReplay(page);
    await page.locator("#question").fill("who could poison my app?");
    await page.locator("#ask button").click();
    await expect(answer(page)).toContainText("“who could poison my app?”");
    await expect(answer(page)).toContainText("template (no LLM)");
    await expect(answer(page)).toContainText("via MCP · keyword rules");  // the tool was picked from the MCP server's list
    await expect(answer(page).locator("table.rank")).toBeVisible();
  });
});

test.describe("graph and Cypher", () => {
  test("Focus and Full graph", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator("#cy canvas").first()).toBeAttached();
    await expect(page.locator("#graph-note")).toContainText("Focus:");
    await expect(page.locator("#view-focus")).toHaveClass(/on/);
    const pillOn = (id: string) => page.evaluate((sel) => {
      const pill = document.querySelector(".graph-card .seg-thumb")!.getBoundingClientRect();
      const btn = document.querySelector(sel)!.getBoundingClientRect();
      return Math.abs(pill.left - btn.left) < 2 && Math.abs(pill.width - btn.width) < 2;
    }, id);
    await expect.poll(() => pillOn("#view-focus")).toBe(true);
    await page.locator("#view-full").click();
    await expect(page.locator("#graph-note")).toContainText("1423 installed versions");
    await expect(page.locator("#view-full")).toHaveClass(/on/);
    await expect.poll(() => pillOn("#view-full")).toBe(true);  // the pill slid over
    await page.locator("#view-focus").click();
    await expect(page.locator("#graph-note")).toContainText("Focus:");
  });

  test("zoom, fit and full screen", async ({ page }) => {
    await openReplay(page);
    await page.locator("#view-full").click();
    await expect(page.locator("#graph-note")).toContainText("installed versions");
    const zoom = async () => Number(await page.locator("#cy").getAttribute("data-zoom"));
    let start = 0;  // wait for the Full graph to be drawn (it waits for the switch to slide) and settle
    await expect.poll(async () => { const z = await zoom(); const same = z > 0 && z === start; start = z; return same; },
      { intervals: [400] }).toBe(true);
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect.poll(zoom).toBeGreaterThan(start * 1.3);
    await page.getByRole("button", { name: "Fit the whole graph" }).click();
    await expect.poll(async () => Math.abs((await zoom()) - start) < start * 0.05).toBe(true);
    await page.locator("#graph-expand").click();
    const card = page.locator(".graph-card");
    await expect(card).toHaveClass(/expanded/);
    await expect.poll(async () => (await card.boundingBox())!.width).toBeGreaterThan(1300);  // nearly the whole window
    await page.keyboard.press("Escape");
    await expect(card).not.toHaveClass(/expanded/);
  });

  test("the Cypher panel slides over the graph, lists every query, and closes with Esc", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator("#drawer-meta")).toContainText("ms in FalkorDB");
    const graphHeight = async () => (await page.locator(".graph-card").boundingBox())!.height;
    const before = await graphHeight();
    await expect(page.locator("#cypher-panel")).toBeHidden();
    await page.locator("#cypher-open").click();
    await expect(page.locator("#cypher-panel")).toBeVisible();
    await expect(page.locator("#cypher .q-head").first()).toBeVisible();
    await expect(page.locator("#cypher pre.code").first()).toContainText("MATCH");
    await expect(page.getByRole("button", { name: "Close (Esc)" })).toBeFocused();
    expect(Math.abs((await graphHeight()) - before)).toBeLessThan(2);  // opening it never shrinks the graph
    const panelTop = (await page.locator("#cypher-panel").boundingBox())!.y;
    expect(panelTop).toBeGreaterThan((await page.locator("#timeline").boundingBox())!.y + 100);  // the replay stays usable
    await page.locator("#tl-next").click();  // it follows the answer while open
    await expect(page.locator("#cypher .q-head b", { hasText: "RANGES_FOR_PACKAGE" }).first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#cypher-panel")).toBeHidden();
    await expect(page.locator("#cypher-open")).toBeFocused();
  });

  test("the story link goes back", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator(".back")).toBeVisible();
    await expect(page.locator(".back")).toHaveAttribute("href", "/");
    await expect(page.locator(".local-badge")).toBeHidden();
  });
});

test.describe("who could poison it (Q2)", () => {
  test("ranks accounts, groups teams, marks bots, and can rank by production first", async ({ page }) => {
    await openReplay(page);
    await page.locator("#q2").click();
    await expect(answer(page).locator("#top3")).toContainText("Together, @qix, @types, @isaacs reach 64 of 90");
    await expect(answer(page).locator('tr[data-maintainer="types"] .tag.bot')).toHaveText("bot");
    await expect(answer(page).locator(".tag.tied").first()).toContainText(/\+\d+ tied/);
    await page.locator("#rank-prod").click();
    await expect(page.locator("#rank-prod")).toHaveAttribute("aria-pressed", "true");
    await expect(answer(page).locator("table.rank tr").first()).toHaveAttribute("data-maintainer", "types");
    await expect(answer(page).locator("table.rank tr").first()).toContainText("14/29");
    await expectSidebarFits(page);
  });
});

test.describe("the replay card folds", () => {
  test("Fold hides the panels, the graph grows, Details brings them back", async ({ page }) => {
    await openReplay(page);
    const graphH = () => page.locator(".graph-card").evaluate((g) => g.getBoundingClientRect().height);
    const before = await graphH();
    await page.locator("#tl-fold").click();
    await expect(page.locator("#tl-fold")).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#panel-chokepoint")).toBeHidden();
    await expect(page.locator("#stops .stop")).toHaveCount(6);
    await expect.poll(graphH).toBeGreaterThan(before + 100);
    await page.reload();
    await expect(page.locator("#tl-fold")).toHaveAttribute("aria-expanded", "false");  // remembered
    await page.locator("#tl-fold").click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
  });
});

test.describe("when something fails", () => {
  test("a dropped request says what happened and Try again recovers", async ({ page }) => {
    await openReplay(page);
    await page.route("**/api/tool/chokepoints", (r) => r.abort());
    await page.locator("#q2").click();
    const problem = answer(page).locator(".problem");
    await expect(problem).toContainText("The server isn't answering");
    await expect(problem).toContainText("30 seconds");  // the hosted site explains the sleeping free host
    await page.unroute("**/api/tool/chokepoints");
    await page.locator("#retry").click();
    await expect(answer(page).locator("table.rank")).toBeVisible();
  });

  test("a project that won't load says so in the graph too", async ({ page }) => {
    await page.route("**/api/graph?*", (r) => r.fulfill({ status: 500, json: { detail: "graph database restarting" } }));
    await page.goto(`/app?project=${REPLAY}`);
    await expect(answer(page).locator(".problem")).toContainText("Something broke on the server");
    await expect(answer(page).locator(".problem")).toContainText("graph database restarting");
    await expect(page.locator(".graph-empty")).toContainText("couldn't load");
    await page.unroute("**/api/graph?*");
    await page.locator("#retry").click();
    await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
    await expect(page.locator(".graph-empty")).toHaveCount(0);
  });
});

test.describe("phone and keyboard", () => {
  test("on a phone nothing scrolls sideways and the moment you step to stays in view", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openReplay(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    for (let i = 0; i < 4; i++) await page.locator("#tl-next").click();
    await expectAt(page, 4);
    await expect.poll(() => page.evaluate(() => {
      const ol = document.querySelector("#stops")!.getBoundingClientRect();
      const card = document.querySelector('#stops [data-stop="4"]')!.getBoundingClientRect();
      return card.left >= ol.left - 1 && card.right <= ol.right + 1;
    })).toBe(true);
  });

  test("the ranking works from the keyboard, and skip links reach the answer and graph", async ({ page }) => {
    await openReplay(page);  // the replay opens on the ranking
    await expect(answer(page).locator("#top3")).toBeVisible();
    const isaacs = answer(page).locator('tr[data-maintainer="isaacs"] button.handle');
    await expect(isaacs).toBeVisible();  // the answer fades in; a hidden button can't take focus
    await isaacs.press("Enter");
    await expect(answer(page).locator("tr.on")).toHaveAttribute("data-maintainer", "isaacs");
    await expect(page.locator("#answer [role=status]")).toContainText("@isaacs");
    await page.goto(`/app?project=${REPLAY}`);
    await expect(page.locator('a[href="#answer"]')).toBeAttached();  // React has rendered
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to the answer" })).toBeFocused();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(page.locator("#graph")).toBeFocused();
  });
});

test.describe("finding your way", () => {
  test("a first-visit hint explains the screen and stays dismissed", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator("#first-hint")).toContainText("How to read this");
    await page.getByRole("button", { name: "Dismiss the hint" }).click();
    await expect(page.locator("#first-hint")).toHaveCount(0);
    await page.reload();
    await expect(page.locator("#panel-chokepoint")).toContainText("Risk mapped");
    await expect(page.locator("#first-hint")).toHaveCount(0);
  });

  test("hovering a legend item fades the rest of the graph", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator("#cy canvas").first()).toBeAttached();
    const faded = () => page.evaluate(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const cy = (document.querySelector("#cy") as any)._cyreg?.cy;
      return cy ? cy.$(".faded").length : -1;
    });
    await page.locator('[data-legend="amber"]').hover();
    await expect.poll(faded).toBeGreaterThan(0);
    await page.mouse.move(5, 5);
    await expect.poll(faded).toBe(0);
  });
});
