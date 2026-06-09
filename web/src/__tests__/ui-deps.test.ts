/**
 * TC-2.1: npm包安装验证
 * TC-2.2: 现有前端测试不被破坏
 */

import { describe, it, expect } from "vitest";

// TC-2.1: react-resizable-panels、react-diff-viewer、ui组件文件存在
describe("TC-2.1: 依赖安装验证", () => {
  it("react-resizable-panels已安装", async () => {
    const mod = await import("react-resizable-panels");
    expect(mod.Panel).toBeDefined();
    expect(mod.Group).toBeDefined();
  });

  it("react-diff-viewer-continued已安装", async () => {
    const mod = await import("react-diff-viewer-continued");
    expect(mod.default).toBeDefined();
  });

  it("Dialog组件文件存在", async () => {
    const mod = await import("../components/ui/dialog");
    expect(mod.Dialog).toBeDefined();
  });

  it("Badge组件文件存在", async () => {
    const mod = await import("../components/ui/badge");
    expect(mod.Badge).toBeDefined();
  });

  it("Tooltip组件文件存在", async () => {
    const mod = await import("../components/ui/tooltip");
    expect(mod.Tooltip).toBeDefined();
  });

  it("ScrollArea组件文件存在", async () => {
    const mod = await import("../components/ui/scroll-area");
    expect(mod.ScrollArea).toBeDefined();
  });

  it("Separator组件文件存在", async () => {
    const mod = await import("../components/ui/separator");
    expect(mod.Separator).toBeDefined();
  });
});