<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TocItem } from '@/utils/markdown'

/**
 * 迷你文档大纲：正文左侧留白处的一列短横线刻度。
 * - 绝对定位在父容器（需 relative，并在左侧留出约 2.5rem 留白）的左边缘，不占据正文宽度
 * - 与正文顶部对齐，滚动时吸顶；不显示标题名称，悬停时以浮层提示
 * - 滚动高亮当前章节，点击平滑跳转
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
  <div v-if="items.length" class="pointer-events-none absolute inset-y-0 left-0 hidden w-6 lg:block">
    <nav aria-label="文档大纲" class="pointer-events-auto sticky top-24">
      <ul class="no-scrollbar flex max-h-[calc(100vh-8rem)] flex-col items-start overflow-y-auto">
        <li v-for="it in items" :key="it.id" class="relative">
          <a
            :href="`#${it.id}`"
            :aria-label="it.text"
            :aria-current="active === it.id ? 'location' : undefined"
            class="group flex h-6 items-center pr-1"
            @click.prevent="go(it.id)"
          >
            <span
              class="block rounded-full transition-all duration-200"
              :class="[
                active === it.id ? 'h-[2.5px] bg-gray-900 dark:bg-white' : 'h-[2px] bg-gray-300 group-hover:bg-gray-500 dark:bg-gray-700 dark:group-hover:bg-gray-400',
                it.depth === 3 ? (active === it.id ? 'w-3.5' : 'w-2.5') : active === it.id ? 'w-5' : 'w-4',
              ]"
            />
            <!-- 悬停才显示的标题浮层 -->
            <span
              class="pointer-events-none invisible absolute top-1/2 left-7 z-30 -translate-y-1/2 rounded-md bg-gray-900 px-2 py-1 text-xs whitespace-nowrap text-white opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100 dark:bg-gray-100 dark:text-gray-900"
              >{{ it.text }}</span
            >
          </a>
        </li>
      </ul>
    </nav>
  </div>
</template>
