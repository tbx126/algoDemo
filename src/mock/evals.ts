import type { EvalRun, EvalStatus } from '@/types'
import { algorithms } from './algorithms'
import { benchmarks } from './benchmarks'
import { fakeSha, hashStr, rng } from '@/utils/format'

// 算法“实力”与速度画像，用于生成可信的指标
const profile: Record<string, { q: number; ms: number; mem: number }> = {
  'vision-lab/resnet50-defect': { q: 0.72, ms: 6.1, mem: 1.4 },
  'vision-lab/efficientnet-b3-defect': { q: 0.78, ms: 8.4, mem: 1.2 },
  'vision-lab/vit-small-defect': { q: 0.83, ms: 9.7, mem: 1.9 },
  'univ-cvlab/convnext-t-defect': { q: 0.86, ms: 11.2, mem: 1.8 },
  'vision-lab/mobilenetv3-defect': { q: 0.6, ms: 2.3, mem: 0.5 },
  'vision-lab/yolo-lite-s': { q: 0.74, ms: 7.8, mem: 2.1 },
  'vision-lab/rtdetr-r18': { q: 0.8, ms: 11.5, mem: 2.8 },
  'vision-lab/faster-rcnn-r50-fpn': { q: 0.66, ms: 38.0, mem: 3.5 },
  'smart-city/yolo-lite-n-traffic': { q: 0.62, ms: 3.2, mem: 0.9 },
  'deepsee/tiled-small-det': { q: 0.85, ms: 64.0, mem: 4.3 },
  'partner-xyz/xy-det-tiny': { q: 0.58, ms: 4.0, mem: 0.8 },
  'partner-xyz/xy-seg-lite': { q: 0.63, ms: 7.2, mem: 0.7 },
  'vision-lab/unet-r34-road': { q: 0.66, ms: 21.0, mem: 1.8 },
  'vision-lab/deeplabv3plus-r50': { q: 0.76, ms: 44.0, mem: 3.2 },
  'vision-lab/segformer-b2': { q: 0.84, ms: 36.0, mem: 2.7 },
  'smart-city/bisenet-v2-road': { q: 0.6, ms: 9.5, mem: 1.0 },
  'medical-ai/mask-rcnn-nuclei': { q: 0.7, ms: 82.0, mem: 3.4 },
  'medical-ai/star-nuclei-net': { q: 0.78, ms: 31.0, mem: 1.6 },
  'signal-team/fft-envelope-svm': { q: 0.74, ms: 0.8, mem: 0 },
  'signal-team/cnn1d-fault': { q: 0.82, ms: 1.6, mem: 0.3 },
}

function metricsFor(benchId: string, algoId: string, ver: string): Record<string, number> {
  const p = profile[algoId] ?? { q: 0.6, ms: 10, mem: 1 }
  const r = rng(hashStr(benchId + algoId + ver))
  // 新版本略优于旧版本；随机扰动小于版本增益，保证同一算法的版本顺序合理
  const [major, minor] = ver.slice(1).split('.').map(Number)
  const verBoost = major * 0.05 + minor * 0.035
  const q = Math.min(0.97, p.q + verBoost + (r() - 0.5) * 0.006)
  const j = () => (r() - 0.5) * 2
  const ms = +(p.ms * (1 + j() * 0.05)).toFixed(1)
  const mem = +(p.mem * (1 + j() * 0.04)).toFixed(2)
  switch (benchId) {
    case 'defect-cls-v3':
      return { top1: 88 + q * 10 + j() * 0.3, top5: 99 + q * 0.9, macro_f1: 0.8 + q * 0.17, latency_ms: ms, peak_mem_gb: mem }
    case 'street-det-v4':
      return { map: 30 + q * 25 + j() * 0.3, map50: 50 + q * 26, map_small: 14 + q * 18, ar100: 44 + q * 22, latency_ms: ms, peak_mem_gb: mem }
    case 'traffic-det-small':
      return { map_small: 10 + q * 26 + j() * 0.3, map: 32 + q * 22, map50: 55 + q * 24, latency_ms: ms * 1.1, peak_mem_gb: mem }
    case 'road-seg-v2':
      return { miou: 58 + q * 24 + j() * 0.3, pixel_acc: 90 + q * 6, mdice: 68 + q * 20, latency_ms: ms, peak_mem_gb: mem }
    case 'nuclei-seg-v2':
      return { mask_ap: 28 + q * 20 + j() * 0.3, mask_ap50: 60 + q * 24, aji: 0.5 + q * 0.2, latency_ms: ms, peak_mem_gb: mem }
    case 'vibration-fault-v3':
      return { acc: 85 + q * 13 + j() * 0.3, macro_f1: 0.82 + q * 0.16, auc: 0.9 + q * 0.09, latency_ms: ms }
  }
  return {}
}

const taskOfBench = Object.fromEntries(benchmarks.map((b) => [b.id, b.task]))

