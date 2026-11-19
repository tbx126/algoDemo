/**
 * 程序化生成预览图（不依赖任何外部图片，避免版权与外网依赖）
 * 同一个 seed 总是生成同一张图，并返回“标注”用于叠加显示。
 */
import type { TaskType } from '@/types'
import { rng } from './format'

export const CLASS_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#06b6d4', '#a855f7', '#eab308']

export interface SynthObject {
  cls: number
  x: number
  y: number
  w: number
  h: number
  shape: 'rect' | 'ellipse' | 'tri'
}

export interface SynthScene {
  objects: SynthObject[]
  label: number // 分类任务的图像级标签
}

function hsl(h: number, s: number, l: number) {
  return `hsl(${Math.round(h)} ${Math.round(s)}% ${Math.round(l)}%)`
}

/**
 * 场景布局（纯函数，与画布尺寸无关）：同一 seed 在任何尺寸下得到相同的目标与标签，
 * 因此 labels.csv 中的框与缩略图 / 大图完全一致。
 */
export function sceneLayout(seed: number, task: TaskType, nClasses: number): SynthScene {
  const ro = rng(seed * 31 + 7)
  const n = Math.max(1, nClasses)
  if (task === 'signal-processing' || task === 'optimization') return { objects: [], label: Math.floor(ro() * n) }
  const nObj = task === 'image-classification' ? 1 : task === 'instance-segmentation' ? 10 + Math.floor(ro() * 8) : 3 + Math.floor(ro() * 5)
  const objects: SynthObject[] = []
  for (let i = 0; i < nObj; i++) {
    const small = task === 'instance-segmentation'
    const w = small ? 0.05 + ro() * 0.06 : task === 'image-classification' ? 0.35 + ro() * 0.3 : 0.08 + ro() * 0.22
    const h = small ? w * (0.8 + ro() * 0.4) : task === 'image-classification' ? 0.35 + ro() * 0.3 : 0.08 + ro() * 0.25
    objects.push({
      cls: Math.floor(ro() * n),
      x: ro() * (1 - w),
      y: task === 'image-classification' ? (1 - h) / 2 : 0.25 + ro() * (0.72 - h),
      w,
      h,
      shape: (['rect', 'ellipse', 'tri'] as const)[Math.floor(ro() * 3)],
    })
  }
  return { objects, label: objects[0]?.cls ?? 0 }
}

