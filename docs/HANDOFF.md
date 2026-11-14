# MemoCard AI — 当前状态交接（2026-11-12）

给下一个接手的人/AI。**先读完再动代码。**

## 1. 仓库状态

- 分支 `feature/authentication`，最新提交以 `git log -1` 为准（本文不记录哈希，避免过期）
- 后端 59 个测试全部通过；前端 `npm run build` 通过
- 前端部署在 **Vercel**，后端在 **Render**，数据库 **Neon + pgvector**

## 2. 这几天解决的主线问题

**文档索引失败（OOM）** —— 这是最长的一条线，结论已定：

| 尝试 | 结果 |
|---|---|
| 前端超时 20s → 120s | 无效，方向错 |
| `model.onnx` 448 MB | **必然 OOM**（512 MB 实例） |
| `model_O4.onnx` 224 MB | 仍 OOM |
| int8 113 MB | 仍 OOM |
| **`BAAI/bge-small-en-v1.5` 63 MB** | ✅ 索引成功，RAG 可用 |

现在嵌入模型是 `bge-small-en-v1.5`（**英文专用**），这是为了塞进 512 MB 的取舍。
副作用：**中文提问的检索会失效**。要修需换多语言模型（需更大实例）或加混合检索。

## 3. 已完成的改动（按主题）

- 聊天：删除对话（保留闪卡、解除关联）；问题排序修复（`ORDER BY created_at, role, id`）
- 复习：写答案 → AI 判断对错（`POST /api/flashcards/{id}/answer-check`）→ 三档评分；练习模式；评分回执
- 日历：按文件分组、默认折叠；点某天只复习那天
- 闪卡：按文件分组；删整组（走项目对话框）；保存去重
- 学习数据：新页面 + `GET /api/analytics/summary`（正确率/掌握度/未来 7 天）
- 前端：设计令牌、统一 1120px 布局、统一标题、玻璃按钮、页面淡入 340ms、英文文案减字

## 4. 还没做（按优先级）

1. **AI 问答：会话列表移入左侧导航**（三次尝试未完成，最需要做）
   - 会话状态在 `ChatPage` 内，必须上提到 `App.jsx`
   - 用 Portal 试过，构建失败已回滚
   - 目标：点 "AI chat" 时在导航内展开历史，右侧不再有 History 按钮
2. **输入框固定底部**（`position: sticky` 未生效，需拆分消息区/输入区结构）
3. **文档索引失败的根因** —— 若再次出现，看 Render 日志的 traceback（已加 `exc_info=True`）
4. `AI_HANDOFF.md` 仍过期（讲的是"改超时"），可删或按本文重写

## 5. 硬性约束（不要违反）

- **不加 UI 框架、图标库、图表库、动画库**（见 `docs/frontend-design.md`）
- 设计令牌在 `src/styles.css` 顶部 `:root`
- 危险操作必须用项目统一的 `<dialog>` 确认
- 英文文案必须短（中文长度的 1.5 倍以内），否则英文版显乱
- 改完必须：`npm run build` + `python -m unittest discover -s tests`
- 推送前等用户确认

## 6. 已知环境坑

- DSH 浏览器插件曾配置为 `channel: chrome`，会弹你的 Chrome；
  已改回 `bundled`（`~/.dsh/dsh-builtin-browser-host/settings.json`）
- 512 MB 实例上任何大模型都会 OOM，不要再用大头文件
- 上传上限已改为 15 MiB（原 4 MiB 是 Vercel 时代的限制）
- 文档处理改成了前端轮询状态，服务端仍是同步接口
