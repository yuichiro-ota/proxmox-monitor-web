<template>
  <div class="avatar-overlay">
    <transition name="bubble">
      <div v-if="message" class="speech-bubble" :class="{ alert: alert }">
        {{ message }}
      </div>
    </transition>
    <canvas ref="canvasEl" class="avatar-canvas"></canvas>
    <div v-if="loadError" class="avatar-error">アバター読み込み失敗</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'

const props = defineProps({
  // 吹き出しに出すメッセージ（null なら非表示）
  message: { type: String, default: null },
  // true のとき吹き出しを警告色にし、表情を心配顔にする
  alert: { type: Boolean, default: false },
  src: { type: String, default: '/avatar.vrm' },
})

const canvasEl = ref(null)
const loadError = ref(false)

let renderer, scene, camera, vrm, lookTarget, raf
let lastT = 0
let bones = null
let hipsY = 1.0
let time = 0
let blinkTimer = 2 + Math.random() * 3
let blinkPhase = 0
// 表情のなめらか遷移用ウェイト
const exprWeights = {}
let emotionTarget = { happy: 0.35 }

const ARM_DOWN = Math.PI / 2 - 0.24

function setEmotion(name) {
  const map = {
    neutral: { happy: 0.15 },
    happy: { happy: 0.35 },
    sad: { sad: 0.9 },
    worried: { sad: 0.6, angry: 0.15 },
    surprised: { surprised: 1.0 },
    angry: { angry: 0.8 },
  }
  emotionTarget = map[name] || map.neutral
}

function setExpr(nm, v) {
  const em = vrm?.expressionManager
  if (!em || !em.setValue) return
  try { em.setValue(nm, THREE.MathUtils.clamp(v, 0, 1)) } catch (_) {}
}

function relaxFingers() {
  const get = n => vrm.humanoid?.getNormalizedBoneNode(n)
  const fingers = ['Index', 'Middle', 'Ring', 'Little']
  for (const side of ['left', 'right']) {
    const sgn = side === 'left' ? 1 : -1
    for (const f of fingers) {
      for (const [seg, curl] of [['Proximal', 0.28], ['Intermediate', 0.35], ['Distal', 0.2]]) {
        const n = get(`${side}${f}${seg}`)
        if (n) n.rotation.z = sgn * curl
      }
    }
    const thumb = get(`${side}ThumbProximal`)
    if (thumb) thumb.rotation.y = sgn * 0.3
  }
}

function armsDown() {
  const uL = vrm.humanoid?.getNormalizedBoneNode('leftUpperArm')
  const uR = vrm.humanoid?.getNormalizedBoneNode('rightUpperArm')
  if (uL) uL.rotation.z = ARM_DOWN
  if (uR) uR.rotation.z = -ARM_DOWN
}

async function loadVrm() {
  const loader = new GLTFLoader()
  loader.register(parser => new VRMLoaderPlugin(parser))
  const gltf = await loader.loadAsync(props.src)
  vrm = gltf.userData.vrm
  VRMUtils.removeUnnecessaryVertices?.(gltf.scene)
  VRMUtils.rotateVRM0(vrm) // VRM0.x を +Z 正面に統一
  vrm.scene.position.y = -0.16 // フレーム内で少し下げ、頭上に吹き出し用の余白を作る
  scene.add(vrm.scene)

  const b = n => vrm.humanoid?.getNormalizedBoneNode(n)
  bones = {
    hips: b('hips'), spine: b('spine'), chest: b('chest'),
    neck: b('neck'), head: b('head'),
  }
  hipsY = bones.hips ? bones.hips.position.y : 1.0

  armsDown()
  relaxFingers()

  lookTarget = new THREE.Object3D()
  scene.add(lookTarget)
  if (vrm.lookAt) vrm.lookAt.target = lookTarget

  setEmotion(props.alert ? 'worried' : 'happy')
}

