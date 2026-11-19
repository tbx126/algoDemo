import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { bare: true } },
    { path: '/algorithms', name: 'algorithms', component: () => import('@/views/algo/AlgoListView.vue') },
    { path: '/algorithms/new', name: 'algo-new', component: () => import('@/views/create/NewAlgoView.vue') },
    { path: '/algorithms/:org/:name', name: 'algo', component: () => import('@/views/algo/AlgoDetailView.vue') },
    { path: '/datasets', name: 'datasets', component: () => import('@/views/dataset/DatasetListView.vue') },
    { path: '/datasets/new', name: 'dataset-new', component: () => import('@/views/create/NewDatasetView.vue') },
    { path: '/datasets/:org/:name', name: 'dataset', component: () => import('@/views/dataset/DatasetDetailView.vue') },
    { path: '/benchmarks', name: 'benchmarks', component: () => import('@/views/benchmark/BenchmarkListView.vue') },
    { path: '/benchmarks/new', name: 'benchmark-new', component: () => import('@/views/create/NewBenchmarkView.vue') },
    { path: '/benchmarks/:id', name: 'benchmark', component: () => import('@/views/benchmark/BenchmarkDetailView.vue') },
    { path: '/evals', name: 'evals', component: () => import('@/views/eval/EvalListView.vue') },
    { path: '/evals/new', name: 'eval-new', component: () => import('@/views/eval/NewEvalView.vue') },
    { path: '/evals/:id', name: 'eval', component: () => import('@/views/eval/EvalDetailView.vue') },
    { path: '/vendors/new', name: 'vendor-new', component: () => import('@/views/create/NewVendorView.vue') },
    { path: '/orgs/:id', name: 'org', component: () => import('@/views/org/OrgView.vue') },
    { path: '/admin/:tab?', name: 'admin', component: () => import('@/views/admin/AdminView.vue') },
    { path: '/:pathMatch(.*)*', name: '404', component: () => import('@/views/NotFoundView.vue') },
  ],
})
