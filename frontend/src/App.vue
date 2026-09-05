<template>
  <div class="dashboard">
    <header class="header">
      <div class="header-left">
        <h1>
          <span class="dot"></span>
          Network Monitor
        </h1>
        <div v-if="report" class="view-tabs" role="tablist">
          <button
            class="view-tab"
            :class="{ active: view === 'topo' }"
            @click="view = 'topo'"
          >系統図</button>
          <button
            class="view-tab"
            :class="{ active: view === 'detail' }"
            @click="view = 'detail'"
          >詳細一覧</button>
        </div>
      </div>
      <div class="header-meta">
        <span class="updated">
          {{ report ? `更新: ${report.collected_at}` : '読み込み中...' }}
        </span>
        <span class="countdown">次の更新まで {{ countdown }}s</span>

        <label
          class="header-toggle"
          :class="{ disabled: !webhookConfigured }"
          :title="notifyTitle"
        >
          <span class="toggle-icon">🔔</span>
          <input
            type="checkbox"
            :checked="notifyEnabled"
            :disabled="!webhookConfigured"
            @change="toggleNotify"
          />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
        </label>

        <label class="header-toggle" :title="avatarTitle">
          <span class="toggle-icon">🧍</span>
          <input type="checkbox" v-model="avatarVisible" />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
        </label>

        <button class="refresh-btn" @click="refresh" :disabled="loading">
          <span v-if="loading">...</span>
          <span v-else>↻ 更新</span>
        </button>
      </div>
    </header>

    <div v-if="error" class="state-message error">{{ error }}</div>
    <div v-else-if="!report" class="state-message">データを取得中...</div>

    <template v-else>
      <SummaryBar :tiles="tiles" :warnings="warnings" />

      <div v-show="view === 'topo'" class="topo-scale" ref="scaleWrap">
      <div class="topo" ref="topoEl">
        <!-- Router -->
        <div class="topo-center">
          <TopoBox
            variant="router"
            icon="router"
            :title="router.name"
            :subtitle="router.ip"
            :badges="[{ text: router.online ? 'ONLINE' : 'OFFLINE', tone: router.online ? 'green' : 'red' }]"
          />
        </div>
        <div class="conn-v"></div>

        <!-- Network segments -->
        <div class="topo-row">
          <TopoBox
            v-for="seg in segments"
            :key="seg.cidr"
            variant="segment"
            icon="network"
            :title="seg.cidr"
            :subtitle="seg.vlan ? `${seg.vlan} · ${seg.label}` : seg.label"
          />
        </div>
        <!-- Groups branch: Proxmox cluster + on-prem groups -->
        <div class="tree-row group-row">
          <div class="tree-node" v-for="grp in groups" :key="grp.name">
            <div class="group-col">
              <GroupHeader :icon="grp.icon" :title="grp.name" :count="grp.count" />

              <!-- Proxmox nodes, each with its guest branch -->
              <div class="tree-row" v-if="grp.type === 'proxmox'">
                <div class="tree-node" v-for="node in grp.nodes" :key="node.node">
                  <div class="node-col">
                    <NodeCard :node="node" @click="openDetail('node', node)" />
                    <!-- VM/LXC を1枚のパネルにまとめて表示 -->
                    <div class="tree-row" v-if="guestsOf(node).length">
                      <div class="tree-node">
                        <div class="guest-panel">
                          <GuestChip
                            v-for="g in guestsOf(node)"
                            :key="`${g.kind}-${g.data.vmid}`"
                            :guest="g.data"
                            :kind="g.kind"
                            @click="openDetail('guest', g.data, g.kind)"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- On-prem host cards -->
              <div class="tree-row" v-else-if="grp.type === 'onprem'">
                <div class="tree-node" v-for="h in grp.hosts" :key="h.ip">
                  <HostCard :host="h" @click="openDetail('host', h)" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>

      <!-- 詳細一覧ビュー: 種類別にカードを並べる -->
      <div v-show="view === 'detail'" class="detail-view">
        <section v-for="grp in detailGroups" :key="grp.key" class="detail-section">
          <div class="detail-section-head">
            <Icon :name="grp.icon" :size="16" class="ds-ico" />
            <span class="ds-title">{{ grp.title }}</span>
            <span class="ds-count">{{ grp.items.length }}</span>
          </div>
          <div class="detail-grid-view">
            <DetailCard
              v-for="d in grp.items"
              :key="d.key"
              :type="d.type"
              :data="d.data"
              :kind="d.kind"
            />
          </div>
        </section>
      </div>
    </template>

    <DetailModal
      v-if="selected"
      :type="selected.type"
      :data="selected.data"
      :kind="selected.kind"
      @close="selected = null"
    />

    <!-- VRM アバター（系統図の前面に表示） -->
    <Avatar
      v-show="avatarVisible"
      :visible="avatarVisible"
      :message="avatarBubble"
      :alert="hasAnomaly"
      :thinking="avatarThinking"
      :emotion="avatarEmotion"
      :motion="avatarMotion"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import NodeCard from './components/NodeCard.vue'
