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
import { ref, onMounted, onUnmounted } from 'vue'
import NodeCard from './components/NodeCard.vue'

const report = ref(null)
const loading = ref(false)
const error = ref(null)
const countdown = ref(10)

let pollTimer = null
let countdownTimer = null

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch('/api/latest')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    report.value = await res.json()
    countdown.value = 10
  } catch (e) {
    error.value = `取得失敗: ${e.message}`
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  pollTimer = setInterval(refresh, 10_000)
  countdownTimer = setInterval(() => {
    if (countdown.value > 0) countdown.value--
  }, 1_000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
})
</script>
