import { expect, test, type Page } from "./fixtures";

const REPLAY = "/app?project=webpack/webpack-dev-server@fa9195c";

test.describe("story page", () => {
  test("hero tells the story and the counter lands on 74 minutes", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Chokepoint · Who can poison your app?");
    const h1 = page.locator(".hero-sec h1");
    await expect(h1).toContainText("One phished login.");
    await expect(h1).toContainText("Eighteen poisoned packages.");
    await expect(h1).toContainText("74 minutes of silence.");
    await expect(h1).toBeVisible();
    await expect(page.locator("[data-count]")).toHaveText("74 min");
    await expect(page.locator(".stats-band .sb")).toHaveCount(4);
    await expect(page.locator(".hero-graph .hg-label")).toHaveText(["your app", "@qix can publish into 43 of 90", "13:12 · debug@4.4.2", "Nightjar ALERT · 13:13"]);
    await expect(page.locator(".hero-graph")).toHaveClass(/lit-alert/, { timeout: 15_000 });  // the story played to the end
  });

  test("navigation, calls to action and the logo", async ({ page }) => {
    await page.goto("/");
    for (const a of await page.locator(".nav-links a").all()) expect((await a.boundingBox())!.height).toBeLessThan(40);  // one line each
    const hrefs = await page.locator(".nav-links a").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
    expect(hrefs).toEqual(["#incident", "#timeline", "#how", "#nightjar", "#cli"]);
    await expect(page.locator(`a[href="${REPLAY}"]`)).toHaveCount(4);  // nav, hero, Nightjar, end
    await expect(page.locator(".nav .logo-mark")).toBeVisible();
    await expect(page.locator(".foot")).toContainText("Graph Hacks 2026");
  });

  test("the logo ring turns a notch on every page load", async ({ page }) => {
    await page.goto("/");
    await expect.poll(() => page.evaluate(() => Number(sessionStorage.getItem("chokepoint-ring")))).toBe(1);
    await page.reload();
    await expect.poll(() => page.evaluate(() => Number(sessionStorage.getItem("chokepoint-ring")))).toBe(2);
  });

  test("incident, timeline, how it works, why a graph", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("#incident .feat")).toHaveCount(3);
    await expect(page.locator(".fair-note")).toContainText("didn't do anything wrong");
    await expect(page.locator("#tl .tl-item")).toHaveCount(7);
    await expect(page.locator("#tl .tl-time")).toHaveText([
      "Before 13:12", "13:12:10 UTC", "13:13:05 UTC", "13:13:05 UTC", /^13:12\s+14:26$/, "14:26:51 UTC", "14:47 · Sept 13",
    ]);
    await expect(page.locator("#tl .tl-item.tone-agent")).toContainText("Nightjar would have spoken up");
    await expect(page.locator("#how .feat")).toHaveCount(3);
    await expect(page.locator("#graph pre")).toContainText("algo.BFS");
    await expect(page.locator("#limits")).toHaveCount(0);  // removed on purpose
    await expect(page.locator(".broke")).toContainText("I'm broke");
    await expect(page.locator("#tl .tl-time svg.flow")).toHaveCount(1);
    expect(await page.locator("body").innerText()).not.toContain("→");  // arrows are icons, never the font-less character
  });

  test("scrolling reveals every section and lights the timeline", async ({ page }) => {
    await page.goto("/");
    for (const id of ["#incident", "#timeline", "#how", "#nightjar", "#graph", "#real", "#cli"]) {
      await page.locator(id).scrollIntoViewIfNeeded();
      await expect(page.locator(`${id} .sec-head`)).toBeVisible();
    }
    await page.locator("#tl .tl-item").last().scrollIntoViewIfNeeded();
    await expect(page.locator("#tl .tl-item.lit").first()).toBeAttached();
    await page.locator(".end-card").scrollIntoViewIfNeeded();
    await expect(page.locator(".end-card h2")).toBeVisible();
  });

  test("Nightjar and the CLI are on the page, with real output", async ({ page }) => {
    await page.goto("/");
    const nj = page.locator("#nightjar");
    await nj.scrollIntoViewIfNeeded();
    await expect(nj.locator("h2")).toHaveText("Nightjar watches from the shadows.");
    await expect(nj.locator(".term")).toContainText("13:13:05  ALERT  chalk@5.6.1");
    expect(await nj.locator(".term .window-body").evaluate((pre) => pre.scrollWidth - pre.clientWidth)).toBeLessThanOrEqual(0);  // every line fits
    await expect(nj.locator(".term")).toContainText("Nightjar spoke up 74 minutes before any advisory existed.");
    await expect(nj.locator(".agent-points .feat")).toHaveCount(3);
    await expect(nj.locator("a.btn.primary")).toHaveAttribute("href", "/app?project=webpack/webpack-dev-server@fa9195c");
    const cli = page.locator("#cli");
    await cli.scrollIntoViewIfNeeded();
    await expect(cli.locator(".term")).toContainText("pipx install --python 3.12 ckpoint");
    await expect(cli.locator(".term")).toContainText("chokepoint nightjar");
    await expect(page.locator(".broke a").first()).toHaveAttribute("href", "#cli");
    await expect(page.locator(".broke a.birdy")).toHaveAttribute("href", "#nightjar");  // the note introduces the bird
    await expect(page.locator(".broke")).toContainText("This app runs on free-tier servers");
  });

  test("every section is consistent: centred icons, alternating backgrounds, aligned examples", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const report = await page.evaluate(() => {
      const offCentre = [...document.querySelectorAll(".itile")].filter((t) => {
        const a = t.getBoundingClientRect(), s = t.querySelector("svg")!.getBoundingClientRect();
        return Math.abs((s.left + s.width / 2) - (a.left + a.width / 2)) > 0.5 || Math.abs((s.top + s.height / 2) - (a.top + a.height / 2)) > 0.5;
      }).length;
      const kinds = [...document.querySelectorAll("main > section[id]")].map((s) => (s.classList.contains("band") ? "band" : "plain"));
      const exBottoms = [...document.querySelectorAll("#how .feat .ex")].map((e) => Math.round(e.getBoundingClientRect().bottom));
      const labelTones = [...document.querySelectorAll(".sec-head .badge")].map((b) => b.className).filter((c) => c !== "badge" && c !== "badge ok live");
      return { offCentre, kinds, exBottoms, labelTones };
    });
    expect(report.offCentre).toBe(0);
    expect(report.kinds.every((k, i) => i === 0 || k !== report.kinds[i - 1])).toBe(true);  // never two alike in a row
    expect(new Set(report.exBottoms).size).toBe(1);
    expect(report.labelTones).toEqual([]);
    // every section headline fits on one line on a laptop-sized window
    const lines = await page.locator(".sec-head h2").evaluateAll((hs) =>
      hs.map((h) => Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight))));
    expect(lines.every((n) => n === 1)).toBe(true);
  });

  test("reduced motion shows everything at once", async ({ browser }) => {
    const ctx = await browser.newContext({ reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto("/");
    await expect(page.locator(".hero-sec h1")).toBeVisible();
    await expect(page.locator("[data-count]")).toHaveText("74 min");
    await expect(page.locator("#cli .cli-points li").first()).toBeVisible();
    await ctx.close();
  });

  test("live project cards come from the graph", async ({ page }) => {
    await page.goto("/");
    const cards = page.locator("#real-cards .real-card");
    await expect(cards).toHaveCount(2);
    await expect(cards.locator(".real-name")).toHaveText(["mochajs/mocha", "webpack/webpack-dev-server"]);
    for (const card of await cards.all()) {
      await expect(card.locator(".mini li")).toHaveCount(3);
      await expect(card.locator(".mini .who").first()).toHaveText(/^@/);
      expect(await card.getAttribute("href")).toMatch(/^\/app\?project=/);
    }
    await expect(page.locator("#recent-scans")).toBeHidden();  // no visitor scans in the test data
  });
});

