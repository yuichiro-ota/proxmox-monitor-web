<template>
  <div class="avatar-overlay">
    <transition name="bubble">
      <div
        v-if="message"
        key="msg"
        class="speech-bubble"
        :class="{ alert: alert }"
        :style="{ marginBottom: bubbleOffset + 'px' }"
      >
        {{ message }}
      </div>
      <!-- Ollama へ問い合わせ中: 「・・・」を順に光らせる -->
      <div
        v-else-if="thinking"
        key="thinking"
        class="speech-bubble thinking"
        aria-label="考え中"
        :style="{ marginBottom: bubbleOffset + 'px' }"
      >
        <span class="dot-typing"><i></i><i></i><i></i></span>
      </div>
    </transition>
    <canvas ref="canvasEl" class="avatar-canvas"></canvas>
    <div v-if="loadError" class="avatar-error">アバター読み込み失敗</div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'

const props = defineProps({
  // 吹き出しに出すメッセージ（null なら非表示）
  message: { type: String, default: null },
  // true のとき吹き出しを警告色にし、表情を心配顔にする
  alert: { type: Boolean, default: false },
  // true のとき（セリフ生成の問い合わせ中）「・・・」の吹き出しを出す
  thinking: { type: Boolean, default: false },
  // セリフに合わせた表情 (neutral / happy / sad / worried / surprised / angry)
  emotion: { type: String, default: 'happy' },
  // セリフに合わせて一度だけ再生するモーション名（MOTIONS のキー）
  motion: { type: String, default: '' },
  // false のあいだは描画ループを止める（親側で v-show と併用する）
  visible: { type: Boolean, default: true },
  src: { type: String, default: '/avatar.vrm' },
})

const canvasEl = ref(null)
const loadError = ref(false)
// 吹き出しを頭のすぐ上に置くための下マージン（負の値でキャンバスに食い込ませる）
const bubbleOffset = ref(0)

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
// 口パクの残り秒数と現在の開き具合
let talkTimer = 0
let mouthOpen = 0
// 再生中のモーション { name, t }
let motionState = null
// カメラの画角合わせに使う、読み込み時の頭・腰の位置
let frame = null

const ARM_DOWN = Math.PI / 2 - 0.24
// 頭のボーンより上（髪・頭頂）に取る余白。画面上端はここに合わせる。
// 同梱モデルは頭ボーン 1.44 に対し髪の頂点が 1.66 なので、少し余裕を見た値。
const HEAD_ROOM = 0.27
// 手のボーンから指先までのおおよその長さ（腕の届く範囲に足す）
const FINGER_LEN = 0.12
// 画面の端と中身のあいだに取る余白。体の上下動ぶんもここで吸収する
const FRAME_MARGIN = 0.08

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

// --- ポーズ用ヘルパ -------------------------------------------------------
// VRM の正規化ボーンは T ポーズ基準。左右で符号が反転するのでここで吸収する。
// raise: 0 で腕を下ろした状態、ARM_DOWN で真横、それ以上で万歳方向。
// forward: 正で前に出す。 twist: 腕のひねり。
function setArm(side, raise, forward = 0, twist = 0) {
  const sgn = side === 'left' ? 1 : -1
  const b = bones[`${side}UpperArm`]
  if (b) b.rotation.set(twist, -sgn * forward, sgn * (ARM_DOWN - raise))
}

// fold: 正でひじを曲げて前腕を持ち上げる（腕を横に上げた状態なら手が上に来る）。
// カメラは正面にあるので、正面から見えるこの軸で曲げる。forward は前後（奥行き）方向。
function setElbow(side, fold, forward = 0) {
  const sgn = side === 'left' ? 1 : -1
  const b = bones[`${side}LowerArm`]
  if (b) b.rotation.set(0, -sgn * forward, -sgn * fold)
}

function setHand(side, swing) {
  const sgn = side === 'left' ? 1 : -1
  const b = bones[`${side}Hand`]
  if (b) b.rotation.set(0, 0, sgn * swing)
}

