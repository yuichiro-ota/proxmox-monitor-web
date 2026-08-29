<template>
  <div class="topo-box" :class="variant">
    <div class="topo-box-head">
      <Icon :name="icon" :size="18" class="topo-icon" />
      <span class="topo-title">{{ title }}</span>
    </div>
    <div v-if="subtitle" class="topo-sub">{{ subtitle }}</div>
    <div v-if="badges && badges.length" class="topo-badges">
      <span
        v-for="b in badges"
        :key="b.text"
        class="badge"
        :class="`badge-${b.tone || 'dim'}`"
      >{{ b.text }}</span>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  icon: { type: String, default: 'router' },
  title: String,
  subtitle: String,
  badges: { type: Array, default: () => [] },
  variant: { type: String, default: 'router' }, // 'router' | 'segment'
})
</script>

<style scoped>
.topo-box {
  min-width: 180px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  text-align: center;
}

.topo-box.router {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.25), 0 4px 18px rgba(99, 102, 241, 0.12);
}

.topo-box.segment {
  background: var(--surface-2);
}

.topo-box-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.topo-box.router .topo-icon { color: var(--accent); }
.topo-box.segment .topo-icon { color: var(--text-muted); }

.topo-title {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text);
}

.topo-sub {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.topo-badges { display: flex; gap: 5px; flex-wrap: wrap; justify-content: center; }

.badge {
  font-size: 0.6rem;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 20px;
  letter-spacing: 0.04em;
}

.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red   { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-accent{ background: rgba(99,102,241,0.18); color: var(--accent); }
.badge-dim   { background: var(--surface); color: var(--text-muted); border: 1px solid var(--border); }
</style>
