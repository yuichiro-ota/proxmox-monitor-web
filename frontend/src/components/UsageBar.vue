<template>
  <div class="usage-bar-wrap">
    <div class="usage-bar-header">
      <span class="usage-label">{{ label }}</span>
      <span class="usage-value">{{ displayValue }}</span>
    </div>
    <div class="usage-bar-track">
      <div
        class="usage-bar-fill"
        :style="{ width: `${pct}%`, background: color }"
      ></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: String,
  pct: Number,
  displayValue: String,
})

const color = computed(() => {
  if (props.pct >= 80) return 'var(--red)'
  if (props.pct >= 60) return 'var(--yellow)'
  return 'var(--green)'
})
</script>

<style scoped>
.usage-bar-wrap { display: flex; flex-direction: column; gap: 4px; }

.usage-bar-header {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
}

.usage-label { color: var(--text-muted); }
.usage-value { color: var(--text); font-variant-numeric: tabular-nums; }

.usage-bar-track {
  height: 6px;
  background: var(--surface-2);
  border-radius: 3px;
  overflow: hidden;
}

.usage-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease, background 0.4s ease;
  min-width: 2px;
}
</style>