import GuestChip from './components/GuestChip.vue'
import HostCard from './components/HostCard.vue'
import TopoBox from './components/TopoBox.vue'
import GroupHeader from './components/GroupHeader.vue'
import Icon from './components/Icon.vue'
import DetailModal from './components/DetailModal.vue'
import DetailCard from './components/DetailCard.vue'
import Avatar from './components/Avatar.vue'
import SummaryBar from './components/SummaryBar.vue'
import { topology } from './topology'

// 使用率の警告しきい値（%）
const CPU_WARN = 85
const MEM_WARN = 85

// 監視データの自動更新間隔（秒）
const POLL_INTERVAL_SEC = 10

// アバターのセリフ(Ollama)を取り直す間隔と、吹き出しの表示時間
const AVATAR_SAY_INTERVAL = 45_000 // 45秒ごとに新しいセリフを生成
const AVATAR_SAY_DURATION = 30_000 // 生成後に吹き出しを出しておく時間
// 応答として受け付けるセリフの上限文字数（api/avatar.py の MAX_LEN と合わせる）と、
// 既知の表情・モーション名
const AVATAR_SAY_MAX_LEN = 52
const AVATAR_EMOTIONS = ['neutral', 'happy', 'sad', 'worried', 'surprised', 'angry']
const AVATAR_MOTIONS = ['wave', 'nod', 'tilt', 'cheer', 'surprised', 'think', 'shrug', 'panic', 'bow', 'sway']

const report = ref(null)
const loading = ref(false)
const error = ref(null)
const countdown = ref(POLL_INTERVAL_SEC)
const notifyEnabled = ref(false)
const webhookConfigured = ref(false)

// 表示ビュー: 'topo'（系統図） / 'detail'（詳細一覧）
const view = ref('topo')

// アバターを表示するか（ヘッダーのスイッチで切替、ブラウザに保存）
const AVATAR_VISIBLE_KEY = 'avatarVisible'
const avatarVisible = ref(loadAvatarVisible())

function loadAvatarVisible() {
  try {
    return localStorage.getItem(AVATAR_VISIBLE_KEY) !== '0'
  } catch (_) {
    return true // プライベートモード等で読めなくても表示する
  }
}

// アバターのセリフ(Ollama生成)。表情・モーションはバックエンドがセリフから判定して返す
const chatMessage = ref(null)
const chatEmotion = ref('happy')
const chatMotion = ref('sway')
// セリフの定期取得を行うか。Ollama 未設定でも定型セリフが返るので通常は true
const avatarSayEnabled = ref(false)
const ollamaConfigured = ref(false)
// Ollama に問い合わせ中か（true の間は「・・・」の吹き出しを出す）
const avatarThinking = ref(false)

// クリックした対象の詳細モーダル
const selected = ref(null)
function openDetail(type, data, kind) {
  selected.value = { type, data, kind }
}

const router = topology.router
const segments = topology.segments
const cluster = topology.cluster

const nodes = computed(() => report.value?.nodes || [])

// Proxmox クラスタ + オンプレグループを系統図の「グループ列」として並べる
const groups = computed(() => {
  const list = [{
    type: 'proxmox',
    name: cluster.name,
    icon: 'cluster',
    count: nodes.value.length,
    nodes: nodes.value,
  }]
  for (const grp of (report.value?.onprem_groups || [])) {
    list.push({
      type: 'onprem',
      name: grp.name,
      icon: 'monitor',
      count: grp.hosts.length,
      hosts: grp.hosts,
    })
  }
  return list
})

const onpremHosts = computed(() =>
  (report.value?.onprem_groups || []).flatMap(g => g.hosts || [])
)