function animate() {
  raf = requestAnimationFrame(animate)
  const now = performance.now()
  const dt = Math.min((now - lastT) / 1000, 0.05)
  lastT = now
  time += dt

  if (vrm) {
    // 瞬き
    blinkTimer -= dt
    if (blinkTimer <= 0) { blinkPhase = 0.22; blinkTimer = 1.8 + Math.random() * 4 }
    let blink = 0
    if (blinkPhase > 0) {
      blinkPhase -= dt
      const k = 1 - Math.abs((blinkPhase / 0.22) * 2 - 1)
      blink = Math.min(1, k * 1.4)
    }

    // アイドル（呼吸・ゆらぎ）
    const breathe = Math.sin(time * 1.6) * 0.006
    const sway = Math.sin(time * 0.7) * 0.02
    if (bones.hips) {
      bones.hips.position.y = hipsY + breathe * 0.3
      bones.hips.rotation.z = sway * 0.5
    }
    if (bones.spine) bones.spine.rotation.x = breathe
    if (bones.chest) bones.chest.rotation.x = breathe
    // 心配時は少しうつむき＋首をかしげる
    if (bones.head) {
      const droop = props.alert ? 0.12 : 0
      bones.head.rotation.x = droop + Math.sin(time * 0.9) * 0.02
      bones.head.rotation.z = (props.alert ? 0.08 : 0) + Math.sin(time * 0.5) * 0.015
    }

    // カメラ方向へ視線
    if (lookTarget) lookTarget.position.set(0, 1.4, 2.0)

    // 表情
    const em = vrm.expressionManager
    if (em) {
      if (em.getExpression?.('blinkLeft') || em.getExpression?.('blinkRight')) {
        setExpr('blinkLeft', blink); setExpr('blinkRight', blink)
      } else {
        setExpr('blink', blink)
      }
      for (const name of ['happy', 'angry', 'sad', 'relaxed', 'surprised']) {
        const target = emotionTarget[name] || 0
        const cur = exprWeights[name] || 0
        const next = cur + (target - cur) * Math.min(1, dt * 4)
        exprWeights[name] = next
        setExpr(name, next * (1 - blink))
      }
    }

    vrm.update(dt)
  }

  renderer.render(scene, camera)
}

function onResize() {
  const el = canvasEl.value
  if (!el || !renderer) return
  const w = el.clientWidth, h = el.clientHeight
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

onMounted(async () => {
  const canvas = canvasEl.value
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)

  scene = new THREE.Scene()
  // 上半身〜顔を大きめに映す
  camera = new THREE.PerspectiveCamera(28, 1, 0.1, 20)
  camera.position.set(0, 1.32, 1.9)
  camera.lookAt(0, 1.28, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.9))
  const key = new THREE.DirectionalLight(0xffffff, 0.9)
  key.position.set(1, 2, 2)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0x88aaff, 0.4)
  rim.position.set(-1.5, 1.5, -1.5)
  scene.add(rim)

  lastT = performance.now()

  try {
    await loadVrm()
  } catch (e) {
    console.error('[avatar] VRM load failed:', e)
    loadError.value = true
  }

  onResize()
  window.addEventListener('resize', onResize)
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('resize', onResize)
  if (vrm) VRMUtils.deepDispose?.(vrm.scene)
  renderer?.dispose()
})

// 心配モードの切替で表情を更新
watch(() => props.alert, v => { if (vrm) setEmotion(v ? 'worried' : 'happy') })
</script>

<style scoped>
.avatar-overlay {
  position: fixed;
  right: 16px;
  bottom: 16px;
  width: 260px;
  height: 380px;
  z-index: 900;
  pointer-events: none; /* 背後の系統図を操作できるように */
}

.avatar-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.speech-bubble {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  max-width: 240px;
  padding: 10px 14px;
  background: var(--surface, #fff);
  border: 2px solid var(--accent, #3b82f6);
  border-radius: 14px;
  color: var(--text, #111);
  font-size: 0.9rem;
  font-weight: 700;
  line-height: 1.35;
  text-align: center;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  white-space: pre-line;
}

.speech-bubble.alert {
  border-color: var(--red, #ef4444);
  color: var(--red, #ef4444);
  animation: shake 0.4s ease-in-out infinite;
}

/* 吹き出しのしっぽ（下向き） */
.speech-bubble::after {
  content: '';
  position: absolute;
  bottom: -10px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 10px 8px 0 8px;
  border-style: solid;
  border-color: var(--accent, #3b82f6) transparent transparent transparent;
}
.speech-bubble.alert::after {
  border-top-color: var(--red, #ef4444);
}

.avatar-error {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: var(--text-muted, #888);
}

.bubble-enter-active, .bubble-leave-active { transition: opacity 0.25s, transform 0.25s; }
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

@keyframes shake {
  0%, 100% { transform: translateX(-50%) rotate(0deg); }
  25% { transform: translateX(-52%) rotate(-1.5deg); }
  75% { transform: translateX(-48%) rotate(1.5deg); }
}

@media (max-width: 640px) {
  .avatar-overlay { width: 170px; height: 250px; right: 6px; bottom: 6px; }
  .speech-bubble { font-size: 0.78rem; max-width: 160px; }
}
</style>
