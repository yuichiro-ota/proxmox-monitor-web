<template>
  <div class="node-card" :class="{ offline: !node.online }">
    <!-- Node header -->
    <div class="node-header">
      <div class="node-title">
        <span class="status-dot" :class="node.online ? 'online' : 'offline'"></span>
        <span class="node-name">{{ node.node }}</span>
      </div>
      <div class="node-badges">
        <span class="badge" :class="node.online ? 'badge-green' : 'badge-red'">
          {{ node.online ? 'ONLINE' : 'OFFLINE' }}
        </span>
        <span class="badge badge-dim">{{ node.uptime_hours }}h</span>
      </div>
    </div>

    <!-- Metrics -->
    <div class="metrics" v-if="node.online">
      <UsageBar
        label="CPU"
        :pct="node.cpu.usage_pct"
        :display-value="`${node.cpu.usage_pct}% / ${node.cpu.cores}core`"
      />
      <UsageBar
        label="MEM"
        :pct="node.memory.usage_pct"
        :display-value="`${node.memory.used_gb} / ${node.memory.total_gb} GB`"
      />
      <UsageBar
        label="rootfs"
        :pct="node.rootfs.usage_pct"
        :display-value="`${node.rootfs.used_gb} / ${node.rootfs.total_gb} GB`"
      />
    </div>

    <!-- VMs -->
    <section v-if="guests.length" class="section">
      <div class="section-title">VM / LXC</div>
      <div class="guest-list">
        <div
          v-for="g in guests"
          :key="g.vmid"
          class="guest-row"
        >
          <span class="guest-status" :class="g.status === 'running' ? 'running' : 'stopped'">
            {{ g.status === 'running' ? '▶' : '■' }}
          </span>
          <span class="guest-name">{{ g.name }}</span>
          <span class="guest-meta">
            <span v-if="g.status === 'running'" class="guest-stat">
              CPU {{ g.cpu_usage_pct }}%
            </span>
            <span v-if="g.status === 'running'" class="guest-stat">
              {{ g.memory.used_gb }}/{{ g.memory.max_gb }}GB
            </span>
            <span v-if="g.status !== 'running'" class="guest-stat stopped-label">stopped</span>
          </span>
        </div>
      </div>
    </section>

    <!-- Storage -->
    <section v-if="node.storage && node.storage.length" class="section">
      <div class="section-title">Storage</div>
      <div class="storage-list">
        <div
          v-for="s in activeStorage"
          :key="s.storage"
          class="storage-row"
        >
          <div class="storage-name-row">
            <span class="storage-name">{{ s.storage }}</span>
            <span class="storage-type">{{ s.type }}</span>
            <span class="storage-pct" :style="{ color: storageColor(s.usage_pct) }">
              {{ s.usage_pct }}%
            </span>
          </div>
          <div class="storage-bar-track">
            <div
              class="storage-bar-fill"
              :style="{ width: `${s.usage_pct}%`, background: storageColor(s.usage_pct) }"
            ></div>
          </div>
          <div class="storage-detail">{{ s.used_gb }} / {{ s.total_gb }} GB</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import UsageBar from './UsageBar.vue'

const props = defineProps({
  node: Object,
})

const guests = computed(() => [
  ...(props.node.vms || []),
  ...(props.node.lxc || []),
].sort((a, b) => {
  if (a.status === b.status) return a.name.localeCompare(b.name)
  return a.status === 'running' ? -1 : 1
}))

const activeStorage = computed(() =>
  (props.node.storage || []).filter(s => s.active && s.total_gb > 0)
)

function storageColor(pct) {
  if (pct >= 80) return 'var(--red)'
  if (pct >= 60) return 'var(--yellow)'
  return 'var(--green)'
}
</script>

<style scoped>
.node-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: border-color 0.2s;
}

.node-card:hover { border-color: var(--accent); }
.node-card.offline { opacity: 0.6; }

/* Node header */
.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.node-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.online { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-dot.offline { background: var(--red); }

.node-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text);
}

.node-badges { display: flex; gap: 6px; align-items: center; }

.badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  letter-spacing: 0.05em;
}

.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red   { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-dim   { background: var(--surface-2); color: var(--text-muted); }

/* Metrics */
.metrics { display: flex; flex-direction: column; gap: 10px; }

/* Sections */
.section { display: flex; flex-direction: column; gap: 8px; }

.section-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

/* Guest list */
.guest-list { display: flex; flex-direction: column; gap: 4px; }

.guest-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  padding: 3px 0;
}

.guest-status {
  font-size: 0.65rem;
  flex-shrink: 0;
  width: 12px;
}

.guest-status.running { color: var(--green); }
.guest-status.stopped { color: var(--text-muted); }

.guest-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guest-meta {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.guest-stat {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  font-size: 0.78rem;
}

.stopped-label { color: var(--text-muted); font-style: italic; }

/* Storage */
.storage-list { display: flex; flex-direction: column; gap: 8px; }

.storage-row { display: flex; flex-direction: column; gap: 3px; }

.storage-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
}

.storage-name { font-weight: 500; flex: 1; }

.storage-type {
  font-size: 0.7rem;
  color: var(--text-muted);
  background: var(--surface-2);
  padding: 1px 6px;
  border-radius: 4px;
}

.storage-pct { font-variant-numeric: tabular-nums; font-weight: 600; font-size: 0.8rem; }

.storage-bar-track {
  height: 4px;
  background: var(--surface-2);
  border-radius: 2px;
  overflow: hidden;
}

.storage-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
  min-width: 2px;
}

.storage-detail {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