// 頭・体に足し込む差分。毎フレーム 0 に戻してからモーションが書き込む
let add = {}
function resetAdd() {
  add = { headX: 0, headY: 0, headZ: 0, spineX: 0, spineZ: 0, hipsY: 0, hipsZ: 0, bodyY: 0 }
}

const smooth = t => t * t * (3 - 2 * t)
// モーションの入り／抜けをなめらかにする包絡線（前後 20% でフェード）
const envelope = p => smooth(THREE.MathUtils.clamp(Math.min(p, 1 - p) * 5, 0, 1))

// --- モーション定義 -------------------------------------------------------
// fn(p, e): p は 0→1 の進行度、e は包絡線（0→1→0）
const MOTIONS = {
  // あいさつ: 右手を顔の横に上げて振る
  wave: {
    dur: 2.6,
    fn(p, e) {
      const swing = Math.sin(p * Math.PI * 7)
      setArm('right', e * ARM_DOWN * 0.95, 0.2 * e)
      setElbow('right', e * (1.25 + swing * 0.3))
      setHand('right', swing * 0.35 * e)
      add.headZ = -0.09 * e
      add.headX = -0.05 * e
    },
  },
  // うなずき: 2 回こくこく
  nod: {
    dur: 1.6,
    fn(p, e) {
      add.headX = Math.sin(p * Math.PI * 4) * 0.22 * e
      add.spineX = Math.sin(p * Math.PI * 4) * 0.05 * e
    },
  },
  // 首をかしげる（疑問）
  tilt: {
    dur: 2.2,
    fn(p, e) {
      add.headZ = 0.3 * e
      add.headY = 0.1 * e
      add.spineZ = 0.05 * e
      setArm('right', 0.1 * e, 0.1 * e)
    },
  },
  // 喜び: 両手を上げて軽く跳ねる
  cheer: {
    dur: 2.0,
    fn(p, e) {
      const up = e * (ARM_DOWN + 0.7)
      setArm('left', up, 0.1)
      setArm('right', up, 0.1)
      setElbow('left', 0.3 * e)
      setElbow('right', 0.3 * e)
      add.hipsY = Math.abs(Math.sin(p * Math.PI * 3)) * 0.05 * e
      add.headX = -0.12 * e
    },
  },
  // びっくり: のけぞって両手をぱっと開く
  surprised: {
    dur: 1.6,
    fn(p, e) {
      const pop = smooth(THREE.MathUtils.clamp(p * 4, 0, 1)) * e
      setArm('left', ARM_DOWN * 0.6 * pop, 0.3 * pop)
      setArm('right', ARM_DOWN * 0.6 * pop, 0.3 * pop)
      setElbow('left', 1.15 * pop)
      setElbow('right', 1.15 * pop)
      add.headX = -0.16 * pop
      add.spineX = -0.09 * pop
      add.hipsY = 0.02 * pop
    },
  },
  // 考え込む: 右手をあごに当てて視線を上に
  think: {
    dur: 2.8,
    fn(p, e) {
      setArm('right', ARM_DOWN * 0.45 * e, 0.3 * e)
      setElbow('right', 0.08 + 2.15 * e, 0.55 * e)
      add.headZ = -0.14 * e
      add.headX = -0.1 * e
      add.headY = 0.12 * e
      add.spineZ = -0.03 * e
    },
  },
  // 肩をすくめる（やれやれ）
  shrug: {
    dur: 2.0,
    fn(p, e) {
      setArm('left', ARM_DOWN * 0.3 * e, 0.15 * e)
      setArm('right', ARM_DOWN * 0.3 * e, 0.15 * e)
      setElbow('left', 0.08 + 1.25 * e, 0.35 * e)
      setElbow('right', 0.08 + 1.25 * e, 0.35 * e)
      add.headZ = 0.12 * e
      add.headX = 0.06 * e
    },
  },
  // あわてる: 両手を上げてぶんぶん振る
  panic: {
    dur: 2.8,
    fn(p, e) {
      const shake = Math.sin(p * Math.PI * 16)
      setArm('left', e * (ARM_DOWN + 0.5) + shake * 0.14 * e, 0.25)
      setArm('right', e * (ARM_DOWN + 0.5) - shake * 0.14 * e, 0.25)
      setElbow('left', e * (0.5 + shake * 0.25))
      setElbow('right', e * (0.5 - shake * 0.25))
      add.headZ = shake * 0.12 * e
      add.hipsZ = shake * 0.04 * e
      add.headX = -0.08 * e
    },
  },
  // おじぎ
  bow: {
    dur: 2.0,
    fn(p, e) {
      const b = Math.sin(THREE.MathUtils.clamp(p * 1.6, 0, 1) * Math.PI) * e
      add.spineX = 0.34 * b
      add.headX = 0.14 * b
      add.hipsY = -0.05 * b
    },
  },
  // 何気ないひとこと: 体を軽く揺らす
  sway: {
    dur: 2.4,
    fn(p, e) {
      const s = Math.sin(p * Math.PI * 2)
      add.hipsZ = s * 0.06 * e
      add.headZ = -s * 0.1 * e
      add.bodyY = s * 0.1 * e
      setArm('left', 0.06 * e)
      setArm('right', 0.06 * e)
    },
  },
}