export function drawScene(ctx: CanvasRenderingContext2D, W: number, H: number, seed: number, task: TaskType, nClasses: number): SynthScene {
  const r = rng(seed)
  const hue = r() * 360
  ctx.clearRect(0, 0, W, H)

  if (task === 'signal-processing') {
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, W, H)
    ctx.strokeStyle = 'rgba(148,163,184,.15)'
    for (let x = 0; x < W; x += W / 10) {
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, H)
      ctx.stroke()
    }
    const f1 = 2 + r() * 6
    const f2 = 15 + r() * 30
    const imp = r() * 0.6
    ctx.strokeStyle = hsl(hue, 80, 65)
    ctx.lineWidth = 1.2
    ctx.beginPath()
    for (let x = 0; x < W; x++) {
      const t = x / W
      let y = Math.sin(t * f1 * Math.PI * 2) * 0.35 + Math.sin(t * f2 * Math.PI * 2) * 0.12 + (r() - 0.5) * 0.12
      if (imp > 0.3 && Math.abs(((t * 7) % 1) - 0.5) < 0.01) y += 0.6
      const py = H / 2 - y * H * 0.4
      if (x === 0) ctx.moveTo(x, py)
      else ctx.lineTo(x, py)
    }
    ctx.stroke()
    return sceneLayout(seed, task, nClasses)
  }

  if (task === 'optimization') {
    ctx.fillStyle = '#f8fafc'
    ctx.fillRect(0, 0, W, H)
    const pts = Array.from({ length: 16 }, () => [W * (0.08 + r() * 0.84), H * (0.08 + r() * 0.84)])
    const depot = [W / 2, H / 2]
    const routes = [pts.slice(0, 5), pts.slice(5, 11), pts.slice(11)]
    routes.forEach((rt, i) => {
      ctx.strokeStyle = CLASS_COLORS[i + 3]
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(depot[0], depot[1])
      rt.forEach((p) => ctx.lineTo(p[0], p[1]))
      ctx.lineTo(depot[0], depot[1])
      ctx.stroke()
    })
    pts.forEach((p) => {
      ctx.fillStyle = '#334155'
      ctx.beginPath()
      ctx.arc(p[0], p[1], 3.5, 0, Math.PI * 2)
      ctx.fill()
    })
    ctx.fillStyle = '#dc2626'
    ctx.fillRect(depot[0] - 5, depot[1] - 5, 10, 10)
    return sceneLayout(seed, task, nClasses)
  }

  // 背景：渐变 + “地面”
  const g = ctx.createLinearGradient(0, 0, 0, H)
  g.addColorStop(0, hsl(hue, 30, 78))
  g.addColorStop(0.55, hsl(hue + 20, 25, 62))
  g.addColorStop(1, hsl(hue + 40, 18, 42))
  ctx.fillStyle = g
  ctx.fillRect(0, 0, W, H)

  // 纹理噪声
  const img = ctx.getImageData(0, 0, W, H)
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (r() - 0.5) * 22
    img.data[i] += n
    img.data[i + 1] += n
    img.data[i + 2] += n
  }
  ctx.putImageData(img, 0, 0)

  // 远景色块
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = hsl(hue + r() * 60, 15, 40 + r() * 30)
    ctx.globalAlpha = 0.35
    ctx.fillRect(r() * W, H * (0.2 + r() * 0.3), W * (0.1 + r() * 0.3), H * (0.2 + r() * 0.4))
  }
  ctx.globalAlpha = 1

  const scene = sceneLayout(seed, task, nClasses)
  const objects = scene.objects
  for (const o of objects) {
    const small = task === 'instance-segmentation'
    const x = o.x * W
    const y = o.y * H
    const ww = o.w * W
    const hh = o.h * H
    const og = ctx.createLinearGradient(x, y, x + ww, y + hh)
    const oh = hue + 120 + o.cls * 47
    og.addColorStop(0, hsl(oh, 45, small ? 35 : 58))
    og.addColorStop(1, hsl(oh + 20, 40, small ? 25 : 38))
    ctx.fillStyle = og
    ctx.shadowColor = 'rgba(0,0,0,.25)'
    ctx.shadowBlur = 6
    ctx.beginPath()
    if (o.shape === 'rect') ctx.roundRect(x, y, ww, hh, Math.min(ww, hh) * 0.15)
    else if (o.shape === 'ellipse') ctx.ellipse(x + ww / 2, y + hh / 2, ww / 2, hh / 2, 0, 0, Math.PI * 2)
    else {
      ctx.moveTo(x + ww / 2, y)
      ctx.lineTo(x + ww, y + hh)
      ctx.lineTo(x, y + hh)
      ctx.closePath()
    }
    ctx.fill()
    ctx.shadowBlur = 0
  }
  // 分类任务：在物体上加“缺陷”纹理
  if (task === 'image-classification') {
    ctx.strokeStyle = 'rgba(20,20,20,.55)'
    ctx.lineWidth = 1.5
    for (let k = 0; k < 3; k++) {
      ctx.beginPath()
      const o = objects[0]
      let px = (o.x + o.w * r()) * W
      let py = (o.y + o.h * r()) * H
      ctx.moveTo(px, py)
      for (let s = 0; s < 6; s++) {
        px += (r() - 0.5) * 24
        py += (r() - 0.5) * 24
        ctx.lineTo(px, py)
      }
      ctx.stroke()
    }
  }
  return scene
}

export function drawAnnotations(ctx: CanvasRenderingContext2D, W: number, H: number, scene: SynthScene, task: TaskType, classes: string[]) {
  ctx.font = `600 ${Math.max(10, Math.round(W / 34))}px Inter, "Microsoft YaHei", sans-serif`
  for (const o of scene.objects) {
    const c = CLASS_COLORS[o.cls % CLASS_COLORS.length]
    const x = o.x * W
    const y = o.y * H
    const w = o.w * W
    const h = o.h * H
    if (task === 'semantic-segmentation' || task === 'instance-segmentation') {
      ctx.fillStyle = c + '88'
      ctx.beginPath()
      if (o.shape === 'rect') ctx.roundRect(x, y, w, h, Math.min(w, h) * 0.15)
      else if (o.shape === 'ellipse') ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2)
      else {
        ctx.moveTo(x + w / 2, y)
        ctx.lineTo(x + w, y + h)
        ctx.lineTo(x, y + h)
        ctx.closePath()
      }
      ctx.fill()
      ctx.strokeStyle = c
      ctx.lineWidth = 1.5
      ctx.stroke()
    } else if (task !== 'image-classification') {
      ctx.strokeStyle = c
      ctx.lineWidth = 2
      ctx.strokeRect(x, y, w, h)
      const t = classes[o.cls] ?? `cls${o.cls}`
      const tw = ctx.measureText(t).width + 8
      const th = Math.max(14, W / 26)
      ctx.fillStyle = c
      ctx.fillRect(x - 1, y - th, tw, th)
      ctx.fillStyle = '#fff'
      ctx.fillText(t, x + 3, y - th * 0.25)
    }
  }
}

/** 生成一张示例图的 dataURL（用于推理组件的“示例图片”） */
export function sampleImageDataUrl(seed: number, task: TaskType, nClasses: number, W = 640, H = 480): string {
  const c = document.createElement('canvas')
  c.width = W
  c.height = H
  const ctx = c.getContext('2d')!
  drawScene(ctx, W, H, seed, task, nClasses)
  return c.toDataURL('image/jpeg', 0.85)
}
