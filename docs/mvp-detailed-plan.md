# MemoCard AI：MVP 产品、页面与算法详细规划

**状态：** MVP 规划已获批准；模块代码在工作区逐步实现并验证，待开发者审核后再创建本地 Commit。Push 仍需另行批准。
**依据：** AGENTS.md、docs/frontend-design.md、docs/database-design.md、当前数据库迁移和工作区代码。

## 0. 当前实际完成情况

项目已有 React/Vite 底座、登录/注册/会话恢复/个人资料页面、登录后首页外壳和学习资料页；后端已有 FastAPI 认证 API、PostgreSQL 会话实现，以及带所有权检查的资料上传/下载/软删除 API。数据库迁移已定义 users、auth_sessions、documents、document_chunks、chat_sessions、chat_messages、message_citations、flashcards、flashcard_sources、flashcard_reviews。

SM-2 纯函数已在本地 Commit 310c7dd；评分 API、PostgreSQL 事务、幂等键和时区资料字段已在本地 Commit 97cc40d。资料上传/列表/下载/软删除模块、PDF/TXT/PPTX 解析与 pgvector 索引、RAG 问答 API、闪卡生成/编辑/管理 API 与页面、SM-2 单卡复习界面、复习日历和首页真实复习摘要已在工作区实现并通过本地测试，均待开发者审核。本地部署准备已加入 Python 3.12 pin、Vercel Function 排除规则、环境模板和部署手册；CLI 的 Windows 本地路由模拟因 symlink 权限失败。聊天、闪卡和评分迁移 003–007 均未应用到 Neon。Neon 生产连接、Vercel Blob 存储、pgvector 迁移和真实 DeepSeek 调用尚未验证或接通。浏览器此前显示的演示账号和内容只是本地预览数据，不代表 Neon 有真实账号或记录。

所以本文件描述将要做的 MVP，不宣称这些功能已经完成。

## 1. 产品目标和完成定义

主学习路径：注册登录 → 上传资料 → 提取文字、切块、建立索引 → 带引用问答 → 从回答生成并编辑闪卡 → SM-2 评分排期 → 首页和日历查看今日/逾期/未来复习。

MVP 完成要同时满足：真实 UI/API/数据库贯通；空、加载、失败、重试状态完整；每个资源都按用户隔离；回答引用能回到资料；复习记录与卡片当前状态一致。空数据要显示真实空状态，不能用写死数量假装功能已存在。

## 2. 已确认的视觉与交互规则

- 白色内容面为主，登录及登录后页面共享浅蓝渐变 #EFF5FF → #DCE9FF → #EDF0FF。
- 页面网格、标题位置、左对齐、间距和列表列线全站一致；信息按标题、分组和分隔线归类，不堆在同一页。
- 每页一个主操作。必要信息默认展示；低频操作用命名清楚的菜单、按钮、抽屉、详情或折叠区承载。
- 桌面正文最大宽约 1200px，阅读正文更窄；手机侧栏变菜单抽屉、列表变单列，不横向挤压。
- 登录页不放猪图、不画替代吉祥物。首页复习区域按原图展示用户提供的第二张布里布里左卫门图片，不重绘、不放到其他页面。
- 状态同时用文字/图标表达，不只依赖颜色。交互控件有焦点、加载、禁用、错误状态并支持键盘操作。
- 页面切换约 140–180ms 轻淡入/轻移；按钮约 100–140ms 按压反馈；抽屉/弹窗约 200–300ms 微弹性；卡片翻面约 280–340ms。动画表达反馈，不循环装饰；遵守 prefers-reduced-motion。
- 圆角、阴影用于需要层级的内容面/浮层，不给每个小区块加卡片外框。

## 3. 逐页布局规划

### 全局框架
桌面左侧固定导航：首页、学习资料、AI 问答、闪卡、复习日历；底部个人资料和退出。选中项清晰。手机顶栏打开同序菜单抽屉，关闭后焦点回到菜单按钮。各页面统一为标题/简述 → 一个主操作 → 主任务 → 按需查看次级内容 → 就地反馈状态。

### 登录/注册
共享一页但一次只显示一个表单；品牌文字、蓝色渐变、白色表单。邮箱、密码、提交、切换登录/注册、字段错误。提交期间防重复并显示进度；成功进首页，会话过期回登录并解释。沿用现有认证接口。