// VM/LXC が「一度でも running を観測できたか」（"node/vmid" -> true）。
// 「常時オフのVM」を通知対象から外すためのベースライン。
// 起動→停止も拾えるよう、初回観測時だけでなく running を見るたびに記録する。
// 警告表示が再計算されるよう ref で持つ（プレーンなオブジェクトだと computed が追従しない）。
const guestSeenRunning = ref({})

function guestKey(node, guest) {
  return `${node}/${guest.vmid}`
}

function recordGuestBaseline(rep) {
  const seen = guestSeenRunning.value
  let changed = false
  for (const n of (rep?.nodes || [])) {
    if (n.online === false) continue
    for (const g of [...(n.vms || []), ...(n.lxc || [])]) {
      const key = guestKey(n.node, g)
      if (g.status === 'running' && !seen[key]) {
        seen[key] = true
        changed = true
      }
    }
  }
  if (changed) guestSeenRunning.value = { ...seen }
}

// 停止した VM/LXC（稼働ノード上で、以前は running だったものだけ）
const downGuests = computed(() => {
  const list = []
  for (const n of nodes.value) {
    if (n.online === false) continue
    for (const g of [...(n.vms || []), ...(n.lxc || [])]) {
      if (g.status !== 'running' && guestSeenRunning.value[guestKey(n.node, g)]) {
        list.push({ node: n.node, name: g.name, vmid: g.vmid })
      }
    }
  }
  return list
})

// --- 画面上部の集計タイル（稼働/総数 の分数表示・系統図と同じアイコン） ---
const tiles = computed(() => {
  const ns = nodes.value
  const hs = onpremHosts.value
  const nodeOnline = ns.filter(n => n.online !== false).length
  const hostOnline = hs.filter(h => h.online !== false).length
  const totalMon = ns.length + hs.length
  const online = nodeOnline + hostOnline
  const offline = totalMon - online
  const countGuests = pred =>
    ns.reduce((s, n) => s
      + (n.vms || []).filter(pred).length
      + (n.lxc || []).filter(pred).length, 0)
  const guestsTotal = countGuests(() => true)
  const guestsRunning = countGuests(g => g.status === 'running')
  // 稼働していたのに停止した VM/LXC（常時オフは除外）
  const guestsDown = downGuests.value.length
  const network = topology.router ? 1 : 0
  return [
    { label: '起動ノード', icon: 'server', value: online, total: totalMon, status: offline > 0 ? 'bad' : 'ok' },
    { label: 'ダウン', icon: 'server', value: offline, total: totalMon, status: offline > 0 ? 'bad' : 'ok' },
    { label: 'Proxmox', icon: 'cluster', value: nodeOnline, total: ns.length, status: nodeOnline < ns.length ? 'bad' : 'ok' },
    { label: 'オンプレ', icon: 'monitor', value: hostOnline, total: hs.length, status: hostOnline < hs.length ? 'bad' : 'ok' },
    { label: 'ネットワーク機器', icon: 'router', value: network, total: network, status: 'ok' },
    { label: 'VM / LXC', icon: 'vm', value: guestsRunning, total: guestsTotal, status: guestsDown > 0 ? 'bad' : 'ok' },
  ]
})

// --- 警告メッセージ生成 ---
// ノード / オンプレサーバー: ダウン + CPU/MEM 高負荷
// Proxmox の VM/LXC: 高負荷は無視し、停止（ダウン）のみ通知
const warnings = computed(() => {
  const w = []
  if (!report.value) return w

  // 重大: ダウン
  for (const n of nodes.value) {
    if (n.online === false) w.push({ level: 'critical', text: `Proxmoxノード「${n.node}」がダウンしています` })
  }
  for (const h of onpremHosts.value) {
    if (h.online === false) w.push({ level: 'critical', text: `オンプレサーバー「${h.name}」がダウンしています` })
  }

  // 警告: ノード / オンプレの高負荷（稼働中のみ）
  for (const n of nodes.value) {
    if (n.online === false) continue
    if (n.cpu?.usage_pct >= CPU_WARN) w.push({ level: 'warn', text: `Proxmoxノード「${n.node}」CPU使用率が高い (${n.cpu.usage_pct}%)` })
    if (n.memory?.usage_pct >= MEM_WARN) w.push({ level: 'warn', text: `Proxmoxノード「${n.node}」メモリ使用率が高い (${n.memory.usage_pct}%)` })
  }
  for (const h of onpremHosts.value) {
    if (h.online === false) continue
    if (h.cpu?.usage_pct >= CPU_WARN) w.push({ level: 'warn', text: `オンプレ「${h.name}」CPU使用率が高い (${h.cpu.usage_pct}%)` })
    if (h.memory?.usage_pct >= MEM_WARN) w.push({ level: 'warn', text: `オンプレ「${h.name}」メモリ使用率が高い (${h.memory.usage_pct}%)` })
  }

  // 重大: VM/LXC のダウン（稼働ノード上のみ。高負荷は通知しない）
  // 「常時オフのVM」を拾わないよう、一度でも running を観測したものが
  // その後停止した場合だけ通知する（ベースライン比較）。
  for (const g of downGuests.value) {
    w.push({ level: 'critical', text: `VM/LXC「${g.name}」(VMID:${g.vmid} / ${g.node}) が停止しました` })
  }

  return w
})

