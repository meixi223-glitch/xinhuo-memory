import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const token = "browser-fixture-token-not-a-real-secret";
async function login(page: any) {
  await page.goto("/");
  await page.getByLabel("访问 Token").fill(token);
  await page.getByRole("button", { name: "进入记忆观察室" }).click();
  await expect(
    page.getByRole("button", { name: "已连接", exact: true }),
  ).toBeVisible();
}
test("real login, empty state, server config, memory actions and logout", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "连接记忆库" })).toBeVisible();
  await page.getByLabel("访问 Token").fill("bad-token");
  await page.getByRole("button", { name: "进入记忆观察室" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await login(page);
  await expect(page.getByText("还没有情绪坐标")).toBeVisible();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByText("记忆整理", { exact: true }).click();
  const form = page.getByRole("form", { name: "记忆整理配置" });
  await form.getByLabel("API 地址").fill("http://127.0.0.1:9/v1");
  await form.getByLabel("API Key", { exact: true }).fill("fixture-worker-key");
  await form.getByLabel("工作模型").selectOption("custom");
  await form.getByLabel("模型 ID", { exact: true }).fill("fixture-model");
  await form.getByRole("button", { name: "保存记忆整理配置" }).click();
  await expect(
    form.getByText("已保存到服务器，下一次模型请求生效。"),
  ).toBeVisible();
  await expect(form.getByLabel("API Key", { exact: true })).toHaveValue("");
  const local = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  expect(local).not.toContain("fixture-worker-key");
  expect(local).not.toContain(token);
  await page.reload();
  await page.getByText("记忆整理", { exact: true }).click();
  await expect(
    page
      .getByRole("form", { name: "记忆整理配置" })
      .getByLabel("API Key", { exact: true }),
  ).toHaveAttribute("placeholder", "已配置；留空保留原密钥");
  await page.getByRole("button", { name: "记忆", exact: true }).click();
  await page.getByText("添加片段与查找记忆", { exact: true }).click();
  await page.getByLabel("留下一段片段").fill("浏览器验收：周末去植物园。");
  await page.getByRole("button", { name: "保存片段", exact: true }).click();
  await expect(
    page.getByText("浏览器验收：周末去植物园。").first(),
  ).toBeVisible();
  const report = await request.post("/affect/self-report", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      turn_id: "browser-fixture-turn",
      model: "fixture-primary",
      valence: 0.5,
      arousal: 0.35,
      dims: { joy: 0.12, trust: 0.11 },
      reason: "想到周末的安排，感到期待。",
      evidence: ["周末去植物园"],
      confidence: 0.9,
      stated_at: new Date().toISOString(),
    },
  });
  expect(report.ok()).toBeTruthy();
  const res = await request.post("/api/tool", {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: "memory_upsert",
      arguments: {
        content: "一条可以固定与归档的测试记忆",
        summary: "可操作的测试记忆",
        emotion_label: "中性",
        emotion_intensity: 1,
      },
    },
  });
  expect(res.ok()).toBeTruthy();
  await page.reload();
  await page.getByText("可操作的测试记忆", { exact: true }).first().click();
  await page.getByRole("button", { name: "固定记忆", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByText("可操作的测试记忆", { exact: true }).first().click();
  await expect(
    page.getByRole("button", { name: "取消固定", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "归档记忆", exact: true }).click();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "连接记忆库" })).toBeVisible();
  expect(errors).toEqual([]);
});
for (const width of [320, 390, 1280])
  test(`live layout ${width}px and accessible pages`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await login(page);
    for (const name of ["状态", "记忆", "记录", "设置"]) {
      await page.getByRole("button", { name, exact: true }).click();
      await expect(page.locator("main h1")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      await page.evaluate(async () => {
        await Promise.all(
          document
            .getAnimations()
            .filter(
              (a) => a.effect?.getComputedTiming().iterations !== Infinity,
            )
            .map((a) => a.finished.catch(() => {})),
        );
      });
      const axe = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();
      expect(
        axe.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => n.target),
        })),
      ).toEqual([]);
    }
    if (width === 390) {
      await page.getByRole("button", { name: "状态", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "状态", exact: true }),
      ).toHaveAttribute("aria-current", "page");
      await page.screenshot({
        path: "test-results/live-mobile.png",
        fullPage: true,
        animations: "disabled",
      });
    }
  });


test('dark mode remains accessible', async ({page}) => {
  await login(page);
  await page.getByRole('button',{name:'设置',exact:true}).click();
  await page.getByRole('button',{name:'深色',exact:true}).click();
  for(const name of ['状态','记忆','记录','设置']) {
    await page.getByRole('button',{name,exact:true}).click();
    await page.evaluate(async()=>{await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});
    const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze();
    expect(result.violations.map(v=>v.id)).toEqual([]);
  }
});
