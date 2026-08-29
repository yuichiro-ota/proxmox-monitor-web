<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal" role="dialog" aria-modal="true">
      <button class="modal-close" @click="$emit('close')" aria-label="閉じる">✕</button>
      <DetailCard :type="type" :data="data" :kind="kind" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import DetailCard from './DetailCard.vue'

defineProps({
  type: String,       // 'node' | 'guest' | 'host'
  data: Object,
  kind: String,       // guest: 'vm' | 'lxc'
})
const emit = defineEmits(['close'])

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(4, 6, 14, 0.66);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 1000;
}

.modal {
  position: relative;
  width: 100%;
  max-width: 420px;
  max-height: 85vh;
  overflow-y: auto;
  border-radius: var(--radius);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-muted);
  width: 26px;
  height: 26px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  line-height: 1;
  z-index: 1;
}
.modal-close:hover { color: var(--text); border-color: var(--accent); }
</style>