// --- 異常検知（アバター用: ダウンしたノード / オンプレサーバー / VM・LXC） ---
const offlineNames = computed(() => {
  const names = []
  for (const n of nodes.value) if (n.online === false) names.push(n.node)
  for (const h of onpremHosts.value) if (h.online === false) names.push(h.name)
  return names
})

// アバターが反応する対象（ホストのダウンに加え、停止した VM/LXC も含む）
const alertNames = computed(() => [
  ...offlineNames.value,
  ...downGuests.value.map(g => g.name),
])

const hasAnomaly = computed(() => alertNames.value.length > 0)

// 詳細一覧ビュー: 種類別（Proxmox / オンプレサーバー / VM・LXC）にカードを並べる
const detailGroups = computed(() => {
  const proxmox = nodes.value.map(n => ({ key: `node-${n.node}`, type: 'node', data: n }))

  const onprem = onpremHosts.value.map(h => ({ key: `host-${h.ip}`, type: 'host', data: h }))

  const guests = []
  for (const n of nodes.value) {
    for (const g of guestsOf(n)) {
      guests.push({ key: `guest-${g.kind}-${g.data.vmid}`, type: 'guest', data: g.data, kind: g.kind })
    }
  }

  return [
    { key: 'proxmox', title: 'Proxmox', icon: 'cluster', items: proxmox },
    { key: 'onprem', title: 'オンプレサーバー', icon: 'monitor', items: onprem },
    { key: 'guests', title: 'VM / LXC', icon: 'vm', items: guests },
  ].filter(g => g.items.length)
})

// アバターの吹き出しメッセージ（ダウン発生時のみ表示）
const avatarMessage = computed(() => {
  if (!report.value) return null
  if (!hasAnomaly.value) return null
  const list = alertNames.value
  const who = list.length <= 2 ? list.join('・') : `${list.slice(0, 2).join('・')} 他${list.length - 2}件`
  const what = offlineNames.value.length ? 'サーバー落ちました！' : 'VMが止まりました！'
  return `${what}\n(${who})`
})

// 実際に吹き出しへ出す内容: 異常時はアラートを最優先、平常時は Ollama のセリフ
const avatarBubble = computed(() =>
  hasAnomaly.value ? avatarMessage.value : chatMessage.value
)

// 吹き出しの内容に合わせた表情とモーション（異常時は心配顔＋あわてる動き）
const avatarEmotion = computed(() => (hasAnomaly.value ? 'worried' : chatEmotion.value))
const avatarMotion = computed(() => (hasAnomaly.value ? 'panic' : chatMotion.value))

// Ollama へ渡す現在の監視状況（セリフの素材）
function avatarContext() {
  const parts = tiles.value.map(t => `${t.label} ${t.value}/${t.total}`)
  parts.push(warnings.value.length
    ? '警告: ' + warnings.value.map(w => w.text).join(' / ')
    : '異常なし')
  return parts.join('、')
}

let pollTimer = null
let countdownTimer = null
let sayTimer = null
let sayHideTimer = null