const runs: EvalRun[] = []
let n = 0
const submitters = ['li.na', 'chen.wei', 'zhao.lei', 'wang.fang', 'sun.yu', 'wu.hao']

function push(benchId: string, algoId: string, ver: string, status: EvalStatus, hoursAgo: number, latest: boolean, extra: Partial<EvalRun> = {}) {
  const a = algorithms.find((x) => x.id === algoId)!
  const v = a.versions.find((x) => x.version === ver)!
  const b = benchmarks.find((x) => x.id === benchId)!
  const id = `ev-${(1042 + n++).toString()}`
  const submitted = new Date(new Date('2026-11-19T12:00:00+08:00').getTime() - hoursAgo * 3600000)
  const m = status === 'succeeded' ? metricsFor(benchId, algoId, ver) : {}
  const dur = status === 'succeeded' ? 120 + (hashStr(id) % 1400) : undefined
  const started = new Date(submitted.getTime() + 60000 * (1 + (hashStr(id) % 9)))
  runs.push({
    id,
    algorithmId: algoId,
    algoVersion: ver,
    benchmarkId: benchId,
    status,
    progress: status === 'succeeded' ? 100 : status === 'running' ? 63 : status === 'failed' ? 41 : 0,
    submittedBy: a.org === 'partner-xyz' ? 'xy.liu' : a.org === 'univ-cvlab' ? 'qm.he' : a.org === 'deepsee' ? 'ds.zhang' : submitters[hashStr(id) % submitters.length],
    submittedAt: submitted.toISOString(),
    startedAt: status === 'queued' ? undefined : started.toISOString(),
    finishedAt: dur ? new Date(started.getTime() + dur * 1000).toISOString() : status === 'failed' ? new Date(started.getTime() + 300000).toISOString() : undefined,
    metrics: m,
    imageDigest: v.imageDigest ?? 'sha256:' + fakeSha(algoId + ver),
    weightsHash: v.weightsHash ?? '',
    evaluatorVersion: b.evaluatorVersion,
    params: { batch_size: taskOfBench[benchId] === 'object-detection' ? 8 : 32, input_size: taskOfBench[benchId] === 'object-detection' ? 640 : 224, score_thresh: 0.001, fp16: true, seed: 42 },
    hardware: 'NVIDIA RTX 4060 Laptop (8GB) · i9-13900H · CUDA 12.4',
    durationSec: dur,
    peakGpuMemGB: m.peak_mem_gb,
    latencyMs: m.latency_ms,
    isLatestValid: latest && status === 'succeeded',
    logs: [
      `[scheduler] 任务入队，声明显存 ${v.gpuMem} GB`,
      ...(status === 'queued' ? ['[scheduler] 等待 GPU 资源（当前显存余量不足）'] : [`[scheduler] 准入通过，启动容器 ${(v.imageDigest ?? '').slice(0, 19)}…`, '[runner] mode=batch, 只读挂载测试集 images/（不挂载 labels.csv）', '[runner] load() 完成，用时 4.2s']),
      ...(status === 'running' ? ['[runner] 推理进度 63% (3780/6000)'] : []),
      ...(status === 'succeeded' ? ['[runner] 推理完成，写出 predictions.json', `[evaluator] ${b.evaluator}@${b.evaluatorVersion} 读取 labels.csv，在平台侧计算指标`, '[evaluator] 完成，结果已归档'] : []),
      ...(status === 'failed' ? ['[runner] 推理进度 41%', '[runner] CUDA out of memory. Tried to allocate 1.20 GiB', '[scheduler] 容器退出 code=1，任务失败'] : []),
    ],
    error: status === 'failed' ? 'CUDA out of memory：实际显存占用超出 algo.yaml 声明值，请调大 gpu_mem 或减小 batch_size。' : undefined,
    ...extra,
  })
}

