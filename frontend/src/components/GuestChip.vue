<template>
  <div class="guest-chip" :class="{ stopped: !running }" :title="tip">
    <div class="chip-head">
      <span class="dot" :class="running ? 'on' : 'off'"></span>
      <Icon :name="kind === 'lxc' ? 'container' : 'vm'" :size="12" class="ic" />
      <span class="name">{{ guest.name }}</span>
    </div>

    <template v-if="running">
      <div class="chip-bar">
        <span class="cl">CPU</span>
        <span class="tk"><span class="fl" :style="{ width: clamp(cpuPct) + '%', background: color(cpuPct) }"></span></span>
        <span class="cv">{{ Math.round(cpuPct) }}%</span>
      </div>
      <div class="chip-bar">
        <span class="cl">MEM</span>
        <span class="tk"><span class="fl" :style="{ width: clamp(memPct) + '%', background: color(memPct) }"></span></span>
        <span class="cv">{{ Math.round(memPct) }}%</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  guest: Object,
  kind: String, // 'vm' | 'lxc'
})

const running = computed(() => props.guest.status === 'running')
const cpuPct = computed(() => props.guest.cpu_usage_pct || 0)
const memPct = computed(() => {
  const max = props.guest.memory?.max_gb || 0
  const used = props.guest.memory?.used_gb || 0
  return max > 0 ? (used / max) * 100 : 0
})

function clamp(v) { return Math.min(Math.max(v, 0), 100) }
function color(pct) {
  if (pct >= 80) return 'var(--red)'
  if (pct >= 60) return 'var(--yellow)'
  return 'var(--green)'
}

const tip = computed(() => {
  const g = props.guest
  if (g.status !== 'running') return `${g.name} (stopped)`
  const mem = g.memory ? ` · MEM ${g.memory.used_gb}/${g.memory.max_gb}GB` : ''
  return `${g.name} · CPU ${g.cpu_usage_pct}%${mem}`
})
</script>

<style scoped>
.guest-chip {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 5px 7px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.guest-chip:hover { border-color: var(--accent); }
.guest-chip.stopped { opacity: 0.5; }

.chip-head {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot.on { background: var(--green); box-shadow: 0 0 4px var(--green); }
.dot.off { background: var(--text-muted); }

.ic { color: var(--text-muted); flex-shrink: 0; }

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-size: 0.72rem;
}

.chip-bar {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cl {
  font-size: 0.58rem;
  color: var(--text-muted);
  width: 26px;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.tk {
  flex: 1;
  max-width: 96px;
  height: 3px;
  background: var(--surface);
  border-radius: 2px;
  overflow: hidden;
}

.fl {
  display: block;
  height: 100%;
  border-radius: 2px;
  min-width: 1px;
}

.cv {
  font-size: 0.55rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  width: 24px;
  text-align: right;
  flex-shrink: 0;
}
</style>