// Ollama にセリフを生成させ、一定時間だけ吹き出しに表示
async function fetchAvatarSay() {
  // 非表示中や異常時（アラートを出している）は生成しない。多重リクエストも防ぐ。
  if (!avatarVisible.value || !avatarSayEnabled.value) return
  if (hasAnomaly.value || avatarThinking.value) return
  // 生成中は前のセリフを消して「・・・」の吹き出しに切り替える
  clearTimeout(sayHideTimer)
  chatMessage.value = null
  avatarThinking.value = true
  try {
    const res = await fetch('/api/avatar/say', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: avatarContext() }),
    })
    if (!res.ok) return
    const data = await res.json()
    // バックエンドで検査済みだが、想定外の応答を吹き出しに出さないよう念のため確認する
    const text = typeof data?.message === 'string' ? data.message.trim() : ''
    if (!text || text.length > AVATAR_SAY_MAX_LEN) return
    chatEmotion.value = AVATAR_EMOTIONS.includes(data.emotion) ? data.emotion : 'happy'
    chatMotion.value = AVATAR_MOTIONS.includes(data.motion) ? data.motion : 'sway'
    chatMessage.value = text
    sayHideTimer = setTimeout(() => { chatMessage.value = null }, AVATAR_SAY_DURATION)
  } catch (_) {
  } finally {
    avatarThinking.value = false
  }
}

// セリフ機能の状態を確認して定期生成を開始する。
// Ollama 未設定でもバックエンドが定型セリフを返すので、基本は常に開始する。
async function initAvatarSay() {
  try {
    const res = await fetch('/api/avatar/status')
    if (res.ok) {
      const st = await res.json()
      ollamaConfigured.value = !!st.configured
      avatarSayEnabled.value = !!(st.always_talks || st.configured)
    }
  } catch (_) {}
  if (!avatarSayEnabled.value) return
  sayTimer = setInterval(fetchAvatarSay, AVATAR_SAY_INTERVAL)
  setTimeout(fetchAvatarSay, 5000) // 初回は起動直後に一度
}

// --- ウィンドウ幅に合わせて系統図全体を自動スケール（横スクロール回避） ---
const scaleWrap = ref(null)
const topoEl = ref(null)

function fitScale() {
  const wrap = scaleWrap.value
  const topo = topoEl.value
  if (!wrap || !topo) return
  topo.style.transform = 'none'
  const avail = wrap.clientWidth
  const natural = topo.offsetWidth // transform は offsetWidth に影響しない
  const scale = natural > avail ? avail / natural : 1
  topo.style.transform = scale < 1 ? `scale(${scale})` : 'none'
  // 縮小後の高さに合わせてラッパー高さを詰める（余白を残さない）
  wrap.style.height = topo.offsetHeight * scale + 'px'
}

const avatarTitle = computed(() =>
  avatarVisible.value ? 'アバター: 表示中 (クリックで非表示)' : 'アバター: 非表示 (クリックで表示)'
)

const notifyTitle = computed(() => {
  if (!webhookConfigured.value) return 'GOOGLE_CHAT_WEBHOOK_URL が未設定です'
  return notifyEnabled.value ? '通知: 有効 (クリックで無効化)' : '通知: 無効 (クリックで有効化)'
})

