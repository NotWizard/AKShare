# 双主题色彩体系重设计方案（Observatory Dark × Paper Light）

> 2026-08-30 · ui-redesign worktree · 状态：方案定稿（随实现同步维护）

## 0. 背景与问题

现状（Terminal Fintech / 第一轮 Observatory Dark）的问题：

1. **只有暗色一套**：无亮色模式，白天/外接显示器场景可读性差。
2. **配色口碑差**：cyan #22d3ee 强调色在深蓝底上「发飘」；图表线色偏藏青/青色，层次弱。
3. **色彩角色冲突**：强调色与相位语义色（复苏绿/衰退蓝…）同场竞争，图表区色彩纪律不严。
4. 色板凭感觉堆，缺少「品牌色 / 语义色 / 数据色」三层分离的体系化定义。

## 1. 设计参照（调研结论）

| 参照 | 学到什么 |
|---|---|
| **Linear / Vercel / Stripe** 仪表盘 | 深色 = 近黑蓝灰底 + 单一高饱和「电蓝」品牌色；阴影在暗色下变成「微光」，边框极细 |
| **Bloomberg / 交易终端** | 数据区色彩纪律：绿涨红跌琥珀警示是行业语义，品牌色不得占用 |
| **Dribbble 2025–26 金融看板趋势** | 深炭底 + 高对比单点强调；亮色模式 = 冷白纸面 + 皇家蓝 CTA |
| **ui-ux-pro-max 调色板库** | 金融看板基线：深色 #020617/#0E1223 + trust blue；亮色知识蓝 #1E3A8A 系 |
| **色彩心理学（金融）** | 蓝 = 信任/理性/机构感；紫 = AI 俗套（弃）；青 = 廉价科技感（本轮被点名，弃） |

**核心决策**：品牌色从 cyan 换成「电蓝」家族（暗色 #5B8CFF / 亮色 #2F5BFF）——暗色下清晰、亮色下深邃，两端都是同一品牌基因；与相位语义色（玉绿/朱红/琥珀/钢蓝）保持距离。

## 2. 三层色彩架构

```
品牌层  brand/accent     —— 交互、主按钮、激活态、图表第 1 系列
语义层  up/down/warn     —— 涨跌/松紧/警示（行业语义，锁定不变义）
数据层  PALETTE[8]       —— 多系列图表的区分色（中性、可分辨性优先）
```

## 3. 完整 Token 表

### 3.1 暗色主题（默认）· Obsidian Blue

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#070B12` | 页面底（近黑蓝，非纯黑保深度） |
| `--surface` | `#0C1322` | 侧栏/顶栏 |
| `--card` | `#101A2B` | 卡片面 |
| `--card-hover` | `#152236` | hover 抬升 |
| `--border` / `--border-hi` | `rgba(148,163,184,.10)` / `.18` | 发丝边框 |
| `--accent` | `#5B8CFF` | 电蓝品牌色（按钮/激活/焦点环） |
| `--accent-hi` | `#7FA6FF` | hover 提亮 |
| `--accent-ink` | `#06122B` | accent 上的文字 |
| `--accent-soft` | `rgba(91,140,255,.14)` | 激活态底 |
| `--up` / `--down` / `--warn` / `--info` | `#34D399` / `#F87171` / `#FBBF24` / `#60A5FA` | 语义色 |
| `--text` / `-2` / `-3` / `-4` | `#E8EEF7` / `#9BAAC0` / `#7C8DA5` / `#7F90A4` | 四级文字（AA 已验） |
| `--shadow-card` | `0 1px 2px rgba(0,0,0,.24)` | 卡片投影（暗色下极轻） |

图表 PALETTE（暗）：`#5B8CFF #A78BFA #FBBF24 #34D399 #F87171 #60A5FA #FB923C #F472B6`

### 3.2 亮色主题 · Paper

| Token | 值 | 对比度要点 |
|---|---|---|
| `--bg` | `#F6F7F9` | 冷白纸面（非纯白，防刺眼） |
| `--surface` | `#FFFFFF` | 侧栏/顶栏 |
| `--card` | `#FFFFFF` | 卡片白 |
| `--card-hover` | `#F8FAFC` | |
| `--border` / `--border-hi` | `#E3E8EF` / `#CBD5E1` | |
| `--accent` | `#2F5BFF` | 皇家蓝；白底对比 5.9:1 ✓AA |
| `--accent-hi` | `#1E40AF` | hover 加深（亮色 hover 向下走） |
| `--accent-ink` | `#FFFFFF` | |
| `--accent-soft` | `rgba(47,91,255,.10)` | |
| `--up` / `--down` / `--warn` / `--info` | `#059669` / `#DC2626` / `#B45309` / `#2563EB` | 白底 AA 全过 |
| `--text` / `-2` / `-3` / `-4` | `#0F172A` / `#334155` / `#475569` / `#64748B` | 4.5:1 起步（亮色 text-4 必须 ≥#64748B） |
| `--shadow-card` | `0 1px 2px rgba(15,23,42,.05)` | 亮色卡片靠投影分层 |

图表 PALETTE（亮）：`#2F5BFF #7C3AED #B45309 #047857 #DC2626 #2563EB #C2410C #DB2777`

### 3.3 相位语义色（双套）

| 相位 | 暗 | 亮 |
|---|---|---|
| 复苏 / easing / 主动补库 / 美丽去杠杆… | `#34D399` | `#059669` |
| 过热 / 被动补库 / stable 系 | `#FBBF24` | `#B45309` |
| 滞胀 / 紧缩 / 主动去库 / 丑陋去杠杆… | `#F87171` | `#DC2626` |
| 衰退 / 被动去库 / 稳定收缩 | `#60A5FA` | `#2563EB` |
| 中性 | `#7C8DA5` | `#64748B` |

## 4. 切换机制（技术方案）

1. **CSS 变量双套**：`tokens.css` 的 `:root` 放暗色（默认），`:root[data-theme='light']` 放亮色覆盖；`tailwind.config.ts` 的色板改为 `var(--bg)` 引用——现有全部 `bg-card`/`text-text-2` 等工具类零改动自动双主题。
2. **`stores/theme.ts`**：`mode: 'dark'|'light'` + `version`（变更计数）+ `toggle()`；初始读 localStorage，缺省跟系统 `prefers-color-scheme`；写 `document.documentElement.dataset.theme` + `color-scheme`。
3. **ECharts 适配**：`echarts.theme.ts` 的 `COLORS/PALETTE` 由常量改为 `chartTheme()` 函数按当前主题取值；各页 option computed 增加 `void theme.version` 依赖，切换即整图重建（vue-echarts setOption 合并，缩放/图例状态由 notMerge=false 保留）。
4. **顶栏切换按钮**：☾/☀ 图标（沿用现有 unicode 图形语汇，不引图标库），`aria-label="切换亮/暗色主题"`。
5. **相位色**：`phases.ts` 改双 map 按主题取值（同 chartTheme 机制）。
6. 切换过渡只过渡 `background-color/border-color/color`（150ms），图表不参与 CSS 过渡（由 option 重建接管），避免全局 transition 抖动。

## 5. 验收标准

- 顶栏一键切换，全站（含所有图表）即时换肤，无刷新残留色
- 两主题下：正文对比度 ≥4.5:1、按钮文本 ≥4.5:1、图表网格/轴标清晰可辨
- 相位语义在两套主题下 hue 一致（绿=扩张、红=收缩、琥珀=中性/过热、蓝=衰退），仅明度不同
- vitest / vue-tsc / build 全绿；两主题各页面截图存档