### 首页
问候/日期；主视觉为今日待复习数量与“开始复习”，为零时显示完成与下一次时间。次要区域最多展示少量最近资料及处理状态、失败重试、“查看全部资料”。最近学习只显示最近一项入口。第二张原图放在复习引导区，窄屏移到文字按钮下方。所有计数必须来自 API。

### 学习资料
主按钮“上传资料”。行内仅显示名称、格式/大小、上传时间、处理中/可问答/失败状态。搜索和状态过滤收进“筛选”。行点击详情；次级菜单有重试和删除。上传面板说明限制、显示进度与取消。仅服务端确认收到后才显示已接收。

### 资料详情
显示名称、大小、日期、状态与处理时间线：已上传→提取中→索引中→可问答；失败显示原因和重试。提取正文默认折叠，用户选择后按页/幻灯片展开。无文本的扫描 PDF 显示未识别文字，若首版不含 OCR 不得标为成功。删除需二次确认。

### AI 问答
桌面会话栏可折叠，手机从“对话”抽屉打开。中央只展示当前会话；新会话默认全选已就绪资料，也可指定范围。顶部显示对话和资料范围。回答正文宽约 760px；引用编号轻量呈现，来源折叠后显示文件、页/幻灯片和核对摘录。底部固定提问框，发送时不跳版。无资料给上传入口；证据不足要明确说资料不够，不补造事实。回答保存后提供“生成闪卡”；模型错误显示可重试。

### 闪卡库与编辑
显示待复习数、卡片列表、主按钮“开始复习”。全部/待复习、来源和关键词过滤按需打开。每行问题摘要、下次日期、来源摘要。编辑器展示问题/答案/来源，修改内容不重置排期。AI 生成先返回草稿，用户逐张编辑/删除，确认后才入库。MVP 不做牌组或标签。

### 复习模式
一屏只显示一张卡：进度 → 问题 → 显示答案 → 来源和评分 → 展示新排期 → 下一卡。中途退出保留已提交评分，未提交不评分。完成后简短总结并可回首页/日历。建议常驻四个选项：忘了 q=0、困难但想起 q=3、记住 q=4、轻松 q=5；q=1/2 放“更精确评分”入口。是否直接常驻六档待确认。

### 日历
默认近期任务列表；用户可切换月历，避免同屏塞满列表和月历。分组逾期/今天/未来 7 天，任务可开始复习。月历每天仅显示数量，点击才显示当天卡片。月份前后切换、返回今天。按个人 IANA 时区计算本地日期，存 UTC；空日使用轻量空状态。

### 个人资料
显示姓名、邮箱和时区；姓名/时区可编辑。邮箱若暂不支持验证流程则只读。退出为次级操作，不增加未批准的通知/语言功能。

## 4. 数据关系与向量存储

PostgreSQL 是业务记录和访问控制事实源：用户、文件元信息/状态、规范 chunk 文本及位置、向量、对话、引用、卡片、来源、复习事件。向量存在 Neon PostgreSQL 的 pgvector 列中，避免在 Vercel 和 Neon 之外再托管一个数据库。

chunk 文本和向量由 PostgreSQL 单一事务保存；稳定 chunk UUID 作为主键，失败时可重试。只有全部向量保存成功后 documents.status 才成为 ready。删除先将文档标为 deleting/已软删除，使它立即退出所有检索；向量与 chunk 同属 PostgreSQL，可保留以满足现有引用外键策略，检索时必须排除非 ready 文档。

现有迁移有软删除、页/幻灯片定位、SM-2 状态和评分前后快照。迁移 003 新增 users.timezone（IANA 名称、默认 UTC）与 flashcard_reviews.idempotency_key（按用户唯一，并以历史 review 的 id 回填）。迁移文件尚未应用到 Neon。不增加 revision_schedules 表，日历从 next_review_at 派生。

文件二进制放私有 Vercel Blob，数据库只存 `storage_key`；不放 Vercel 临时磁盘。上传先支持 PDF、UTF-8 TXT、PPTX，单文件最大 4 MiB；SQL 约束保留已有旧式 PPT 元数据，但 API 不接受新的 `.ppt` 文件。旧式 PPT 需转换能力，不能视为自动兼容。首版 PDF 仅保证文本层解析；扫描 PDF 没有文字时要报告需 OCR。[python-pptx 文档](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html)、[pypdf 文本提取说明](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)。