function guestsOf(node) {
  const vms = (node.vms || []).map(d => ({ kind: 'vm', data: d }))
  const lxc = (node.lxc || []).map(d => ({ kind: 'lxc', data: d }))
  return [...vms, ...lxc].sort((a, b) => {
    const ar = a.data.status === 'running'
    const br = b.data.status === 'running'
    if (ar !== br) return ar ? -1 : 1
    return a.data.name.localeCompare(b.data.name)
  })
}

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch('/api/latest')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    report.value = await res.json()
    recordGuestBaseline(report.value)
    countdown.value = POLL_INTERVAL_SEC
  } catch (e) {
    error.value = `取得失敗: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function fetchNotifyStatus() {
  try {
    const res = await fetch('/api/notify/status')
    if (!res.ok) return
    const data = await res.json()
    notifyEnabled.value = data.enabled
    webhookConfigured.value = data.webhook_configured
  } catch (_) {}
}

async function toggleNotify() {
  try {
    const res = await fetch('/api/notify/toggle', { method: 'POST' })
    if (!res.ok) return
    const data = await res.json()
    notifyEnabled.value = data.enabled
  } catch (_) {}
}

// アバターの表示状態を保存。再表示したら新しいセリフを取りにいく
watch(avatarVisible, v => {
  try { localStorage.setItem(AVATAR_VISIBLE_KEY, v ? '1' : '0') } catch (_) {}
  if (!v) {
    clearTimeout(sayHideTimer)
    chatMessage.value = null
  } else if (avatarSayEnabled.value) {
    setTimeout(fetchAvatarSay, 1500)
  }
})

// レポート更新でカード数が変わったら再フィット
watch(report, () => nextTick(fitScale))
// 系統図ビューに戻ったら再フィット（非表示中は幅が測れないため）
watch(view, v => { if (v === 'topo') nextTick(fitScale) })

onMounted(() => {
  refresh()
  fetchNotifyStatus()
  initAvatarSay()
  pollTimer = setInterval(refresh, POLL_INTERVAL_SEC * 1_000)
  countdownTimer = setInterval(() => {
    if (countdown.value > 0) countdown.value--
  }, 1_000)

  window.addEventListener('resize', fitScale)
  nextTick(fitScale)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
  clearInterval(sayTimer)
  clearTimeout(sayHideTimer)
  window.removeEventListener('resize', fitScale)
})
</script>

<style scoped>
/* ヘッダー左側: タイトル ＋ 表示切替タブ */
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.view-tabs {
  display: flex;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px;
  gap: 3px;
}
.view-tab {
  padding: 6px 14px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 700;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}
.view-tab:hover { color: var(--text); }
.view-tab.active { background: var(--accent); color: #fff; }

/* 詳細一覧ビュー: 種類別セクション */
.detail-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 24px;
}

.detail-section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px 10px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 14px;
}
.ds-ico { color: var(--accent); flex-shrink: 0; }
.ds-title { font-size: 0.95rem; font-weight: 700; color: var(--text); }
.ds-count {
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--surface-2);
  border-radius: 20px;
  padding: 1px 9px;
}

/* 詳細一覧ビュー: 詳細カードをグリッドで並べる */
.detail-grid-view {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  align-items: start;
}

/* Auto-scale wrapper: fits the whole tree to the window width (no h-scroll) */
.topo-scale {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow: hidden;
}

.topo {
  width: fit-content;
  transform-origin: top center;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 24px 24px;
}

/* Centered spine element */
.topo-center {
  display: flex;
  justify-content: center;
}

/* Row of sibling boxes (segments) */
.topo-row {
  display: flex;
  justify-content: center;
  gap: 28px;
}

/* Vertical connector on the spine */
.conn-v {
  width: 1px;
  height: 22px;
  background: var(--border);
  margin: 0 auto;
}

/* ---- Group branch (segment -> cluster / on-prem groups) ---- */
.group-row {
  align-items: flex-start;
}

/* wider spacing between top-level groups */
.group-row > .tree-node {
  padding-left: 28px;
  padding-right: 28px;
}

.group-col {
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ---- Tree connectors (one parent -> a row of children) ----
   The horizontal bus is drawn as two half-lines that meet at each child's
   centre, so it connects sibling centres correctly even when the columns
   have very different widths. Spacing between siblings comes from the
   child padding (not flex-gap) so the bus has no breaks. */
.tree-row {
  display: flex;
  justify-content: center;
  padding-top: 20px;
  position: relative;
}

/* vertical drop from the parent down to the bus */
.tree-row::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  width: 0;
  height: 20px;
  border-left: 1px solid var(--border);
}

.tree-node {
  position: relative;
  padding: 20px 14px 0;
}

/* two horizontal half-lines forming the bus */
.tree-node::before,
.tree-node::after {
  content: '';
  position: absolute;
  top: 0;
  right: 50%;
  width: 50%;
  height: 20px;
  border-top: 1px solid var(--border);
}

/* the right half also carries the vertical stub down to the child */
.tree-node::after {
  right: auto;
  left: 50%;
  border-left: 1px solid var(--border);
}

/* trim the bus outside the first / last child */
.tree-node:first-child::before { border-top-color: transparent; }
.tree-node:last-child::after { border-top-color: transparent; }

/* single child: a straight vertical line, no horizontal bus */
.tree-node:only-child::before { display: none; }
.tree-node:only-child::after { border-top: 0; }

/* ---- Node column: node card + its consolidated guest panel ---- */
.node-col {
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* VM/LXC を1枚にまとめたコンパクトなパネル（ノードと同じ幅） */
.guest-panel {
  width: 190px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
</style>
