<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TocItem } from '@/utils/markdown'

/**
 * 悬浮式迷你文档大纲：
 * 仅在左侧边缘显示一列短横线刻度（不占据正文布局、不显示标题名称），滚动时高亮当前章节，点击跳转。
 */
const props = defineProps<{ items: TocItem[] }>()
const active = ref('')
/** 点击跳转的目标：页面已滚到底、标题无法再到达顶部时，仍保持高亮该项 */
let pinned = ''
let pinnedAt = 0 // 平滑滚动期间不清除点击目标

function update() {
  // 当前章节 = 最后一个顶部进入视口上方 40% 区域的标题（页面较短时靠后的章节也能被选中）
  const line = Math.max(120, window.innerHeight * 0.4)
  let cur = props.items[0]?.id ?? ''
  for (const it of props.items) {
    const el = document.getElementById(it.id)
    if (el && el.getBoundingClientRect().top <= line) cur = it.id
  }
  const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4
  if (atBottom && pinned) {
    const el = document.getElementById(pinned)
    const top = el?.getBoundingClientRect().top ?? Infinity
    if (top > 0 && top < window.innerHeight) cur = pinned
  } else if (!atBottom && Date.now() - pinnedAt > 1200) pinned = ''
  active.value = cur
}

// 用短定时器节流（requestAnimationFrame 在后台页面会暂停）
let timer: ReturnType<typeof setTimeout> | undefined
const onScroll = () => {
  if (timer) return
  timer = setTimeout(() => {
    timer = undefined
    update()
  }, 60)
}
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  nextTick(update)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  if (timer) clearTimeout(timer)
})
watch(() => props.items, () => nextTick(update))

function go(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  pinned = id
  pinnedAt = Date.now()
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 80, behavior: 'smooth' })
  active.value = id
}
</script>

<template>
  <nav
    v-if="items.length"
    aria-label="文档大纲"
    class="fixed top-1/2 left-[max(0.5rem,calc(50%-744px))] z-30 hidden -translate-y-1/2 lg:block"
  >
    <ul class="no-scrollbar flex max-h-[70vh] flex-col items-start overflow-y-auto py-1">
      <li v-for="it in items" :key="it.id">
        <a
          :href="`#${it.id}`"
          :aria-label="it.text"
          :aria-current="active === it.id ? 'location' : undefined"
          class="group flex items-center py-1.5 pr-2"
          @click.prevent="go(it.id)"
        >
          <span
            class="block rounded-full transition-all duration-200"
            :class="[
              active === it.id
                ? 'h-[2.5px] bg-gray-900 dark:bg-white'
                : 'h-[2px] bg-gray-300 group-hover:bg-gray-500 dark:bg-gray-700 dark:group-hover:bg-gray-400',
              it.depth === 3
                ? active === it.id
                  ? 'w-3.5'
                  : 'w-2.5'
                : active === it.id
                  ? 'w-5'
                  : 'w-4',
            ]"
          />
        </a>
      </li>
    </ul>
  </nav>
</template>
