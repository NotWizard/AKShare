<script setup lang="ts">
// AI 设置 — profiles 管理 + 连接测试（M4a 配置层）+ 模板编辑器 + 生成历史（M4c 呈现层）。
// 纯页面内局部 ref，不建 pinia store（设置页无跨组件共享态，YAGNI）。
// 布局（UI 重设计）：三大块从全宽平铺改为分区 tab；模板编辑器改主-从布局（左键列表 · 右编辑面板）。
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { api } from '@/api/client'
import type { AiProfile, AiProfileList, AiTestResult, Commentary, CommentaryHistoryItem } from '@/api/types'

const PRESETS: Record<AiProfile['preset'], string> = {
  dashscope: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  deepseek: 'https://api.deepseek.com',
  openrouter: 'https://openrouter.ai/api/v1',
  custom: '',
}
const PRESET_LABELS: Record<AiProfile['preset'], string> = {
  dashscope: '通义 DashScope', deepseek: 'DeepSeek', openrouter: 'OpenRouter', custom: '自定义',
}
const btnCls = 'text-xs px-2.5 py-1 rounded-lg border border-border hover:border-border-hi text-text-2 transition-colors disabled:opacity-50'
const inputCls = 'w-full bg-surface border border-border rounded-lg px-2.5 py-1.5 text-sm text-text placeholder:text-text-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent'

// ── 页内分区（平铺三大块改 tab）─────────────────────────────────────────────
type Section = 'profiles' | 'templates' | 'history'
const section = ref<Section>('profiles')
const SECTIONS: [Section, string][] = [['profiles', 'Profiles 配置'], ['templates', '提示词模板'], ['history', '生成历史']]

const active = ref<string | null>(null)
const profiles = ref<AiProfile[]>([])
const pageError = ref<string | null>(null)

function apply(r: AiProfileList) { active.value = r.active_profile; profiles.value = r.profiles }
async function load() {
  try { apply(await api.getAiProfiles()); pageError.value = null }
  catch (e) { pageError.value = (e as Error).message }
}
onMounted(() => { void load(); void loadTemplates(); void loadHistory() })

// ── 连接测试 / 设默认 / 删除 ────────────────────────────────────────────────
const testing = ref<string | null>(null)
const testResults = ref<Record<string, AiTestResult>>({})
const confirmName = ref<string | null>(null)

async function runTest(name: string) {
  testing.value = name
  try { testResults.value[name] = await api.testAiProfile(name) }
  catch (e) { testResults.value[name] = { ok: false, latency_ms: null, error: (e as Error).message } }
  finally { testing.value = null }
}
async function setActive(name: string) {
  try { apply(await api.setAiActive(name)); pageError.value = null }
  catch (e) { pageError.value = (e as Error).message }
}
async function remove(name: string) {
  try { await api.deleteAiProfile(name); confirmName.value = null; await load() }
  catch (e) { pageError.value = (e as Error).message }
}

// ── 模板编辑器（M4c；主-从布局）─────────────────────────────────────────────
const TPL_ORDER = ['system', 'merrill', 'credit', 'inventory', 'debt', 'real_estate', 'fiscal_external', 'overall']
const TPL_LABELS: Record<string, string> = {
  system: '系统提示', merrill: '美林时钟', credit: '信用周期', inventory: '库存周期',
  debt: '债务周期', real_estate: '房地产', fiscal_external: '财政与外需', overall: '总体研判',
}
const tplDefaults = ref<Record<string, string>>({})
const tplDraft = ref<Record<string, string>>({})
const tplInitial = ref<Record<string, string>>({})
const tplHash = ref('')
const tplSaving = ref(false)
const tplMsg = ref<string | null>(null)
const tplMsgOk = ref(true)
const tplSel = ref('system')   // 主-从布局当前选中的模板键
// 无改动不保存：避免误触 _save 造成假 stale
const tplDirty = computed(() => JSON.stringify(tplDraft.value) !== JSON.stringify(tplInitial.value))

