import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const nav = async (page: any, label: string) =>
  page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: label, exact: true })
    .click();
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "情绪的形状", exact: true }),
  ).toBeVisible();
});
test("mobile navigation, layouts, and no personal content", async ({
  page,
}) => {
  for (const [label, heading] of [
    ["状态", "情绪的形状"],
    ["记忆", "记忆，是我们之间的回声。"],
    ["记录", "每一刻，都有来处。"],
    ["设置", "照看记忆的生长。"],
  ]) {
    await nav(page, label);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(await page.locator("body").innerText()).not.toMatch(
      /PRIVATE_NAME|INTERNAL_HOST|PRIVATE_MESSAGE/,
    );
  }
});
test("timeline merges evidence before filtering and supports empty search", async ({
  page,
}) => {
  await nav(page, "记忆");
  await expect(page.locator(".timeline-entry")).toHaveCount(7);
  await expect(page.getByText("跨渠道已合并")).toHaveCount(2);
  await page.getByLabel("按渠道筛选").selectOption("论坛");
  await expect(page.locator(".timeline-entry")).toHaveCount(2);
  await page.getByLabel("搜索记忆").fill("绝对不会匹配的词");
  await expect(page.getByText("这段时间，暂时没有找到")).toBeVisible();
  await page.getByLabel("清空搜索").click();
  await page.getByLabel("按渠道筛选").selectOption("企微");
  await expect(
    page.getByRole("heading", { name: "给记忆一个可以回来的地方" }),
  ).toBeVisible();
  await page.getByLabel("按时间筛选").selectOption("today");
  await page.getByLabel("按类型筛选").selectOption("memory");
  await expect(page.locator(".timeline-entry")).toHaveCount(2);
});
test("recall details and all Johari areas work", async ({ page }) => {
  await nav(page, "记忆");
  await page.getByRole("tab", { name: /每轮召回/ }).click();
  await expect(page.locator(".recall-card")).toHaveCount(2);
  await page.locator(".recall-item").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("关闭弹窗").click();
  await page.getByRole("tab", { name: "乔哈里之窗" }).click();
  await page.getByRole("button", { name: /未知区/ }).click();
  const first = await page.locator(".unknown-modal>p").innerText();
  await page.getByRole("button", { name: "再翻一页" }).click();
  expect(await page.locator(".unknown-modal>p").innerText()).not.toBe(first);
  await page.getByLabel("关闭弹窗").click();
  await page.getByRole("button", { name: /盲目区/ }).click();
  await expect(page.getByRole("dialog")).toContainText("整日印象");
  await page.getByRole("button", { name: "去补上我的视角" }).click();
  await expect(page.getByRole("tab", { name: "每日印象" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(
    page.getByRole("heading", { name: "每一刻，都有来处。" }),
  ).toBeVisible();
});
test("AI owns the scene and self reports; human legacy drafts are not AI reports", async ({
  page,
}) => {
  await page.evaluate(() =>
    localStorage.setItem(
      "xinhuo-self-reports",
      JSON.stringify([
        {
          id: "old",
          at: new Date().toISOString(),
          v: 0.1,
          a: 0.2,
          label: "旧的人类草稿",
          reason: "旧的人类自评",
          quote: "不要混入 AI 自评",
        },
      ]),
    ),
  );
  await page.reload();
  await expect(
    page.locator(".scene-fields").getByText("状态", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("有一点期待，也有被理解的安心。")).toBeVisible();
  await page.getByRole("button", { name: "翻阅自评" }).click();
  await expect(
    page.getByText("自己选择的情绪，和当时写下的理由。"),
  ).toBeVisible();
  await expect(page.locator(".journal-entry")).toHaveCount(3);
  await expect(page.getByText("自述", { exact: true })).toHaveCount(3);
  await expect(page.getByText("旧的人类自评")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "记一笔心情" })).toHaveCount(0);
  expect(
    await page.evaluate(() => localStorage.getItem("xinhuo-self-reports")),
  ).toContain("旧的人类自评");
  await page.getByRole("tab", { name: "每日印象" }).click();
  await expect(page.getByRole("heading", { name: "当日印象" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "你的补充" })).toBeVisible();
});
test("daily personal supplement survives refresh", async ({ page }) => {
  await nav(page, "记录");
  await page.getByRole("tab", { name: "每日印象" }).click();
  await page.getByRole("button", { name: "补上我的视角" }).click();
  await page.getByLabel("补充今天的感受").fill("另一半故事，也是我的声音。");
  await page.getByRole("button", { name: "保存补充" }).click();
  await expect(page.getByText("另一半故事，也是我的声音。")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "每日印象" }).click();
  await expect(page.getByText("另一半故事，也是我的声音。")).toBeVisible();
});
test("workers save separate model/API/key configurations locally, with no egress", async ({
  page,
}) => {
  await nav(page, "设置");
  await expect(page.locator(".worker-item")).toHaveCount(8);
  await expect(page.getByText("界面状态预览")).toHaveCount(0);
  const requests: string[] = [];
  page.on("request", (r) =>
    requests.push(r.url() + JSON.stringify(r.headers()) + (r.postData() || "")),
  );
  for (const [name, model, key] of [
    ["记忆整理", "curation-model", "mock-only-curation-key"],
    ["情绪自评", "emotion-model", "mock-only-emotion-key"],
    ["向量嵌入", "embedding-model", "mock-only-embedding-key"],
  ]) {
    await page.locator("summary").filter({ hasText: name }).click();
    const form = page.getByRole("form", { name: name + "配置" });
    await form.getByLabel("API 地址").fill("https://example.invalid/" + model);
    await form.getByLabel("API Key", { exact: true }).fill(key);
    await expect(form.getByLabel("API Key", { exact: true })).toHaveAttribute(
      "type",
      "password",
    );
    await form.getByLabel("工作模型").selectOption("custom");
    await form
      .getByRole("textbox", { name: "模型 ID", exact: true })
      .fill(model);
    await form.getByRole("button", { name: "保存" + name + "配置" }).click();
    await expect(
      form.getByText("已保存到此浏览器，仅用于这项工作。"),
    ).toBeVisible();
    await page.locator("summary").filter({ hasText: name }).click();
  }
  await expect(page.getByText("3 / 8 项已保存到本机")).toBeVisible();
  expect(requests.some((r) => /mock-only-|example.invalid/.test(r))).toBe(
    false,
  );
  await page.reload();
  for (const [name, model, key] of [
    ["记忆整理", "curation-model", "mock-only-curation-key"],
    ["情绪自评", "emotion-model", "mock-only-emotion-key"],
    ["向量嵌入", "embedding-model", "mock-only-embedding-key"],
  ]) {
    await page.locator("summary").filter({ hasText: name }).click();
    const form = page.getByRole("form", { name: name + "配置" });
    await expect(
      form.getByRole("textbox", { name: "模型 ID", exact: true }),
    ).toHaveValue(model);
    await expect(form.getByLabel("API Key", { exact: true })).toHaveValue(key);
    await expect(form.getByLabel("API Key", { exact: true })).toHaveAttribute(
      "type",
      "password",
    );
  }
  await page
    .getByRole("form", { name: "情绪自评配置" })
    .getByRole("button", { name: "清除本机密钥" })
    .click();
  await page.reload();
  await page.locator("summary").filter({ hasText: "情绪自评" }).click();
  await expect(
    page
      .getByRole("form", { name: "情绪自评配置" })
      .getByLabel("API Key", { exact: true }),
  ).toHaveValue("");
  await page.locator("summary").filter({ hasText: "记忆整理" }).click();
  await expect(
    page
      .getByRole("form", { name: "记忆整理配置" })
      .getByLabel("API Key", { exact: true }),
  ).toHaveValue("mock-only-curation-key");
});
test("legacy worker config migrates once without copying its key to other roles", async ({
  page,
}) => {
  await page.evaluate(() =>
    localStorage.setItem(
      "xinhuo-model-config",
      JSON.stringify({
        endpoint: "https://example.invalid/v1",
        model: "custom",
        custom: "old-model",
        apiKey: "old-local-key",
        provider: "OpenAI 兼容",
      }),
    ),
  );
  await nav(page, "设置");
  await page.locator("summary").filter({ hasText: "记忆整理" }).click();
  const form = page.getByRole("form", { name: "记忆整理配置" });
  await expect(
    form.getByRole("textbox", { name: "模型 ID", exact: true }),
  ).toHaveValue("old-model");
  await expect(form.getByLabel("API Key", { exact: true })).toHaveValue(
    "old-local-key",
  );
  await form.getByRole("button", { name: "保存记忆整理配置" }).click();
  await page.locator("summary").filter({ hasText: "情绪自评" }).click();
  await expect(
    page
      .getByRole("form", { name: "情绪自评配置" })
      .getByLabel("API Key", { exact: true }),
  ).toHaveValue("");
  expect(
    await page.evaluate(() => localStorage.getItem("xinhuo-model-config")),
  ).toBeNull();
});
// Fixture changes happen only in the test browser's module responses, never in product UI.
const fixture = async (page: any, path: string, script: string) => {
  await page.route("**/src/" + path + "*", async (route: any) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      body: (await response.text()) + "\n" + script,
    });
  });
};
test("empty content appears in place after loading real empty fixture", async ({
  page,
}) => {
  await fixture(
    page,
    "mocks/snapshot.ts",
    `
    demo.mood = { v:null, a:null, label:"", dimensions:{}, updatedAt:"", note:"" };
    demo.scene = { focus:"", phase:"", body:"", transition:"", expiresAt:null };
    for (const key of ["entries","reports","impressions","recalls","unknown"]) demo[key] = [];
    for (const key of Object.keys(demo.stats)) demo.stats[key] = 0;
  `,
  );
  await page.reload();
  await expect(
    page.getByRole("status", { name: "正在加载", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("还没有情绪坐标")).toBeVisible();
  await expect(page.getByText("现在，还没有被描画")).toBeVisible();
  await nav(page, "记忆");
  await expect(page.getByText("这段时间，暂时没有找到")).toBeVisible();
  await page.getByRole("tab", { name: "每轮召回" }).click();
  await expect(page.locator(".empty")).toBeVisible();
  await page.getByRole("tab", { name: "乔哈里之窗" }).click();
  await page.getByRole("button", { name: /未知区/ }).click();
  await expect(page.getByText("门后暂时还是一片空白")).toBeVisible();
  await page.getByLabel("关闭弹窗").click();
  await nav(page, "记录");
  await expect(page.getByText("还没有留下自评")).toBeVisible();
  await page.getByRole("tab", { name: "每日印象" }).click();
  await expect(page.getByText("还没有每日印象")).toBeVisible();
  await nav(page, "设置");
  await expect(
    page.getByText("还没有数据，第一段记忆会从这里开始。"),
  ).toBeVisible();
});
test("fresh data expires with time and failure can retry without a state selector", async ({
  page,
}) => {
  await page.clock.install();
  await fixture(
    page,
    "mocks/snapshot.ts",
    `demo.expiresAt = demo.scene.expiresAt = new Date(Date.now()+4000).toISOString();`,
  );
  await page.reload();
  await expect(page.getByText("情景帧保鲜中")).toBeVisible();
  await page.clock.fastForward(5000);
  await expect(page.getByText("stale · 等待新的情景帧")).toBeVisible();
  await expect(page.locator(".scene-card")).toHaveClass(/stale/);
  await expect(
    page.getByText("这是一份旧快照，等待下一次更新。"),
  ).toBeVisible();
  await fixture(
    page,
    "api.ts",
    `const originalSnapshot = api.getSnapshot; api.getSnapshot = async () => { if (!window.fixtureRecovered) throw new Error("读取暂时失败"); return originalSnapshot(); };`,
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "记忆暂时没有回来" }),
  ).toBeVisible();
  await page.evaluate(() => ((window as any).fixtureRecovered = true));
  await page.getByRole("button", { name: "再试一次" }).click();
  await expect(
    page.getByRole("heading", { name: "情绪的形状", exact: true }),
  ).toBeVisible();
});
test("worker roles are supplied by the adapter catalogue", async ({ page }) => {
  await fixture(
    page,
    "mocks/workers.ts",
    `mockWorkers.push({ ...mockWorkers[0], id:"new-role", name:"额外工作", description:"由配置增加的用途" });`,
  );
  await page.reload();
  await nav(page, "设置");
  await page.locator("summary").filter({ hasText: "额外工作" }).click();
  await expect(
    page
      .getByRole("form", { name: "额外工作配置" })
      .getByLabel("API Key", { exact: true }),
  ).toBeVisible();
});
test("emotion vocabulary is supplied by configuration", async ({ page }) => {
  await page.route("**/src/config.ts*", async (route) => {
    const res = await route.fetch();
    await route.fulfill({
      response: res,
      body: (await res.text())
        .replaceAll("喜悦", "明朗")
        .replaceAll("惊喜", "轻快")
        .replace(/\\u559c\\u60a6/gi, "明朗")
        .replace(/\\u60ca\\u559c/gi, "轻快"),
    });
  });
  await page.reload();
  await expect(
    page.locator(".component-row").filter({ hasText: "明朗" }),
  ).toBeVisible();
  await expect(page.locator(".wheel-center strong")).toHaveText("轻快");
});
test("320px and 430px views have no overflow; dark mode and reduced motion", async ({
  page,
}) => {
  for (const width of [320, 430]) {
    await page.setViewportSize({ width, height: 844 });
    for (const tab of ["状态", "记忆", "记录", "设置"]) {
      await nav(page, tab);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.getByRole("button", { name: "深色", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await nav(page, "状态");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .locator(".emotion-dot")
      .evaluate((el) => getComputedStyle(el, "::before").animationName),
  ).toBe("none");
});
test("core screens have no serious accessibility issues", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const label of ["状态", "记忆", "记录", "设置"]) {
    await nav(page, label);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
});

test("touch scrolling keeps the last content above the bottom bar", async ({
  page,
}) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: 190, y: 650 }],
  });
  for (let y = 610; y >= 210; y -= 40)
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: 190, y }],
    });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  expect(await page.evaluate(() => scrollY)).toBeGreaterThan(100);
  await page.evaluate(() => scrollTo(0, document.body.scrollHeight));
  expect(
    await page.evaluate(
      () =>
        document.querySelector(".app-foot")!.getBoundingClientRect().bottom <
        document.querySelector(".bottom-nav")!.getBoundingClientRect().top,
    ),
  ).toBe(true);
});
test("Johari and dark screens remain accessible", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await nav(page, "记忆");
  await page.getByRole("tab", { name: "乔哈里之窗" }).click();
  expect(
    (
      await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()
    ).violations.map((v) => v.id),
  ).toEqual([]);
  await nav(page, "设置");
  await page.getByRole("button", { name: "深色", exact: true }).click();
  for (const label of ["状态", "记忆", "记录", "设置"]) {
    await nav(page, label);
    expect(
      (
        await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()
      ).violations.map((v) => ({
        id: v.id,
        targets: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
});
