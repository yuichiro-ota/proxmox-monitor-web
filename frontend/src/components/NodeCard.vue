<template>
  <div class="node-card" :class="{ offline: !node.online }">
    <!-- Node header -->
    <div class="node-header">
      <div class="node-title">
        <Icon name="server" :size="15" class="node-icon" />
        <span class="node-name">{{ node.node }}</span>
      </div>
      <span class="status-dot" :class="node.online ? 'online' : 'offline'"></span>
    </div>

    <div class="node-badges">
      <span class="badge" :class="node.online ? 'badge-green' : 'badge-red'">
        {{ node.online ? 'ONLINE' : 'OFFLINE' }}
      </span>
      <span class="badge badge-dim">{{ node.uptime_hours }}h</span>
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
    </div>

    <!-- Storage -->
    <section v-if="activeStorage.length" class="section">
      <div class="section-title">Storage</div>
      <div class="storage-list">
        <div
          v-for="s in activeStorage"
          :key="s.storage"
          class="storage-row"
        >
          <div class="storage-name-row">
            <Icon name="disk" :size="12" class="storage-ic" :style="{ color: storageColor(s.usage_pct) }" />
            <span class="storage-name">{{ s.storage }}</span>
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
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import UsageBar from './UsageBar.vue'
import Icon from './Icon.vue'

const props = defineProps({
  node: Object,
})

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
  width: 190px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.node-card:hover { border-color: var(--accent); }
.node-card.offline { opacity: 0.55; }

/* Node header */
.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.node-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.node-icon { color: var(--text-muted); }

.node-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
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

.node-badges { display: flex; gap: 5px; align-items: center; }

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

/* Metrics */
.metrics { display: flex; flex-direction: column; gap: 7px; }

/* Sections */
.section { display: flex; flex-direction: column; gap: 6px; }

.section-title {
  font-size: 0.62rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding-bottom: 3px;
  border-bottom: 1px solid var(--border);
}

/* Storage */
.storage-list { display: flex; flex-direction: column; gap: 6px; }

.storage-row { display: flex; flex-direction: column; gap: 3px; }

.storage-name-row {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
}

.storage-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-pct { font-variant-numeric: tabular-nums; font-weight: 600; }

.storage-bar-track {
  height: 3px;
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
</style>