function applyTpl(overrides: Record<string, string>, hash: string) {
  const next: Record<string, string> = {}
  for (const k of TPL_ORDER) next[k] = overrides[k] ?? ''
  tplInitial.value = { ...next }
  tplDraft.value = next
  tplHash.value = hash
}
async function loadTemplates() {
  try {
    const r = await api.getAiTemplates()
    tplDefaults.value = r.defaults
    applyTpl(r.overrides, r.template_hash)
  } catch (e) { tplMsg.value = (e as Error).message; tplMsgOk.value = false }
}
async function saveTpl() {
  tplSaving.value = true
  tplMsg.value = null
  try {
    const r = await api.saveAiTemplates(tplDraft.value)
    applyTpl(r.overrides, r.template_hash)   // 服务端规范化为准（纯空白被移除）
    tplMsg.value = '已保存——评论已标记过期，重新生成后生效'
    tplMsgOk.value = true
  } catch (e) { tplMsg.value = (e as Error).message; tplMsgOk.value = false }
  finally { tplSaving.value = false }
}

// ── 生成历史（M4c）──────────────────────────────────────────────────────────
const batches = ref<CommentaryHistoryItem[]>([])
const historyError = ref<string | null>(null)
const batchDetails = ref<Record<string, Commentary>>({})
const batchLoading = ref<Record<string, boolean>>({})
const batchErrors = ref<Record<string, string>>({})

async function loadHistory() {
  try { batches.value = (await api.getCommentaryHistory()).items; historyError.value = null }
  catch (e) { historyError.value = (e as Error).message }
}
// 首次展开懒加载单批详情；按 ts 缓存，重复展开不再请求（失败不缓存 → 可重试）
async function toggleBatch(b: CommentaryHistoryItem, e: Event) {
  if (!(e.target as HTMLDetailsElement).open) return
  const ts = b.generated_at
  if (batchDetails.value[ts] || batchLoading.value[ts]) return
  batchLoading.value[ts] = true
  try { batchDetails.value[ts] = await api.getCommentaryBatch(ts) }
  catch (err) { batchErrors.value[ts] = (err as Error).message }
  finally { batchLoading.value[ts] = false }
}

// ── 新增/编辑 dialog（焦点管理/Esc 同 HealthLight 基线）────────────────────
const dialogOpen = ref(false)
const editing = ref(false)
const formError = ref<string | null>(null)
const form = reactive({ name: '', preset: 'custom' as AiProfile['preset'], endpoint: 'chat_completions' as AiProfile['endpoint'], base_url: '', model: '', temperature: 0.3, api_key: '' })
const triggerRef = ref<HTMLElement | null>(null)
const nameInputRef = ref<HTMLInputElement | null>(null)
const presetSelectRef = ref<HTMLSelectElement | null>(null)

async function openDialog(trigger: EventTarget | null) {
  triggerRef.value = trigger instanceof HTMLElement ? trigger : null
  formError.value = null
  dialogOpen.value = true
  await nextTick()
  ;(editing.value ? presetSelectRef.value : nameInputRef.value)?.focus()
}
function openCreate(trigger: EventTarget | null) {
  editing.value = false
  Object.assign(form, { name: '', preset: 'custom', endpoint: 'chat_completions', base_url: '', model: '', temperature: 0.3, api_key: '' })
  void openDialog(trigger)
}
function openEdit(p: AiProfile, trigger: EventTarget | null) {
  editing.value = true
  Object.assign(form, { name: p.name, preset: p.preset, endpoint: p.endpoint, base_url: p.base_url, model: p.model, temperature: p.temperature, api_key: '' })
  void openDialog(trigger)
}
function closeDialog() {
  dialogOpen.value = false
  triggerRef.value?.focus()  // 焦点归还触发器
}
function setPreset(v: AiProfile['preset']) {
  form.preset = v
  if (v !== 'custom') form.base_url = PRESETS[v]  // 自动回填；非 custom 时输入框只读
}
async function submit() {
  formError.value = null
  const payload: Record<string, unknown> = {
    preset: form.preset, endpoint: form.endpoint, base_url: form.base_url,
    model: form.model, temperature: form.temperature,
  }
  if (form.api_key) payload.api_key = form.api_key  // 编辑态空串 → 保留原密钥
  try {
    if (editing.value) await api.updateAiProfile(form.name, payload)
    else await api.createAiProfile({ ...payload, name: form.name })
    closeDialog()
    await load()
  } catch (e) { formError.value = (e as Error).message }
}
</script>

