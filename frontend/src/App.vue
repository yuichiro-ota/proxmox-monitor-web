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
    <div v-else class="nodes-grid">
      <NodeCard
        v-for="node in report.nodes"
        :key="node.node"
        :node="node"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import NodeCard from './components/NodeCard.vue'

const report = ref(null)
const loading = ref(false)
const error = ref(null)
const countdown = ref(60)
const notifyEnabled = ref(false)
const webhookConfigured = ref(false)

let pollTimer = null
let countdownTimer = null

const notifyTitle = computed(() => {
  if (!webhookConfigured.value) return 'GOOGLE_CHAT_WEBHOOK_URL が未設定です'
  return notifyEnabled.value ? '通知: 有効 (クリックで無効化)' : '通知: 無効 (クリックで有効化)'
})

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

onMounted(() => {
  refresh()
  fetchNotifyStatus()
  pollTimer = setInterval(refresh, 60_000)
  countdownTimer = setInterval(() => {
    if (countdown.value > 0) countdown.value--
  }, 1_000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
})
</script>