建议关系图：

~~~mermaid
erDiagram
    USER ||--o{ AUTH_SESSION : owns
    USER ||--o{ DOCUMENT : owns
    DOCUMENT ||--o{ DOCUMENT_CHUNK : contains
    USER ||--o{ CHAT_SESSION : owns
    CHAT_SESSION ||--o{ CHAT_MESSAGE : contains
    CHAT_MESSAGE ||--o{ MESSAGE_CITATION : has
    DOCUMENT_CHUNK ||--o{ MESSAGE_CITATION : cited_by
    USER ||--o{ FLASHCARD : owns
    CHAT_MESSAGE o|--o{ FLASHCARD : may_generate
    FLASHCARD ||--o{ FLASHCARD_SOURCE : supported_by
    DOCUMENT ||--o{ FLASHCARD_SOURCE : source
    FLASHCARD ||--o{ FLASHCARD_REVIEW : review_history
~~~

向量检索使用 Neon 支持的 pgvector。FastEmbed 在 FastAPI 侧使用 `intfloat/multilingual-e5-small` 本地生成 384 维文本向量；该步骤不把资料发送给 embedding API。模型首次加载需下载文件，Vercel 冷启动和函数资源限制仍需部署验证。

## 5. 上传、切块与 RAG

### 上传/处理生命周期
状态：uploaded → processing → chunked → ready；任一步失败到 failed。`chunked` 表示文本及来源定位已存 PostgreSQL，但向量索引尚未完成，因此不能问答。删除先进入 `deleting` 并立即禁止新检索，完成存储清理后变成 `deleted`；清理失败时可重试。

1. 验证会话、大小、扩展名和实际文件签名。文件名仅用于显示，私有存储路径由服务端按用户 ID 和随机 ID 生成。
2. 文件成功写入私有 Blob 后创建 PostgreSQL 行并返回已接收。若数据库写入失败，服务端尝试移除刚上传的 Blob。
3. 当前解析模块使用 pypdf 提取 PDF 文本层、UTF-8 TXT 和 python-pptx 的幻灯片文本/表格；页码/幻灯片号从 1 起，损坏、加密、超限或无文本内容给可读失败原因。图片 OCR 不在当前模块范围内。
4. 当前首轮切块会规范空白、保持每页/幻灯片来源边界，并使用可复现的中英文字数估算（约 600 个估算单位、80 单位重叠）；这不是 embedding tokenizer 的精确 token 数，需按检索评估结果调整。
5. PostgreSQL 在单个事务中保存稳定 UUID、顺序、内容、位置、content hash，并将状态更新为 `chunked`。重试会原子替换仅处于处理阶段的旧块。
6. 后端使用 FastEmbed 和 multilingual-e5-small 生成 384 维向量，并在 PostgreSQL 事务中保存到对应 chunk。
7. 所有向量保存成功后才标 ready；部分失败保留安全错误并可重试。删除先将 PG 状态设为 `deleting`，再清理 Blob；若 Blob 清理失败，保留状态和安全错误提示，允许重试。检索端只查询 `ready` 文档。

### 检索与生成
- 先由已认证用户查询 PostgreSQL 中 ready 文件 ID；指定资料时与用户允许的 ID 取交集。
- pgvector 检索必须在同一 SQL 查询中按 `document_chunks.user_id`、`documents.user_id`、资料范围和 `documents.status = 'ready'` 过滤。
- 初始 top-k 取 6 作为评估参数，不是永久最佳值；相似度阈值由标注问题集校准。若精准术语召回差，再评估关键词/混合检索。
- 后端按 PG 元数据组装来源，不让模型编造页码/文件名。
- 没有证据时不生成事实性答案；有证据时将带编号片段给 DeepSeek，要求仅据片段回答、事实后附来源号。服务器验证引用号属于本次检索，事务保存 assistant message 和 citation。超时/限流/无效输出显示可重试错误，不伪装成功。
- DeepSeek 官方文档确认 Chat API 兼容 OpenAI/Anthropic 格式；模型名在服务器配置。[DeepSeek 接入文档](https://api-docs.deepseek.com/quick_start/agent_integrations/)。

首版模型已选为 multilingual-e5-small（384 维）。若将来换模型，需按新维度创建新列/索引并重建向量，不能混合不同向量空间。上线前需评估中文/英文检索效果、模型包体和冷启动。

## 6. 闪卡生成逻辑

1. 用户从有来源引用的回答点生成；服务器验证消息所有权。
2. 只取该回答的 citation chunks 和来源，不无限发送整个聊天。
3. 模型返回严格结构化 question、answer、source_refs；一轮建议最多 5 张。
4. 服务器检查格式、长度、非空字段；source_refs 仅可指向本次可信来源。
5. 同批规范化问题去重；近似重复提示用户。
6. 返回未保存草稿；用户编辑/删卡并确认后，在一个事务写 flashcards、flashcard_sources。
7. 保存 source_message_id 与文档/块链接。
8. 不合格 JSON 或模型失败不产生半张卡；可重试。

## 7. SM-2 详细规则

### 状态和公式
新卡：repetition_count=0，EF=2.500，interval_days=0，立即待复习。repetition_count 表示连续成功次数，评分 q 为 0–5：

- 5 完美；4 正确但犹豫；3 很困难但答对；2 错误但答案似乎容易；1 错误但答案有印象；0 完全忘记。
- 初始 EF=2.5；成功后的第 1、2 次间隔分别 1、6 天；第 3 次及以后计算新间隔时使用本次评分前已有的 EF：interval=ceil(前次 interval × 当前 EF)。本次评分更新出的 EF 用于后续排期。
- EF' = max(1.3, EF + 0.1 − (5 − q) × (0.08 + (5 − q) × 0.02))。
- q<3：重置连续成功次数为 0，按经典规则 EF 保持原值，下一间隔 1 天。
- q≥3：先按本次评分前的状态计算当前间隔（第一成功后 1 天，第二成功后 6 天，其后乘当前 EF 并向上取整），再将成功次数 +1 并按公式更新 EF。新 EF 用于下次及之后的间隔。
- EF 不低于 1.3。集中为一个纯函数；使用 Decimal/整数毫单位，写入现有 NUMERIC(6,3) 三位小数，避免不同层自行计算。

评分等级、公式、间隔和下限参考 [SuperMemo 原始 SM-2 说明](https://www.supermemo.com/en/archives1990-2015/english/ol/sm2)。

### 评分事务
建议 POST /api/flashcards/{card_id}/reviews：

1. 认证并确认卡片属该用户。
2. 单一事务 SELECT … FOR UPDATE 锁卡。
3. 校验 q=0…5 与幂等 key。
4. 按用户本地日历日计算下一日期，再转 UTC；不要简单加 24 小时，以处理夏令时。
5. 插入 flashcard_reviews，含 q 和评分前后 repetition/EF/interval/next_review_at 快照。
6. 更新 flashcards 当前状态并提交，响应新状态和本地日期。
7. 幂等请求返回首次结果；并发评分锁序列化，避免两次同时用同一个旧状态计算。

建议仅允许给到期/逾期卡评分；提前卡可看但不改变排期。是否允许提前评分待确认。q=0、1、2 均重置；q=3 更新 EF 并成功；q=4 EF 不变；q=5 提升 EF。资料删除后卡片是否继续复习取决于已批准的保留策略。

## 8. 日历和 API

日历不存重复 schedule rows。按用户时区构造本地每日边界并转 UTC 查 next_review_at，逾期/今天/未来七日分组；月历只汇总每天计数，点开再查卡片。列表/月历共用一套查询服务。

建议端点（每一项都服务端认证并验证 user_id）：

| 功能 | API 草案 |
|---|---|
| 资料 | GET/POST /api/documents；GET/DELETE /api/documents/{id}；POST /api/documents/{id}/retry |
| 直传（仅选 Blob 后） | POST /api/documents/upload-token |
| 聊天 | GET/POST /api/chat/sessions；GET /api/chat/sessions/{id}/messages；POST /api/chat/sessions/{id}/messages |
| 卡片生成/管理 | POST /api/flashcards/generate；GET/POST /api/flashcards；PATCH/DELETE /api/flashcards/{id} |
| 评分 | POST /api/flashcards/{id}/reviews |
| 日历 | GET /api/revisions?from=…&to=…；GET /api/revisions/day?date=… |
| 首页摘要 | GET /api/dashboard/summary |

异步状态首版可轻量轮询；SSE/逐字流式单独评估 Vercel 限制。

## 9. 安全与部署注意

- 所有资源查询由服务器以会话 user_id 检查，不能仅依靠前端隐藏。
- 写操作检查请求来源，沿用 HttpOnly/SameSite/Secure cookie；若拆分域名需重新审核 CORS/CSRF。
- DeepSeek key、Neon 地址和上传 token 仅服务端使用，禁止写入 VITE_*。
- 上传校验扩展名/MIME/签名、大小、页数、处理时长和解压内容限制。
- Vercel Functions request/response body 上限是 4.5 MB；所选 FastAPI 服务端上传将每个文件限制为 4 MiB，留出 multipart 请求开销。[限制说明](https://vercel.com/docs/functions/limitations)。
- 用户资料保存在私有 Vercel Blob，由 Python SDK 上传和读取；API 根据会话与 PostgreSQL 所有权检查后代理下载。Vercel 项目仍需创建并连接私有 Blob Store，线上上传尚不能运行。[Python 私有 Blob 指南](https://vercel.com/kb/guide/python-and-vercel-blob)。
- 文档解析和模型调用可能超时；先限制文件、把步骤做成可重试并实测，再决定是否加队列/worker。Vercel Python runtime 文档目前标 Beta，上线前重核限制。[Python runtime](https://vercel.com/docs/functions/runtimes/python)。
- Neon 用合适连接策略，环境凭据分离；不将 DATABASE_URL 提交或回显。
- 向量、来源文本和所有权数据同存在 Neon；迁移与备份须覆盖 pgvector 列及 HNSW 索引。
- 日志不记录密码、Cookie、密钥、上传全文或完整隐私对话。

## 10. 分阶段计划与验收

### 0. 方案审核
页面和核心规划已审核；文档存储确定为私有 Vercel Blob，支持 PDF/TXT/PPTX，最大 4 MiB。向量方案已改为 Neon pgvector，模型为 FastEmbed multilingual-e5-small；聊天资料范围和引用保留细节仍待相应模块实施前讨论。当前 branch 是 feature/authentication；保留现有工作区更改，不切分支、不 Push。

### 1. 文件存储与资料管理
范围包括 backend/app/documents、backend/app/storage、API 路由、资料列表/上传 UI、requirements.txt 和迁移 004。代码已在工作区实现；本地 API 测试通过，尚未连接 Neon 或 Vercel Blob，也待开发者审核。验收：文件限制准确、上传状态真实、归属正确、软删除立即排除检索、存储清理失败可重试。

### 2. 解析、分块与 pgvector 索引（已在工作区实现，待整体审核）
实现范围：backend/app/processing、资料处理 API、迁移 005/006、pypdf/python-pptx、FastEmbed 与 pgvector。已执行的后端测试通过；Neon 迁移尚未应用，Vercel 冷启动/部署尚未验证。验收：页/幻灯片定位准确；重试不会产生重复 PostgreSQL 块；损坏/空文件有清楚错误；跨用户不串数据；只有全部向量持久化后才可问答。

### 3. RAG 问答（已在工作区实现，待审核）
实现范围：`backend/app/chat`、DeepSeek Chat Completions 适配器、迁移 007、AI 问答页面与导航。每轮先检索当前用户/会话范围内 ready 文件的 pgvector 块，再把最近对话和标记来源的摘录发送给 DeepSeek；引用标签只会映射到本次检索到的块。AI 失败不保存半轮对话。验收：引用指向真实块；资料范围正确；无可用资料时不调用模型；历史可读；超时/限流诚实显示。尚未连接真实 DeepSeek key 或 Neon。

### 4. 闪卡草稿和管理（已在工作区实现，待审核）
实现 `backend/app/flashcards`、生成/列表/编辑/删除 API、聊天回答草稿确认弹窗和闪卡库页面。生成只使用该回答的真实引用，校验 JSON、来源编号和同批重复问题；确认前不写入数据库。保存时在 PostgreSQL 事务中写卡片和来源，列表/编辑/删除均检查所有权。专属闪卡测试通过；完整后端套件与前端构建已验证。无新迁移或依赖。真实 DeepSeek 与 Neon 尚未接通，线上生成/持久化未验证。

### 5. SM-2 复习（界面已在工作区实现，待审核）
在 `src/review/ReviewPage.jsx` 逐张加载到期卡片，先显示问题、用户主动翻看答案，再选择 0–5 记忆质量；评分通过既有 API 更新 SM-2 状态，按服务器返回的下次复习时间推进队列。失败时保留本次幂等键及评分，允许同一请求安全重试；完成和无到期卡片均显示明确状态。首页入口和侧边栏导航已连接。既有纯函数/API 测试覆盖 EF 下限、1/6 天间隔、失败重置、重复请求和时区边界；Neon 尚未应用迁移，真实数据库流程未验证。

### 6. 首页和日历接真数据（已在工作区实现，待审核）
新增 `GET /api/dashboard/summary` 与 `GET /api/revisions`、`GET /api/revisions/day`，全部使用会话 user_id 和 PostgreSQL 中的 IANA 时区；日历范围最多 42 天，按本地日期边界统计并查询当天卡片。首页真实展示逾期、今天、未来 7 天和下一张卡片时间；日历支持月份切换、每日数量和当天卡片列表，并可从到期日期进入复习。没有新增表、迁移或依赖。Neon 尚未连接，因此线上 SQL 未在实际数据库验证。

### 7. MVP 集成与部署审核
本地准备已完成：固定 Python 3.12、排除 Vercel Python Function 中的开发文件、提供无密钥环境模板和部署/迁移/Smoke test 手册。Python 3.12.14 下安装现有 requirements 后 52 项后端测试通过，前端构建通过；Vercel CLI 65.14.0 已下载，但 `vercel dev --local` 在 Windows 建立缓存 symlink 时返回 EPERM，因此路由模拟未通过。尚未链接 Vercel 项目、配置平台环境变量、创建 Blob Store、连接 Neon、应用迁移或部署。发布与 GitHub Push 仍单独等待批准。

## 11. Git 流程

每个模块严格按：讨论具体实现和文件/数据变化 → 等待明确批准 → 只实现该模块 → 相关测试并报告 → 等待用户审核 → 审核通过后清晰本地 Commit → Push 前列出文件、Commit、Branch 并再次等待明确批准。

建议提交信息：feat: add document upload and status tracking；feat: index chunks with Neon pgvector；feat: add cited RAG chat；feat: generate editable flashcard drafts；feat: implement SM-2 review scheduling；feat: add timezone-aware revision calendar。

规划完成不等于功能完成；模块实现情况按上方状态逐项记录。

## 12. 需要开发者决定的事项

以下只提建议，不会擅自实施：

1. 首版扫描 PDF 不做 OCR 并提示，是否接受？
2. 主评分放 q=0/3/4/5 加精确评分 q=1/2，还是常驻六档？
3. 是否只允许对已到期卡评分？
4. 删除资料后保留聊天/卡片来源快照并清理文件，还是连学习历史一起删除？
5. MVP 是否要逐字流式聊天？建议先做稳定完整回答、引用、取消/重试，再单独评审流式。

默认建议是先审页面和产品逻辑；数据库变更、额外依赖、外部服务、代码仍逐项审批。

## 13. 官方参考

- [SuperMemo 原始 SM-2 算法](https://www.supermemo.com/en/archives1990-2015/english/ol/sm2)
- [Neon pgvector](https://neon.com/docs/extensions/pgvector)
- [Neon Connection Pooling](https://neon.com/docs/connect/connection-pooling)
- [DeepSeek API](https://api-docs.deepseek.com/quick_start/agent_integrations/)
- [Vercel Function Limits](https://vercel.com/docs/functions/limitations)
- [Private Vercel Blob storage with Python](https://vercel.com/kb/guide/python-and-vercel-blob)
- [Vercel Blob Client Uploads](https://vercel.com/docs/vercel-blob/client-upload)
- [Vercel Python Runtime](https://vercel.com/docs/functions/runtimes/python)
- [pypdf Text Extraction](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)
- [python-pptx Quickstart](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html)

\n