function playMotion(name) {
  if (!name || !MOTIONS[name]) return
  motionState = { name, t: 0 }
}

// セリフの長さぶんだけ口を動かす（1文字あたり ≒0.13 秒）
function startTalking(text) {
  if (!text) return
  talkTimer = THREE.MathUtils.clamp(text.length * 0.13, 1.2, 5)
}

async function loadVrm() {
  const loader = new GLTFLoader()
  loader.register(parser => new VRMLoaderPlugin(parser))
  const gltf = await loader.loadAsync(props.src)
  vrm = gltf.userData.vrm
  VRMUtils.removeUnnecessaryVertices?.(gltf.scene)
  VRMUtils.rotateVRM0(vrm) // VRM0.x を +Z 正面に統一
  scene.add(vrm.scene)

  const b = n => vrm.humanoid?.getNormalizedBoneNode(n)
  bones = {
    hips: b('hips'), spine: b('spine'), chest: b('chest'),
    neck: b('neck'), head: b('head'),
    leftUpperArm: b('leftUpperArm'), leftLowerArm: b('leftLowerArm'), leftHand: b('leftHand'),
    rightUpperArm: b('rightUpperArm'), rightLowerArm: b('rightLowerArm'), rightHand: b('rightHand'),
  }
  hipsY = bones.hips ? bones.hips.position.y : 1.0

  resetAdd()
  setArm('left', 0); setArm('right', 0)
  relaxFingers()

  lookTarget = new THREE.Object3D()
  scene.add(lookTarget)
  if (vrm.lookAt) vrm.lookAt.target = lookTarget

  measureFrame()
  setEmotion(props.alert ? 'worried' : props.emotion)
}

// 映す範囲を読み込み時に一度だけ測っておく。
// 下端は腰、上端と左右は「腕を上げたときに手が届く範囲」まで含める
// （含めないと、モーションで振り上げた腕が画面外に出て切れてしまう）。
function measureFrame() {
  vrm.scene.updateWorldMatrix(true, true)
  const head = bones.head, hips = bones.hips
  if (!head || !hips) return
  const wp = b => b.getWorldPosition(new THREE.Vector3())
  const hw = wp(head), pw = wp(hips)
  const headTop = hw.y + HEAD_ROOM

  // 肩の位置と、肩から指先までの長さ。
  // ここを呼ぶ時点で腕は下ろしたポーズなので、関節間の距離を足して求める
  // （関節間の距離はポーズによらず一定）。
  let shoulderX = 0.2, shoulderY = hw.y - 0.1, reach = 0.5
  const ua = bones.leftUpperArm || bones.rightUpperArm
  const la = bones.leftLowerArm || bones.rightLowerArm
  const hand = bones.leftHand || bones.rightHand
  if (ua && la && hand) {
    const uw = wp(ua), lw = wp(la), aw = wp(hand)
    shoulderX = Math.abs(uw.x - hw.x)
    shoulderY = uw.y
    reach = uw.distanceTo(lw) + lw.distanceTo(aw) + FINGER_LEN
  }

  frame = {
    x: hw.x,
    headTop,
    bottom: pw.y,
    // 頭より上に腕が来ることがあるので、高いほうを上端にする
    top: Math.max(headTop, shoulderY + reach) + FRAME_MARGIN,
    halfW: shoulderX + reach + FRAME_MARGIN,
  }
}

