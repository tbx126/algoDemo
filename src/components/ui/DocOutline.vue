<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { TocItem } from '@/utils/markdown'

/** 文档大纲：一条一条列出标题，滚动时高亮当前所在章节，点击跳转 */
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
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
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
  <nav v-if="items.length" aria-label="文档大纲" class="text-sm">
    <p class="mb-2 text-xs font-medium tracking-wide text-gray-400">大纲</p>
    <ul class="scroll-thin max-h-[calc(100vh-8rem)] overflow-y-auto border-l border-gray-200 dark:border-gray-800">
      <li v-for="it in items" :key="it.id">
        <a
          :href="`#${it.id}`"
          class="-ml-px block border-l-2 py-1 pr-2 leading-snug transition-colors"
          :class="[
            it.depth === 3 ? 'pl-6 text-[13px]' : 'pl-3',
            active === it.id ? 'border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-800 dark:hover:border-gray-600 dark:hover:text-gray-200',
          ]"
          :aria-current="active === it.id ? 'location' : undefined"
          @click.prevent="go(it.id)"
          >{{ it.text }}</a
        >
      </li>
    </ul>
  </nav>
</template>
