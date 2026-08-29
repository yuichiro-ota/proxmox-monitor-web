<template>
  <div class="group-header">
    <Icon :name="icon" :size="15" class="group-icon" />
    <span class="group-name">{{ title }}</span>
    <span v-if="count != null" class="group-count">{{ count }}</span>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  icon: { type: String, default: 'cluster' },
  title: String,
  count: { type: [Number, String], default: null },
})
</script>

<style scoped>
.group-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 14px;
}

.group-icon { color: var(--accent); }

.group-name {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text);
}

.group-count {
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 0 7px;
  min-width: 18px;
  text-align: center;
}
</style>