// 測った範囲がちょうど収まるようカメラを合わせる。
// キャンバスはウインドウ下端に密着させてあるので、腰から下は画面外に切れる。
function fitCamera() {
  if (!camera || !frame || !canvasEl.value) return
  const vTan = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)
  const hTan = vTan * camera.aspect
  // 縦・横それぞれに必要な距離のうち、遠いほうを採る
  const dist = Math.max(
    Math.max(0.3, frame.top - frame.bottom) / 2 / vTan,
    frame.halfW / hTan,
  )
  // 余ったぶんは上に付ける。こうすると横で決まったときも下端は腰のまま
  const visH = 2 * dist * vTan
  const centerY = frame.bottom + visH / 2
  camera.position.set(frame.x, centerY, dist)
  camera.lookAt(frame.x, centerY, 0)
  camera.updateProjectionMatrix()

  // 髪の先がキャンバス上端から何px下かを求め、吹き出しを頭のすぐ上まで下ろす
  const gap = (centerY + visH / 2 - frame.headTop) / visH * canvasEl.value.clientHeight
  bubbleOffset.value = -Math.max(0, Math.round(gap) - 14)
}

function animate() {
  raf = requestAnimationFrame(animate)
  // 非表示になったら次のフレームを予約せずループを抜ける
  if (!props.visible) { cancelAnimationFrame(raf); raf = null; return }
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

    // 基本姿勢（腕を下ろす）に戻してからモーションを重ねる
    resetAdd()
    setArm('left', 0); setArm('right', 0)
    setElbow('left', 0.08); setElbow('right', 0.08)
    setHand('left', 0); setHand('right', 0)

    if (motionState) {
      const m = MOTIONS[motionState.name]
      motionState.t += dt
      const p = motionState.t / m.dur
      if (p >= 1) {
        motionState = null
      } else {
        m.fn(p, envelope(p))
      }
    }

    // アイドル（呼吸・ゆらぎ）＋ モーションの差分
    const breathe = Math.sin(time * 1.6) * 0.006
    const sway = Math.sin(time * 0.7) * 0.02
    if (bones.hips) {
      bones.hips.position.y = hipsY + breathe * 0.3 + add.hipsY
      bones.hips.rotation.z = sway * 0.5 + add.hipsZ
      bones.hips.rotation.y = add.bodyY
    }
    if (bones.spine) { bones.spine.rotation.x = breathe + add.spineX; bones.spine.rotation.z = add.spineZ }
    if (bones.chest) bones.chest.rotation.x = breathe + add.spineX * 0.4
    // 心配時は少しうつむき＋首をかしげる
    if (bones.head) {
      const droop = props.alert ? 0.12 : 0
      bones.head.rotation.x = droop + Math.sin(time * 0.9) * 0.02 + add.headX
      bones.head.rotation.y = add.headY
      bones.head.rotation.z = (props.alert ? 0.08 : 0) + Math.sin(time * 0.5) * 0.015 + add.headZ
    }

    // カメラ方向へ視線
    if (lookTarget) lookTarget.position.set(frame ? frame.x : 0, frame ? frame.top - HEAD_ROOM : 1.4, 2.0)

    // 口パク（セリフ表示中だけ動かす）
    let mouthTarget = 0
    if (talkTimer > 0) {
      talkTimer -= dt
      mouthTarget = (0.55 + 0.45 * Math.sin(time * 17)) * (0.45 + 0.35 * Math.sin(time * 6.7))
    }
    mouthOpen += (mouthTarget - mouthOpen) * Math.min(1, dt * 18)

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
      setExpr('aa', mouthOpen)
    }

    vrm.update(dt)
  }

  renderer.render(scene, camera)
}