// ---- 已完成的评测（含历史版本） ----
push('defect-cls-v3', 'vision-lab/resnet50-defect', 'v1.2.0', 'succeeded', 150, true)
push('defect-cls-v3', 'vision-lab/resnet50-defect', 'v1.1.0', 'succeeded', 210, true)
push('defect-cls-v3', 'vision-lab/efficientnet-b3-defect', 'v2.0.0', 'succeeded', 180, true)
push('defect-cls-v3', 'vision-lab/efficientnet-b3-defect', 'v1.0.0', 'succeeded', 200, true)
push('defect-cls-v3', 'vision-lab/vit-small-defect', 'v0.2.0', 'succeeded', 90, true)
push('defect-cls-v3', 'univ-cvlab/convnext-t-defect', 'v1.0.0', 'succeeded', 60, true)
push('defect-cls-v3', 'vision-lab/mobilenetv3-defect', 'v1.0.0', 'succeeded', 220, true)
push('street-det-v4', 'vision-lab/yolo-lite-s', 'v3.1.0', 'succeeded', 40, true)
push('street-det-v4', 'vision-lab/yolo-lite-s', 'v3.0.0', 'succeeded', 120, true)
push('street-det-v4', 'vision-lab/rtdetr-r18', 'v1.0.0', 'succeeded', 100, true)
push('street-det-v4', 'vision-lab/faster-rcnn-r50-fpn', 'v1.0.0', 'succeeded', 96, true)
push('street-det-v4', 'partner-xyz/xy-det-tiny', 'v1.0.0', 'succeeded', 30, true)
push('street-det-v4', 'vision-lab/rtdetr-r18', 'v1.0.0', 'succeeded', 130, false) // 被更新结果覆盖
push('traffic-det-small', 'smart-city/yolo-lite-n-traffic', 'v2.2.0', 'succeeded', 20, true)
push('traffic-det-small', 'smart-city/yolo-lite-n-traffic', 'v2.1.0', 'succeeded', 70, true)
push('traffic-det-small', 'deepsee/tiled-small-det', 'v1.0.0', 'succeeded', 26, true)
push('traffic-det-small', 'vision-lab/yolo-lite-s', 'v3.1.0', 'succeeded', 18, true)
push('road-seg-v2', 'vision-lab/unet-r34-road', 'v1.1.0', 'succeeded', 300, true)
push('road-seg-v2', 'vision-lab/deeplabv3plus-r50', 'v1.0.0', 'succeeded', 280, true)
push('road-seg-v2', 'vision-lab/segformer-b2', 'v1.0.0', 'succeeded', 140, true)
push('road-seg-v2', 'smart-city/bisenet-v2-road', 'v1.0.0', 'succeeded', 260, true)
push('road-seg-v2', 'partner-xyz/xy-seg-lite', 'v1.0.0', 'succeeded', 90, true)
push('traffic-det-small', 'partner-xyz/xy-det-tiny', 'v1.0.0', 'succeeded', 28, true)
push('nuclei-seg-v2', 'medical-ai/mask-rcnn-nuclei', 'v1.0.0', 'succeeded', 900, true)
push('nuclei-seg-v2', 'medical-ai/star-nuclei-net', 'v1.0.0', 'succeeded', 860, true)
push('vibration-fault-v3', 'signal-team/fft-envelope-svm', 'v2.0.0', 'succeeded', 320, true)
push('vibration-fault-v3', 'signal-team/fft-envelope-svm', 'v1.0.0', 'succeeded', 400, true)
push('vibration-fault-v3', 'signal-team/cnn1d-fault', 'v1.0.0', 'succeeded', 310, true)
// ---- 历史评测：同一算法版本 × 基准的早期结果，已被上面的最新结果覆盖（不上榜） ----
const history: [string, string, string][] = [
  ['defect-cls-v3', 'vision-lab/resnet50-defect', 'v1.1.0'],
  ['defect-cls-v3', 'vision-lab/efficientnet-b3-defect', 'v1.0.0'],
  ['defect-cls-v3', 'vision-lab/mobilenetv3-defect', 'v1.0.0'],
  ['street-det-v4', 'vision-lab/yolo-lite-s', 'v3.0.0'],
  ['street-det-v4', 'vision-lab/faster-rcnn-r50-fpn', 'v1.0.0'],
  ['road-seg-v2', 'vision-lab/unet-r34-road', 'v1.1.0'],
  ['road-seg-v2', 'vision-lab/deeplabv3plus-r50', 'v1.0.0'],
  ['road-seg-v2', 'smart-city/bisenet-v2-road', 'v1.0.0'],
  ['traffic-det-small', 'smart-city/yolo-lite-n-traffic', 'v2.1.0'],
  ['vibration-fault-v3', 'signal-team/fft-envelope-svm', 'v1.0.0'],
  ['vibration-fault-v3', 'signal-team/cnn1d-fault', 'v1.0.0'],
  ['nuclei-seg-v2', 'medical-ai/mask-rcnn-nuclei', 'v1.0.0'],
]
history.forEach(([b, a, v], i) => {
  const hours = 330 + ((i * 53) % 370) // 约 14–29 天前
  push(b, a, v, i % 6 === 5 ? 'failed' : 'succeeded', hours, false)
})

// ---- 进行中 / 排队 / 失败 ----
push('street-det-v4', 'deepsee/tiled-small-det', 'v1.0.0', 'running', 0.3, false)
push('road-seg-v2', 'vision-lab/unet-r34-road', 'v1.0.0', 'queued', 0.2, false)
push('defect-cls-v3', 'vision-lab/resnet50-defect', 'v1.0.0', 'queued', 0.1, false)
push('street-det-v4', 'vision-lab/faster-rcnn-r50-fpn', 'v1.0.0', 'failed', 5, false)
push('road-seg-v2', 'vision-lab/deeplabv3plus-r50', 'v1.0.0', 'canceled', 48, false)

export const evalRuns = runs

// 回填算法的评测次数
for (const a of algorithms) a.evalCount = runs.filter((r) => r.algorithmId === a.id).length
