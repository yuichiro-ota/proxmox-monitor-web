<template>
  <div class="dashboard">
    <header class="header">
      <h1>
        <span class="dot"></span>
        Proxmox Monitor
      </h1>
      <div class="header-meta">
        <span class="updated">
          {{ report ? `更新: ${report.collected_at}` : '読み込み中...' }}
        </span>
        <span class="countdown">次の更新まで {{ countdown }}s</span>

        <label
          class="notify-toggle"
          :class="{ 'no-webhook': !webhookConfigured }"
          :title="notifyTitle"
        >
          <span class="notify-icon">🔔</span>
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

        <button class="refresh-btn" @click="refresh" :disabled="loading">
          <span v-if="loading">...</span>
          <span v-else>↻ 更新</span>
        </button>
      </div>
    </header>

    <div v-if="error" class="state-message error">{{ error }}</div>
    <div v-else-if="!report" class="state-message">データを取得中...</div>

    <div v-else class="topo-scale" ref="scaleWrap">
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
                    <NodeCard :node="node" />
                    <!-- VM/LXC を1枚のパネルにまとめて表示 -->
                    <div class="tree-row" v-if="guestsOf(node).length">
                      <div class="tree-node">
                        <div class="guest-panel">
                          <GuestChip
                            v-for="g in guestsOf(node)"
                            :key="`${g.kind}-${g.data.vmid}`"
                            :guest="g.data"
                            :kind="g.kind"
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
                  <HostCard :host="h" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import NodeCard from './components/NodeCard.vue'
import GuestChip from './components/GuestChip.vue'
import HostCard from './components/HostCard.vue'
import TopoBox from './components/TopoBox.vue'
import GroupHeader from './components/GroupHeader.vue'
import { topology } from './topology'

const report = ref(null)
const loading = ref(false)
const error = ref(null)
const countdown = ref(60)
const notifyEnabled = ref(false)
const webhookConfigured = ref(false)

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

let pollTimer = null
let countdownTimer = null

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
    countdown.value = 60
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

// レポート更新でカード数が変わったら再フィット
watch(report, () => nextTick(fitScale))

onMounted(() => {
  refresh()
  fetchNotifyStatus()
  pollTimer = setInterval(refresh, 60_000)
  countdownTimer = setInterval(() => {
    if (countdown.value > 0) countdown.value--
  }, 1_000)

  window.addEventListener('resize', fitScale)
  nextTick(fitScale)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
  window.removeEventListener('resize', fitScale)
})
</script>

<style scoped>
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