<template>
  <div class="p-6 space-y-5">
    <header>
      <h1 class="text-xl font-bold text-text tracking-tight">AI 设置</h1>
      <p class="text-xs text-text-3 mt-1">AI 生成配置 profiles — 密钥存 macOS 钥匙串，配置文件零密钥</p>
    </header>

    <!-- 分区 tab（与全局日期分段控件同一语汇） -->
    <div class="flex items-center rounded-lg border border-border p-0.5 gap-0.5 w-fit" role="tablist" aria-label="AI 设置分区">
      <button
        v-for="t in SECTIONS"
        :key="t[0]"
        role="tab"
        :aria-selected="section === t[0]"
        class="px-3 py-1.5 text-xs font-medium rounded-md transition-colors duration-150"
        :class="section === t[0] ? 'bg-accent-soft text-accent' : 'text-text-3 hover:text-text-2'"
        @click="section = t[0]"
      >{{ t[1] }}</button>
    </div>

    <!-- ═══ Profiles 配置 ═══ -->
    <div v-if="section === 'profiles'" class="bg-card border border-border rounded-xl p-4" role="tabpanel">
      <div class="flex items-center justify-between mb-3">
        <div class="text-[11px] font-semibold tracking-[0.14em] text-text-3 select-none">PROFILES</div>
        <button :class="btnCls" @click="openCreate($event.target)">＋ 新增</button>
      </div>

      <div v-if="pageError" class="text-xs text-down mb-2">{{ pageError }}</div>
      <div v-if="!profiles.length" class="text-sm text-text-3 py-3">
        暂无配置——新增 profile 或设置 COMMENTARY_BASE_URL / COMMENTARY_API_KEY / COMMENTARY_MODEL 环境变量
      </div>

      <div v-for="p in profiles" :key="p.name" class="py-3 border-b border-border last:border-0">
        <div class="flex items-center gap-2 text-sm">
          <span v-if="active === p.name" class="text-warn" aria-label="当前默认">★</span>
          <span class="font-medium text-text">{{ p.name }}</span>
          <span v-if="p.source === 'env'" class="text-[10px] text-text-3 border border-border rounded px-1.5 py-0.5"
            aria-label="来源：环境变量，只读">环境变量</span>
          <span class="flex-1"></span>
          <span v-if="p.has_key" class="text-xs text-up">✓ 密钥已存</span>
          <span v-else class="text-xs text-down">✗ 无密钥</span>
        </div>
        <div class="text-[11px] text-text-3 mt-0.5 tnum">{{ p.preset }} · {{ p.endpoint }} · {{ p.model }}</div>
        <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
          <button :class="btnCls" :disabled="testing === p.name" @click="runTest(p.name)">
            {{ testing === p.name ? '测试中…' : '测试' }}
          </button>
          <template v-if="p.source === 'user'">
            <button :class="btnCls" @click="openEdit(p, $event.target)">编辑</button>
            <template v-if="confirmName === p.name">
              <span class="text-xs text-warn">确认删除？</span>
              <button :class="btnCls" @click="remove(p.name)">确认</button>
              <button :class="btnCls" @click="confirmName = null">取消</button>
            </template>
            <button v-else :class="btnCls" @click="confirmName = p.name">删除</button>
          </template>
          <button v-if="active !== p.name" :class="btnCls" @click="setActive(p.name)">设为默认</button>
          <span role="status">
            <span v-if="testResults[p.name]?.ok" class="text-xs text-up tnum">✓ {{ testResults[p.name].latency_ms }}ms</span>
            <span v-else-if="testResults[p.name]" class="text-xs text-down" :title="testResults[p.name].error ?? ''">
              ✗ {{ testResults[p.name].error }}
            </span>
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ 提示词模板：主-从布局（左键列表 · 右编辑面板） ═══ -->
    <div v-else-if="section === 'templates'" class="bg-card border border-border rounded-xl overflow-hidden" role="tabpanel">
      <div class="flex items-center justify-between px-4 pt-4 pb-3 border-b border-border">
        <div class="text-[11px] font-semibold tracking-[0.14em] text-text-3 select-none">提示词模板</div>
        <div v-if="tplHash" class="text-[11px] text-text-4 tnum">当前 tpl {{ tplHash.slice(0, 8) }}</div>
      </div>
      <div class="grid grid-cols-[200px_1fr] min-h-[420px]">
        <!-- 左：模板键列表 -->
        <div class="border-r border-border py-2 bg-surface/50" role="tablist" aria-label="模板键" aria-orientation="vertical">
          <button
            v-for="k in TPL_ORDER" :key="k"
            role="tab"
            :aria-selected="tplSel === k"
            class="relative w-full text-left px-3.5 py-2 text-xs transition-colors duration-150 flex items-center gap-2"
            :class="tplSel === k ? 'bg-accent-soft text-text font-medium' : 'text-text-3 hover:bg-white/[0.04] hover:text-text-2'"
            @click="tplSel = k"
          >
            <span
              class="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-accent transition-opacity"
              :class="tplSel === k ? 'opacity-100' : 'opacity-0'"
              aria-hidden="true"
            />
            <span class="flex-1">{{ TPL_LABELS[k] }}</span>
            <span v-if="tplDraft[k]?.trim()" class="w-1.5 h-1.5 rounded-full bg-accent" title="已覆盖默认" />
          </button>
        </div>
        <!-- 右：当前模板编辑 -->
        <div class="p-4 flex flex-col">
          <div class="flex items-center gap-2 mb-2">
            <label :for="'tpl-' + tplSel" class="text-sm font-medium text-text">{{ TPL_LABELS[tplSel] }}</label>
            <span v-if="tplDraft[tplSel]?.trim()" class="text-[10px] text-accent border border-border rounded px-1.5 py-0.5">已覆盖</span>
            <span v-else class="text-[10px] text-text-4">使用默认</span>
            <span class="flex-1"></span>
            <button :class="btnCls" :disabled="!tplDraft[tplSel]" @click="tplDraft[tplSel] = ''">重置默认</button>
          </div>
          <textarea
            :id="'tpl-' + tplSel" v-model="tplDraft[tplSel]" rows="10"
            :placeholder="tplDefaults[tplSel]"
            class="flex-1 w-full bg-surface border border-border rounded-lg px-3 py-2.5 text-sm text-text leading-relaxed placeholder:text-text-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent resize-y font-mono"
          ></textarea>
          <div class="flex items-center gap-3 mt-3">
            <button
              class="px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
              :class="tplDirty ? 'bg-accent text-accent-ink hover:bg-accent-hi' : 'border border-border text-text-3'"
              :disabled="!tplDirty || tplSaving"
              @click="saveTpl"
            >{{ tplSaving ? '保存中…' : '保存全部' }}</button>
            <span v-if="tplDirty" class="text-[11px] text-warn">有未保存改动</span>
            <span v-if="tplMsg" role="status" :class="tplMsgOk ? 'text-xs text-up' : 'text-xs text-down'">{{ tplMsg }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 生成历史 ═══ -->
    <div v-else class="bg-card border border-border rounded-xl p-4" role="tabpanel">
      <div class="text-[11px] font-semibold tracking-[0.14em] text-text-3 select-none mb-3">生成历史</div>
      <div v-if="historyError" class="text-xs text-down mb-2">{{ historyError }}</div>
      <div v-else-if="!batches.length" class="text-sm text-text-3 py-3">暂无生成记录</div>
      <details
        v-for="b in batches"
        :key="b.generated_at"
        class="py-2 border-b border-border last:border-0"
        @toggle="toggleBatch(b, $event)"
      >
        <summary class="cursor-pointer text-sm text-text-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
          <span class="tnum">{{ b.generated_at }}</span><template v-if="b.model"> · {{ b.model }}</template><template v-if="b.profile"> · {{ b.profile }}</template><template v-if="b.template_hash"> · tpl {{ b.template_hash.slice(0, 8) }}</template> · {{ b.status }}
          <span v-if="b.stale" class="text-xs px-1.5 py-0.5 rounded bg-warn-soft text-warn">已过期</span>
        </summary>
        <div v-if="batchLoading[b.generated_at]" class="text-xs text-text-3 mt-2">加载中…</div>
        <div v-else-if="batchErrors[b.generated_at]" class="text-xs text-down mt-2">{{ batchErrors[b.generated_at] }}</div>
        <div v-else-if="batchDetails[b.generated_at]" class="mt-2 space-y-2 text-sm text-text-2">
          <div>
            <div class="text-xs text-text-3 mb-0.5">总体研判</div>
            <div class="whitespace-pre-line leading-relaxed">{{ batchDetails[b.generated_at].overall }}</div>
          </div>
          <div v-for="(t, sec) in batchDetails[b.generated_at].sections" :key="sec">
            <div class="text-xs text-text-3 mb-0.5">{{ TPL_LABELS[sec] ?? sec }}</div>
            <div class="whitespace-pre-line leading-relaxed">{{ t }}</div>
          </div>
        </div>
      </details>
    </div>

    <!-- 新增/编辑 dialog -->
    <div v-if="dialogOpen" class="fixed inset-0 z-[120] bg-black/60 flex items-center justify-center p-4" @click.self="closeDialog">
      <div
        role="dialog" aria-modal="true" :aria-label="editing ? '编辑 AI 配置' : '新增 AI 配置'" tabindex="-1"
        class="w-[480px] max-w-full max-h-[85vh] overflow-y-auto rounded-xl border border-border-hi bg-card shadow-xl p-5 outline-none"
        @keydown.esc="closeDialog"
      >
        <div class="space-y-3">
          <div>
            <label for="ai-name" class="block text-xs text-text-2 mb-1">名称</label>
            <input id="ai-name" ref="nameInputRef" v-model="form.name" type="text" :readonly="editing"
              :class="inputCls + (editing ? ' text-text-3' : '')" placeholder="字母/数字/下划线/连字符，≤40 字符">
          </div>
          <div>
            <label for="ai-preset" class="block text-xs text-text-2 mb-1">Provider</label>
            <select id="ai-preset" ref="presetSelectRef" :value="form.preset" :class="inputCls"
              @change="setPreset(($event.target as HTMLSelectElement).value as AiProfile['preset'])">
              <option v-for="(label, k) in PRESET_LABELS" :key="k" :value="k">{{ label }}</option>
            </select>
          </div>
          <div>
            <label for="ai-base-url" class="block text-xs text-text-2 mb-1">Base URL</label>
            <input id="ai-base-url" v-model="form.base_url" type="text" :readonly="form.preset !== 'custom'"
              :class="inputCls + (form.preset !== 'custom' ? ' text-text-3' : '')" placeholder="https://…">
          </div>
          <fieldset>
            <legend class="text-xs text-text-2 mb-1">端点方言</legend>
            <div class="flex items-center gap-4 text-xs text-text-2">
              <label class="flex items-center gap-1.5">
                <input id="ai-ep-chat" v-model="form.endpoint" type="radio" name="ai-endpoint" value="chat_completions"
                  class="focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                chat_completions（OpenAI 兼容）
              </label>
              <label class="flex items-center gap-1.5">
                <input id="ai-ep-resp" v-model="form.endpoint" type="radio" name="ai-endpoint" value="responses"
                  class="focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                responses（OpenAI Responses）
              </label>
            </div>
          </fieldset>
          <div>
            <label for="ai-model" class="block text-xs text-text-2 mb-1">模型</label>
            <input id="ai-model" v-model="form.model" type="text" :class="inputCls" placeholder="如 qwen-max / deepseek-chat / gpt-4o-mini">
          </div>
          <div>
            <label for="ai-temp" class="block text-xs text-text-2 mb-1">Temperature（0–2）</label>
            <input id="ai-temp" v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" :class="inputCls">
          </div>
          <div>
            <label for="ai-key" class="block text-xs text-text-2 mb-1">API Key{{ editing ? '' : '（可选）' }}</label>
            <input id="ai-key" v-model="form.api_key" type="password" autocomplete="off" :class="inputCls"
              :placeholder="editing ? '留空保持原密钥' : '写入 macOS 钥匙串'">
          </div>
          <div v-if="formError" class="text-xs text-down">{{ formError }}</div>
          <div class="flex justify-end gap-2 pt-1">
            <button :class="btnCls" @click="closeDialog">取消</button>
            <button :class="btnCls" @click="submit">{{ editing ? '保存' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