function onResize() {
  const el = canvasEl.value
  if (!el || !renderer) return
  const w = el.clientWidth, h = el.clientHeight
  if (!w || !h) return
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  fitCamera()
}

onMounted(async () => {
  const canvas = canvasEl.value
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)

  scene = new THREE.Scene()
  // 上半身〜顔だけを大きく映す（腰から下はウインドウ下端で切る）
  camera = new THREE.PerspectiveCamera(28, 1, 0.1, 20)
  camera.position.set(0, 1.2, 1.6)

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
  if (props.visible) animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('resize', onResize)
  if (vrm) VRMUtils.deepDispose?.(vrm.scene)
  renderer?.dispose()
})

// 非表示のあいだは描画を止め、再表示でサイズを測り直してから再開する
watch(() => props.visible, async v => {
  if (v) {
    await nextTick()
    onResize()
    lastT = performance.now()
    if (!raf) animate()
  } else {
    cancelAnimationFrame(raf)
    raf = null
  }
})

// 心配モードの切替で表情を更新
watch(() => props.alert, v => {
  if (!vrm) return
  setEmotion(v ? 'worried' : props.emotion)
  if (v) playMotion('panic')
})

// セリフに合わせた表情
watch(() => props.emotion, v => { if (vrm && !props.alert) setEmotion(v) })

// 新しいセリフが出たら、口パクと指定モーションを再生
watch(() => props.message, (v, old) => {
  if (!v || v === old) return
  startTalking(v)
  playMotion(props.alert ? 'panic' : (props.motion || 'sway'))
})
</script>

<style scoped>
/* ウインドウ右下に密着させ、上半身から下は画面の外に切れるようにする */
.avatar-overlay {
  position: fixed;
  right: 0;
  bottom: 0;
  /* 腕を上げるモーションが切れないよう縦横に余裕を持たせる（キャンバスは透過）。
     狭いウインドウでは縦横比を保ったまま縮む */
  width: min(620px, 60vw);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  z-index: 900;
  pointer-events: none; /* 背後の系統図を操作できるように */
}

.avatar-canvas {
  width: 100%;
  /* 腕を広げた範囲がちょうど入る比率。fitCamera() はこの比率で画角を合わせる */
  aspect-ratio: 620 / 430;
  display: block;
}

.speech-bubble {
  position: relative;
  margin-bottom: 10px; /* fitCamera() が頭の位置に合わせて上書きする */
  max-width: 260px;
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

/* 問い合わせ中の「・・・」吹き出し */
.speech-bubble.thinking {
  padding: 10px 16px;
  border-color: var(--border, #999);
}
.speech-bubble.thinking::after {
  border-top-color: var(--border, #999);
}

.dot-typing {
  display: flex;
  align-items: center;
  gap: 5px;
}
.dot-typing i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted, #888);
  animation: dot-typing 1.2s ease-in-out infinite;
}
.dot-typing i:nth-child(2) { animation-delay: 0.2s; }
.dot-typing i:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-typing {
  0%, 60%, 100% { opacity: 0.25; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
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
.bubble-enter-from, .bubble-leave-to { opacity: 0; transform: translateY(8px); }

@keyframes shake {
  0%, 100% { transform: translateX(0) rotate(0deg); }
  25% { transform: translateX(-2px) rotate(-1.5deg); }
  75% { transform: translateX(2px) rotate(1.5deg); }
}

@media (max-width: 640px) {
  .avatar-overlay { width: 78vw; }
  .speech-bubble { font-size: 0.78rem; max-width: 180px; }
}
</style>
