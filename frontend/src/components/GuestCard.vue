<template>
  <div class="guest-card" :class="{ stopped: guest.status !== 'running' }">
    <div class="guest-header">
      <div class="guest-title">
        <Icon :name="kind === 'lxc' ? 'container' : 'vm'" :size="14" class="guest-icon" />
        <span class="guest-name">{{ guest.name }}</span>
      </div>
      <span class="status-dot" :class="running ? 'online' : 'offline'"></span>
    </div>

    <span class="badge" :class="running ? 'badge-green' : 'badge-dim'">
      {{ running ? 'RUNNING' : 'STOPPED' }}
    </span>

    <div class="metrics" v-if="running">
      <UsageBar
        label="CPU"
        :pct="guest.cpu_usage_pct"
        :display-value="`${guest.cpu_usage_pct}%`"
      />
      <UsageBar
        label="MEM"
        :pct="memPct"
        :display-value="`${guest.memory.used_gb} / ${guest.memory.max_gb} GB`"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import UsageBar from './UsageBar.vue'
import Icon from './Icon.vue'

const props = defineProps({
  guest: Object,
  kind: String, // 'vm' | 'lxc'
})

const running = computed(() => props.guest.status === 'running')

const memPct = computed(() => {
  const max = props.guest.memory?.max_gb || 0
  const used = props.guest.memory?.used_gb || 0
  return max > 0 ? Math.round((used / max) * 1000) / 10 : 0
})
</script>

<style scoped>
.guest-card {
  width: 190px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.guest-card.stopped { opacity: 0.6; }

.guest-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.guest-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.guest-icon { color: var(--text-muted); }

.guest-name {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.online { background: var(--green); box-shadow: 0 0 5px var(--green); }
.status-dot.offline { background: var(--text-muted); }

.badge {
  align-self: flex-start;
  font-size: 0.58rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 20px;
  letter-spacing: 0.05em;
}

.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-dim   { background: var(--surface-2); color: var(--text-muted); }

.metrics { display: flex; flex-direction: column; gap: 6px; }
</style>
