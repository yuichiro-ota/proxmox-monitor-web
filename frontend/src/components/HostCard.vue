<template>
  <div class="host-card" :class="{ offline: !host.online }">
    <div class="host-header">
      <div class="host-title">
        <Icon name="monitor" :size="15" class="host-icon" />
        <span class="host-name">{{ host.name }}</span>
      </div>
      <span class="status-dot" :class="host.online ? 'online' : 'offline'"></span>
    </div>

    <div class="host-sub">{{ host.hostname }} · {{ host.ip }}</div>

    <div class="host-badges">
      <span class="badge" :class="host.online ? 'badge-green' : 'badge-red'">
        {{ host.online ? 'ONLINE' : 'OFFLINE' }}
      </span>
      <span class="badge badge-dim">{{ osLabel }}</span>
      <span v-if="host.online && host.uptime_hours != null" class="badge badge-dim">
        {{ host.uptime_hours }}h
      </span>
    </div>

    <div class="metrics" v-if="host.online">
      <UsageBar
        label="CPU"
        :pct="host.cpu.usage_pct"
        :display-value="`${host.cpu.usage_pct}% / ${host.cpu.cores}core`"
      />
      <UsageBar
        label="MEM"
        :pct="host.memory.usage_pct"
        :display-value="`${host.memory.used_gb} / ${host.memory.total_gb} GB`"
      />
      <UsageBar
        v-if="host.disk"
        label="DISK"
        :pct="host.disk.usage_pct"
        :display-value="`${host.disk.used_gb} / ${host.disk.total_gb} GB`"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import UsageBar from './UsageBar.vue'
import Icon from './Icon.vue'

const props = defineProps({
  host: Object,
})

const osLabel = computed(() => {
  if (props.host.os === 'windows') return 'Windows'
  if (props.host.os === 'linux') return 'Linux'
  return props.host.os || '—'
})
</script>

<style scoped>
.host-card {
  width: 190px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.host-card:hover { border-color: var(--accent); }
.host-card.offline { opacity: 0.55; }

.host-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.host-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.host-icon { color: var(--text-muted); }

.host-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.host-sub {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.online { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-dot.offline { background: var(--red); }

.host-badges { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }

.badge {
  font-size: 0.6rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 20px;
  letter-spacing: 0.05em;
}

.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red   { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-dim   { background: var(--surface-2); color: var(--text-muted); }

.metrics { display: flex; flex-direction: column; gap: 7px; }
</style>
