<template>
  <footer class="mt-16 border-t border-gray-100 py-8 text-sm text-gray-500 dark:border-gray-800">
    <div class="container-page flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
      <div class="flex items-center gap-2">
        <img src="/logo.svg" alt="" class="size-5 opacity-80" />
        <span>AlgoHub · 统一的算法与数据集评测平台</span>
      </div>
      <div class="flex flex-wrap gap-x-5 gap-y-1">
        <RouterLink to="/algorithms" class="hover:text-gray-900 dark:hover:text-white">算法</RouterLink>
        <RouterLink to="/datasets" class="hover:text-gray-900 dark:hover:text-white">数据集</RouterLink>
        <RouterLink to="/benchmarks" class="hover:text-gray-900 dark:hover:text-white">评测基准</RouterLink>
        <span class="text-gray-400">前端原型 · 数据均为模拟</span>
      </div>
    </div>
  </footer>
</template>
