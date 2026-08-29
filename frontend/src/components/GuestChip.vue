<template>
  <div class="guest-chip" :class="{ stopped: !running }" :title="tip">
    <span class="dot" :class="running ? 'on' : 'off'"></span>
    <Icon :name="kind === 'lxc' ? 'container' : 'vm'" :size="12" class="ic" />
    <span class="name">{{ guest.name }}</span>
    <span v-if="running" class="cpu">{{ Math.round(guest.cpu_usage_pct) }}%</span>
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
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.72rem;
  min-width: 0;
}

.guest-chip.stopped { opacity: 0.5; }

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
}

.cpu {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
</style>
