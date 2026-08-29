<template>
  <div class="summary">
    <!-- 集計タイル（稼働/総数・系統図と同じアイコン） -->
    <div class="stat-row">
      <div class="stat" :class="t.status" v-for="t in tiles" :key="t.label">
        <span class="stat-num">
          <span class="v">{{ t.value }}</span><span class="t">/{{ t.total }}</span>
        </span>
        <span class="stat-label">
          <Icon :name="t.icon" :size="13" class="stat-ico" />
          {{ t.label }}
        </span>
      </div>
    </div>

    <!-- 警告メッセージ -->
    <div v-if="warnings.length" class="warn-list">
      <div
        v-for="(w, i) in warnings"
        :key="i"
        class="warn-item"
        :class="w.level"
      >
        <span class="warn-ico">{{ w.level === 'critical' ? '🔴' : '⚠️' }}</span>
        <span class="warn-text">{{ w.text }}</span>
      </div>
    </div>
    <div v-else class="all-ok">
      <span class="warn-ico">✅</span>
      <span>すべて正常に稼働しています</span>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  tiles: { type: Array, default: () => [] },
  warnings: { type: Array, default: () => [] },
})
</script>

<style scoped>
.summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 8px;
}

/* --- 集計タイル --- */
.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stat {
  position: relative;
  flex: 1 1 120px;
  min-width: 110px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 12px 10px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: box-shadow 0.2s, border-color 0.2s;
}

/* 左端のステータスバー（緑=正常 / 赤=異常） */
.stat::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  background: var(--text-muted);
}
.stat.ok::before { background: var(--green); }
.stat.bad::before { background: var(--red); }

/* 異常タイルは枠と淡いにじみで強調 */
.stat.bad {
  border-color: rgba(239, 68, 68, 0.45);
  box-shadow: inset 10px 0 18px -12px var(--red);
}
.stat.ok {
  box-shadow: inset 10px 0 18px -14px var(--green);
}

.stat-num {
  display: flex;
  align-items: baseline;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.stat-num .v {
  font-size: 1.6rem;
  font-weight: 800;
  color: var(--text);
}
.stat-num .t {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-muted);
}

.stat-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.66rem;
  color: var(--text-muted);
  letter-spacing: 0.04em;
  text-align: center;
}
.stat-ico { color: var(--accent); flex-shrink: 0; }

/* --- 警告リスト --- */
.warn-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.warn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  border: 1px solid var(--border);
}

.warn-item.critical {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--red);
  font-weight: 700;
}

.warn-item.warn {
  background: rgba(234, 179, 8, 0.1);
  border-color: rgba(234, 179, 8, 0.35);
  color: var(--yellow);
}

.warn-ico { flex-shrink: 0; }
.warn-text { min-width: 0; }

.all-ok {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  color: var(--green);
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.25);
}
</style>