test.describe("scan a public repo", () => {
  const cp = {
    direct: { direct: 12, prod: 7 },
    ranking: [
      { maintainer: "alice", reach: 6, rank: 1 }, { maintainer: "bob", reach: 4, rank: 2 }, { maintainer: "carol", reach: 2, rank: 3 },
    ],
  };
  const stats = { nodes: { Version: 120, Maintainer: 33 } };

  async function mockScan(page: Page, outcome: "ok" | "busy") {
    let polls = 0;
    await page.route("**/api/scan**", async (route) => {
      const req = route.request();
      if (req.method() === "POST") {
        if (outcome === "busy") return route.fulfill({ status: 400, json: { detail: "Busy scanning someone/else for someone else." } });
        expect(req.postDataJSON()).toEqual({ repo: "acme/widgets" });
        return route.fulfill({ json: { repo: "acme/widgets", state: "running", stage: 1 } });
      }
      polls += 1;
      return route.fulfill({ json: polls < 2 ? { repo: "acme/widgets", state: "running", stage: 2, packages: 120 }
        : { repo: "acme/widgets", state: "done", seconds: 12.4 } });
    });
    await page.route("**/api/tool/graph_stats", (route) => route.fulfill({ json: stats }));
    await page.route("**/api/tool/chokepoints", (route) => route.fulfill({ json: cp }));
  }

  // The scan card fades in when it scrolls into view, like every section: scroll there first.
  async function toScanCard(page: Page) {
    await page.goto("/");
    await page.locator("#scan-card").scrollIntoViewIfNeeded();
    await expect(page.locator("#scan-repo")).toBeVisible();
  }

  test("an empty submit explains what to type", async ({ page }) => {
    await toScanCard(page);
    await page.locator("#scan-btn").click();
    await expect(page.locator("#scan-error")).toBeVisible();
    await expect(page.locator("#scan-error")).toContainText("Type a repository first");
  });

  test("progress, then the result with the top chokepoints", async ({ page }) => {
    await mockScan(page, "ok");
    await toScanCard(page);
    await page.locator("#scan-repo").fill("acme/widgets");
    await page.locator("#scan-btn").click();
    await expect(page.locator("#scan-progress")).toBeVisible();
    await expect(page.locator("#sp-repo")).toHaveText("acme/widgets");
    const result = page.locator("#scan-result");
    await expect(result).toBeVisible();
    await expect(result).toContainText("Scanned in 12s");
    await expect(result).toContainText("120 packages · 33 maintainer accounts");
    await expect(result.locator(".mini li")).toHaveCount(3);
    await expect(result.locator(".who")).toHaveText(["@alice", "@bob", "@carol"]);
    await expect(result.locator("a.btn.primary")).toHaveAttribute("href", "/app?project=acme%2Fwidgets");
    await expect(page.locator("#scan-progress")).toBeHidden();
    await result.locator("[data-again]").click();
    await expect(result).toBeHidden();
    await expect(page.locator("#scan-repo")).toHaveValue("");
  });

  test("an example chip scans that repo", async ({ page }) => {
    let asked = "";
    await page.route("**/api/scan**", (route) => {
      asked = route.request().postDataJSON()?.repo ?? asked;
      return route.fulfill({ status: 400, json: { detail: "No package-lock.json found." } });
    });
    await toScanCard(page);
    await page.locator('#scan-card .chip[data-repo="axios/axios"]').click();
    await expect(page.locator("#scan-repo")).toHaveValue("axios/axios");
    await expect(page.locator("#scan-error")).toContainText("No package-lock.json found.");
    expect(asked).toBe("axios/axios");
  });

  test("a busy server says so and offers a retry", async ({ page }) => {
    await mockScan(page, "busy");
    await toScanCard(page);
    await page.locator("#scan-repo").fill("acme/widgets");
    await page.locator("#scan-btn").click();
    const err = page.locator("#scan-error");
    await expect(err).toContainText("Couldn't scan acme/widgets.");
    await expect(err).toContainText("Busy scanning");
    await expect(err.locator("[data-retry]")).toBeVisible();
    await expect(page.locator("#scan-btn")).toHaveText("Scan");
    await expect(page.locator("#scan-btn")).toBeEnabled();
  });
});

test.describe("404", () => {
  test("an unknown page shows the 404 page; an unknown API path stays JSON", async ({ page, request }) => {
    const res = await page.goto("/no/such/page");
    expect(res?.status()).toBe(404);
    await expect(page.locator("h1")).toHaveText("Nothing to watch here.");
    await expect(page.locator(".nf-text code")).toHaveText("/no/such/page");
    await expect(page.getByRole("link", { name: "Back to the story" })).toHaveAttribute("href", "/");
    const api = await request.get("/api/no-such-thing");
    expect(api.status()).toBe(404);
    expect(await api.json()).toHaveProperty("detail");
  });
});
