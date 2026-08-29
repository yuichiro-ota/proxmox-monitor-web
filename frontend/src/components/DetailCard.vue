<template>
  <div class="detail-card">
    <div class="dc-head">
      <Icon :name="headIcon" :size="20" class="dc-icon" />
      <div class="dc-head-text">
        <div class="dc-title">{{ title }}</div>
        <div v-if="subtitle" class="dc-sub">{{ subtitle }}</div>
      </div>
    </div>

    <div v-if="badges.length" class="dc-badges">
      <span v-for="b in badges" :key="b.text" class="badge" :class="`badge-${b.tone}`">{{ b.text }}</span>
    </div>

    <div v-if="bars.length" class="dc-metrics">
      <UsageBar
        v-for="m in bars"
        :key="m.label"
        :label="m.label"
        :pct="m.pct"
        :display-value="m.value"
      />
    </div>

    <div v-if="storages.length" class="dc-section">
      <div class="sec-title">STORAGE</div>
      <UsageBar
        v-for="s in storages"
        :key="s.storage"
        :label="`${s.storage} (${s.type})`"
        :pct="s.usage_pct"
        :display-value="`${s.used_gb} / ${s.total_gb} GB`"
      />
    </div>

    <div v-if="details.length" class="dc-section">
      <div class="detail-grid">
        <template v-for="d in details" :key="d.k">
          <div class="dk">{{ d.k }}</div>
          <div class="dv">{{ d.v }}</div>
        </template>
      </div>
    </div>

    <div v-if="guestLines.length" class="dc-section">
      <div class="sec-title">VM / LXC ({{ guestLines.length }})</div>
      <div class="guest-lines">
        <div v-for="g in guestLines" :key="g.key" class="guest-line">
          <span class="gdot" :class="g.running ? 'on' : 'off'"></span>
          <Icon :name="g.kind === 'lxc' ? 'container' : 'vm'" :size="12" class="gic" />
          <span class="gname">{{ g.name }}</span>
          <span class="gstat">{{ g.running ? 'running' : 'stopped' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import UsageBar from './UsageBar.vue'
import Icon from './Icon.vue'

const props = defineProps({
  type: String,       // 'node' | 'guest' | 'host'
  data: Object,
  kind: String,       // guest: 'vm' | 'lxc'
})

const headIcon = computed(() => {
  if (props.type === 'node') return 'server'
  if (props.type === 'host') return 'monitor'
  return props.kind === 'lxc' ? 'container' : 'vm'
})

const title = computed(() =>
  props.type === 'node' ? props.data.node : props.data.name
)

const subtitle = computed(() => {
  if (props.type === 'host') return `${props.data.hostname} · ${props.data.ip}`
  return ''
})

const badges = computed(() => {
  const d = props.data
  if (props.type === 'node') {
    return [
      { text: d.online ? 'ONLINE' : 'OFFLINE', tone: d.online ? 'green' : 'red' },
      { text: `${d.uptime_hours}h`, tone: 'dim' },
    ]
  }
  if (props.type === 'host') {
    const os = d.os === 'windows' ? 'Windows' : d.os === 'linux' ? 'Linux' : (d.os || '—')
    const b = [
      { text: d.online ? 'ONLINE' : 'OFFLINE', tone: d.online ? 'green' : 'red' },
      { text: os, tone: 'dim' },
    ]
    if (d.online && d.uptime_hours != null) b.push({ text: `${d.uptime_hours}h`, tone: 'dim' })
    return b
  }
  // guest
  const running = d.status === 'running'
  return [
    { text: running ? 'RUNNING' : 'STOPPED', tone: running ? 'green' : 'dim' },
    { text: props.kind === 'lxc' ? 'LXC' : 'VM', tone: 'dim' },
    { text: `VMID ${d.vmid}`, tone: 'dim' },
  ]
})

const bars = computed(() => {
  const d = props.data
  if (props.type === 'node') {
    if (!d.online) return []
    const out = [
      { label: 'CPU', pct: d.cpu.usage_pct, value: `${d.cpu.usage_pct}% / ${d.cpu.cores}core` },
      { label: 'MEM', pct: d.memory.usage_pct, value: `${d.memory.used_gb} / ${d.memory.total_gb} GB` },
    ]
    if (d.rootfs) out.push({ label: 'rootfs', pct: d.rootfs.usage_pct, value: `${d.rootfs.used_gb} / ${d.rootfs.total_gb} GB` })
    return out
  }
  if (props.type === 'host') {
    if (!d.online) return []
    const out = [
      { label: 'CPU', pct: d.cpu.usage_pct, value: `${d.cpu.usage_pct}% / ${d.cpu.cores}core` },
      { label: 'MEM', pct: d.memory.usage_pct, value: `${d.memory.used_gb} / ${d.memory.total_gb} GB` },
    ]
    if (d.disk) out.push({ label: 'DISK', pct: d.disk.usage_pct, value: `${d.disk.used_gb} / ${d.disk.total_gb} GB` })
    return out
  }
  // guest
  if (d.status !== 'running') return []
  const max = d.memory?.max_gb || 0
  const used = d.memory?.used_gb || 0
  const memPct = max > 0 ? Math.round((used / max) * 1000) / 10 : 0
  return [
    { label: 'CPU', pct: d.cpu_usage_pct, value: `${d.cpu_usage_pct}%` },
    { label: 'MEM', pct: memPct, value: `${used} / ${max} GB` },
  ]
})

const storages = computed(() => {
  if (props.type !== 'node') return []
  return (props.data.storage || []).filter(s => s.active && s.total_gb > 0)
})

const details = computed(() => {
  const d = props.data
  if (props.type === 'node') {
    return [
      { k: 'CPUコア', v: d.cpu?.cores ?? '—' },
      { k: '稼働時間', v: `${d.uptime_hours}h` },
      { k: 'VM数', v: (d.vms || []).length },
      { k: 'LXC数', v: (d.lxc || []).length },
    ]
  }
  if (props.type === 'host') {
    return [
      { k: 'ホスト名', v: d.hostname },
      { k: 'IP', v: d.ip },
      { k: 'OS', v: d.os },
      { k: '稼働時間', v: d.uptime_hours != null ? `${d.uptime_hours}h` : '—' },
    ]
  }
  return [
    { k: 'VMID', v: d.vmid },
    { k: '状態', v: d.status },
    { k: 'ディスク', v: `${d.disk_gb} GB` },
    { k: '稼働時間', v: `${d.uptime_hours}h` },
  ]
})

const guestLines = computed(() => {
  if (props.type !== 'node') return []
  const vms = (props.data.vms || []).map(g => ({ kind: 'vm', ...g }))
  const lxc = (props.data.lxc || []).map(g => ({ kind: 'lxc', ...g }))
  return [...vms, ...lxc]
    .sort((a, b) => {
      const ar = a.status === 'running', br = b.status === 'running'
      if (ar !== br) return ar ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    .map(g => ({ key: `${g.kind}-${g.vmid}`, name: g.name, kind: g.kind, running: g.status === 'running' }))
})
</script>

<style scoped>
.detail-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dc-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dc-icon { color: var(--accent); flex-shrink: 0; }
.dc-title { font-size: 1.05rem; font-weight: 700; color: var(--text); }
.dc-sub { font-size: 0.78rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }

.dc-badges { display: flex; gap: 6px; flex-wrap: wrap; }

.badge {
  font-size: 0.62rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 20px;
  letter-spacing: 0.04em;
}
.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red   { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-dim   { background: var(--surface-2); color: var(--text-muted); }

.dc-metrics { display: flex; flex-direction: column; gap: 10px; }

.dc-section { display: flex; flex-direction: column; gap: 8px; }

.sec-title {
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.detail-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 16px;
  font-size: 0.82rem;
}
.dk { color: var(--text-muted); }
.dv { color: var(--text); text-align: right; font-variant-numeric: tabular-nums; word-break: break-all; }

.guest-lines { display: flex; flex-direction: column; gap: 5px; }
.guest-line { display: flex; align-items: center; gap: 7px; font-size: 0.8rem; }
.gdot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.gdot.on { background: var(--green); }
.gdot.off { background: var(--text-muted); }
.gic { color: var(--text-muted); flex-shrink: 0; }
.gname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.gstat { color: var(--text-muted); font-size: 0.72rem; }
</style>
