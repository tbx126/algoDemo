import type { Benchmark } from '@/types'

/** 评测基准：绑定测试集具体版本，确保评测结果可复现 */
export const benchmarks: Benchmark[] = [
  {
    id: 'cat-dog-cls-bench',
    name: 'cat-dog-cls-bench',
    displayName: '猫狗图像识别评测基准',
    description: '基于 Admin/cat-dog-dataset 测试集 v1.0（2,000 张图片），评估猫狗二分类算法的 Top-1 准确率与 Macro F1。',
    task: 'image-classification',
    datasetId: 'Admin/cat-dog-dataset',
    datasetVersion: 'v1.0',
    split: 'test',
    evaluator: 'algohub-cls-eval',
    evaluatorVersion: 'v1.2.0',
    metrics: [
      { key: 'top1', label: 'Top-1 准确率', higherIsBetter: true, unit: '%', primary: true },
      { key: 'f1', label: 'Macro F1', higherIsBetter: true, unit: '%' },
      { key: 'precision', label: '精确率', higherIsBetter: true, unit: '%' },
      { key: 'recall', label: '召回率', higherIsBetter: true, unit: '%' },
    ],
    createdAt: '2026-11-18T15:30:00+08:00',
    org: 'Admin',
  },
]
