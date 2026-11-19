# AlgoHub · 算法评测平台（前端原型）

用于统一收集、管理、测试、评估算法与数据集的平台前端原型。交互模式参考 Hugging Face（卡片列表 + 左侧筛选、详情页 Tab、右侧推理组件、README 卡片），所有数据均为本地 mock，不依赖后端。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 类型检查 + 生产构建
```

> 如果 `npm install` 因网络中断漏装了原生依赖（报错 `Cannot find module '@rolldown/binding-win32-x64-msvc'`），重新执行一次 `npm install` 即可。项目 `.npmrc` 使用 npmmirror 镜像。

## 技术栈

Vue 3 + Vite + TypeScript · Tailwind CSS v4 · Reka UI（无样式交互组件）· lucide 图标 · marked（README 渲染）。依赖均为 MIT / ISC 许可。

## 目录

```
src/
  api/index.ts      # 服务层：函数签名按将来 FastAPI REST 接口设计，现由 mock 实现
  mock/             # 组织/用户、数据集、算法、评测基准、评测记录
  types/            # 领域模型
  stores/session.ts # 当前身份（角色切换器）、主题、权限判断
  utils/synth.ts    # 程序化生成预览图（无外部图片）
  components/       # 布局、卡片、推理组件、排行榜图表等
  views/            # 页面
```

## 页面

| 路由 | 页面 |
| --- | --- |
| `/` | 首页 / 探索 |
| `/algorithms`、`/algorithms/:org/:name` | 算法列表、算法详情（卡片 / 文件与版本 / 评测记录 + 在线推理） |
| `/datasets`、`/datasets/:org/:name` | 数据集列表、详情（卡片 / 训练集 / 测试集 / 版本） |
| `/benchmarks`、`/benchmarks/:id` | 评测基准列表、排行榜（对比、精度/速度散点、规则） |
| `/evals`、`/evals/new`、`/evals/:id` | 评测任务队列、发起评测、任务详情（指标、复现信息、日志、错误样例） |
| `/algorithms/new`、`/datasets/new`、`/benchmarks/new` | 创建向导 |
| `/orgs/:id` | 厂商 / 内部命名空间主页 |
| `/admin/{users,reviews,vendors}`、`/vendors/new` | 管理后台：账号管理、厂商提交审核、厂商入库 |
| `/login` | 静态登录页 |

## 数据集结构

每个数据集分为**训练集**和**测试集**，分开上传、各自有版本，内部结构一致：

```
train/ 或 test/
├── images/        # 具体数据（图片 / 信号文件等）
├── masks/         # 仅分割任务：掩码 PNG
└── labels.csv     # 真值，UTF-8（兼容 BOM），必有 file_name 列
```

| 任务 | labels.csv 必需列 | 行规则 |
| --- | --- | --- |
| 分类 / 信号 | file_name, label | 一个文件一行 |
| 检测 / OCR / 关键点 | file_name, label, x_min, y_min, x_max, y_max | 一个框一行；无目标的图写一行且 label 留空 |
| 分割 | file_name, mask_file | 一个文件一行 |
| 优化求解 | file_name, best_known | 一个算例一行 |

可选条件列（weather、light、occlusion、scene 等）填写后，评测可按条件拆分结果。上传时校验：必需列、label 是否在类别表内、框坐标、与另一部分表头一致、文件存在、训练 / 测试间按哈希去重。训练集所有账号可下载；测试集仅管理员可查看与下载，评测时算法只读取 `images/`。

## 厂商与算法申报（《智能运维平台算法中心算法标准 1.0》）

- **新建厂商** `/vendors/new`（仅管理员）：标准第四部分 1–7 项（企业主体、联系方式、对接人、资质 / 软著 / 专利 / 其他知识产权）+ `packageinfo.xml` 中的 `vendor.id / zh_CN / en_US`，可同时为对接人开通厂商账号。
- **新建算法** `/algorithms/new`：6 步向导，字段、必选 / 可选与最大长度（按 UTF-8 字节）取自第一部分表 A.1–A.7；第二部分声明支持的分析参数；第四部分 8–17 项交付材料与 18–34 项内容自查。提交前可预览自动生成的 `packageinfo.xml`、`managementinfo.json`、`technicalinfo.json`，提交后在算法详情“申报信息”页签查看。
- 标准未规定的部分由平台约定：算法分类的行业编码表为示例；资源占用单位为 MB / 核。
- 管理员与演示账号不属于任何组织；厂商账号必须归属某个厂商。

## 账号类型与权限

右上角头像菜单可切换演示身份，页面的可见范围与可用操作随之变化。

| | 管理员 | 演示账号 | 厂商账号 |
| --- | --- | --- | --- |
| 算法 | 全部可见 | 全部可见 | 仅自己的 |
| 提交算法 | ✓（直接构建） | ✗ | ✓（需管理员审核） |
| 训练 / 验证集 | 查看、下载 | 查看、下载 | 查看、下载 |
| 测试集 | 查看、下载、编辑 | 不可见 | 不可见，但可在其上发起评测 |
| 发起评测 | 任意算法 | ✗ | 仅自己的算法 |
| 排行榜 | 全部 | 全部 | 仅自己的成绩与名次 |
| 在线推理 | ✓ | ✓ | ✓（自己的算法） |
| 数据集 / 评测基准 / 账号 / 审核 | ✓ | ✗ | ✗ |

## 接入真实后端

只需替换 `src/api/index.ts` 中各函数的实现为 `fetch` 调用，页面代码无需修改。权限过滤目前在 mock 层模拟，真实环境应由后端完成。
