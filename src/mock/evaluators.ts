import type { Evaluator } from '@/types'

/** 平台评测器目录：包含内置标准评测器与自定义业务评测器 */
export const evaluators: Evaluator[] = [
  {
    id: 'pytorch-cls-evaluator',
    name: '图像分类标准评测器',
    version: 'v1.2.0',
    kind: 'builtin',
    task: 'image-classification',
    status: 'ready',
    description: '面向单标签图像分类任务（如猫狗识别），在隐藏测试集上执行批量推理并计算准确率、Macro F1、精确率与召回率。',
    entrypoint: 'backend/model_registry.py:evaluate_version_on_test',
    runtime: 'Python 3.12 · PyTorch 2.6+cu124 · CUDA 12.4',
    supportedMetrics: [
      { key: 'top1', label: '准确率', higherIsBetter: true, unit: '%', primary: true },
      { key: 'f1', label: 'Macro F1', higherIsBetter: true, unit: '%' },
      { key: 'precision', label: '精确率', higherIsBetter: true, unit: '%' },
      { key: 'recall', label: '召回率', higherIsBetter: true, unit: '%' },
    ],
    config: [
      { key: 'batch_size', label: '推理批大小', type: 'number', value: 64, desc: 'GPU 批量前向推理的每批图片数' },
      { key: 'amp_fp16', label: '开启混合精度（AMP）', type: 'boolean', value: true, desc: '使用 CUDA FP16 加速测试集推理' },
      { key: 'average', label: '多类平均方式', type: 'select', value: 'macro', options: ['macro', 'micro', 'weighted'], desc: 'Precision / Recall / F1 的跨类别汇总口径' },
      { key: 'zero_division', label: '除零处理值', type: 'select', value: '0', options: ['0', '1'], desc: '某类别无预测样本时的指标填充值' },
    ],
    script: `def evaluate(y_true: list[int], y_pred: list[int], num_classes: int, average: str = "macro"):
    n = max(1, len(y_true))
    top1 = sum(1 for a, b in zip(y_true, y_pred) if a == b) / n * 100
    precs, recs, f1s = [], [], []
    for c in range(num_classes):
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == c and b == c)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != c and b == c)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == c and b != c)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
        precs.append(p); recs.append(r); f1s.append(f1)
    return {
        "top1": round(top1, 2),
        "f1": round(sum(f1s) / len(f1s) * 100, 2),
        "precision": round(sum(precs) / len(precs) * 100, 2),
        "recall": round(sum(recs) / len(recs) * 100, 2),
    }`,
    updatedAt: '2026-11-20T09:30:00+08:00',
    updatedBy: 'admin',
  },
  {
    id: 'dehaze-psnr-ssim-evaluator',
    name: '图像去雾 PSNR/SSIM 评测器',
    version: 'v1.0.0',
    kind: 'builtin',
    task: 'image-dehazing',
    status: 'ready',
    description: '面向图像去雾配对数据集（有雾图 + 清晰真值图），逐张执行真实去雾前向推理并计算峰值信噪比（PSNR）与结构相似度（SSIM），支持按轻/中/浓雾浓度拆分。',
    entrypoint: 'backend/dehaze_registry.py:evaluate_dehaze_on_test',
    runtime: 'Python 3.12 · PyTorch 2.6+cu124 · NumPy',
    supportedMetrics: [
      { key: 'psnr', label: 'PSNR', higherIsBetter: true, unit: 'dB', primary: true },
      { key: 'ssim', label: 'SSIM', higherIsBetter: true, unit: '' },
    ],
    config: [
      { key: 'tile_size', label: '滑窗分块尺寸（0 表示整图）', type: 'number', value: 0, desc: '大图显存不足时可按 tile 滑窗推理' },
      { key: 'amp_fp16', label: '开启混合精度（AMP）', type: 'boolean', value: true, desc: '深度学习模型在 GPU 上启用 FP16 推理' },
    ],
    script: `def evaluate_pair(pred: np.ndarray, gt: np.ndarray):
    mse = float(np.mean((pred - gt) ** 2))
    psnr = 50.0 if mse <= 1e-12 else 10.0 * math.log10(1.0 / mse)
    ssim = compute_ssim(pred, gt)  # 11x11 滑动窗口 RGB 平均
    return {"psnr": round(psnr, 2), "ssim": round(ssim, 4)}`,
    updatedAt: '2026-11-20T10:10:00+08:00',
    updatedBy: 'admin',
  },
  {
    id: 'builtin-coco-detection',
    name: '目标检测 COCO 评测器',
    version: 'v2.0.1',
    kind: 'builtin',
    task: 'object-detection',
    status: 'ready',
    description: '基于标准 COCO 协议评估边界框检测模型，计算 mAP@50:95、mAP@50 以及精确率与召回率，支持无目标负样本误报统计。',
    entrypoint: 'evaluators/coco_detection.py:run_eval',
    runtime: 'Python 3.12 · pycocotools 2.0',
    supportedMetrics: [
      { key: 'map', label: 'mAP@50:95', higherIsBetter: true, unit: '%', primary: true },
      { key: 'map50', label: 'mAP@50', higherIsBetter: true, unit: '%' },
      { key: 'precision', label: '精确率', higherIsBetter: true, unit: '%' },
      { key: 'recall', label: '召回率', higherIsBetter: true, unit: '%' },
    ],
    config: [
      { key: 'iou_range', label: 'IoU 阈值范围', type: 'string', value: '0.50:0.95:0.05', desc: '计算 mAP 时的交并比采样区间' },
      { key: 'conf_threshold', label: '默认置信度阈值', type: 'number', value: 0.25, desc: '低于该阈值的预测框不计入统计' },
      { key: 'max_dets', label: '单图最大检出数', type: 'number', value: 100, desc: '每张图片保留的最高置信度框上限' },
    ],
    script: `def run_eval(gt_boxes, pred_boxes, iou_range="0.50:0.95:0.05", conf_threshold=0.25, max_dets=100):
    # 过滤低置信度框并按 COCO 协议逐阈值匹配 IoU
    filtered = [b for b in pred_boxes if b["score"] >= conf_threshold][:max_dets]
    return compute_coco_metrics(gt_boxes, filtered, iou_range=iou_range)`,
    updatedAt: '2026-11-18T11:00:00+08:00',
    updatedBy: 'admin',
  },
  {
    id: 'builtin-semantic-seg',
    name: '语义分割像素评测器',
    version: 'v2.0.1',
    kind: 'builtin',
    task: 'semantic-segmentation',
    status: 'ready',
    description: '逐像素对比预测掩码与真值 masks/ PNG，计算平均交并比（mIoU）与像素准确率。',
    entrypoint: 'evaluators/semantic_seg.py:run_eval',
    runtime: 'Python 3.12 · NumPy 2.x',
    supportedMetrics: [
      { key: 'miou', label: 'mIoU', higherIsBetter: true, unit: '%', primary: true },
      { key: 'pixel_acc', label: '像素准确率', higherIsBetter: true, unit: '%' },
    ],
    config: [
      { key: 'ignore_index', label: '忽略像素值', type: 'number', value: 255, desc: '真值掩码中不参与计分的像素标签' },
      { key: 'include_background', label: '计入背景类', type: 'boolean', value: true, desc: 'mIoU 汇总时是否包含类别 0（背景）' },
    ],
    script: `def run_eval(gt_masks, pred_masks, ignore_index=255, include_background=True):
    cm = confusion_matrix(gt_masks, pred_masks, ignore_index=ignore_index)
    ious = compute_iou_per_class(cm)
    if not include_background:
        ious = ious[1:]
    return {"miou": round(float(ious.mean()) * 100, 2), "pixel_acc": round(float(cm.diagonal().sum() / cm.sum()) * 100, 2)}`,
    updatedAt: '2026-11-18T11:00:00+08:00',
    updatedBy: 'admin',
  },
  {
    id: 'custom-meter-ocr',
    name: '巡检表计与数显 OCR 评测器',
    version: 'v0.9.0',
    kind: 'custom',
    task: 'ocr',
    status: 'uninitialized',
    description: '针对新能源场站红色 LED 数显、避雷器电流表与放电计数等巡检读数任务，支持前导零严格匹配与数值误差容忍度配置。',
    entrypoint: 'evaluators/meter_ocr.py:evaluate_readings',
    runtime: 'Python 3.12 · 标准库',
    supportedMetrics: [
      { key: 'exact_match', label: '整串完全匹配率', higherIsBetter: true, unit: '%', primary: true },
      { key: 'tol_acc', label: '容差内准确率', higherIsBetter: true, unit: '%' },
      { key: 'mae', label: '数值平均绝对误差', higherIsBetter: false },
    ],
    config: [
      { key: 'keep_leading_zeros', label: '严格校验前导零', type: 'boolean', value: true, desc: '关闭时 "04" 与 "4" 视为一致' },
      { key: 'numeric_tolerance', label: '数值容差阈值', type: 'number', value: 0.05, desc: '指针表盘读数允许的最大绝对偏差' },
      { key: 'null_as_error', label: '空结果记为错误', type: 'boolean', value: true, desc: '识别返回 null 时直接计为失败，不补 0' },
    ],
    script: `def evaluate_readings(gt_rows, pred_rows, keep_leading_zeros=True, numeric_tolerance=0.05):
    exact = tol = 0
    abs_errs = []
    for gt, pred in zip(gt_rows, pred_rows):
        if pred is None:
            continue
        if (str(gt) == str(pred)) if keep_leading_zeros else (str(gt).lstrip("0") == str(pred).lstrip("0")):
            exact += 1
        try:
            err = abs(float(gt) - float(pred))
            abs_errs.append(err)
            if err <= numeric_tolerance:
                tol += 1
        except ValueError:
            pass
    n = max(1, len(gt_rows))
    return {"exact_match": round(exact / n * 100, 2), "tol_acc": round(tol / n * 100, 2), "mae": round(sum(abs_errs) / max(1, len(abs_errs)), 4)}`,
    updatedAt: '2026-11-19T16:00:00+08:00',
    updatedBy: 'admin',
  },
  {
    id: 'custom-power-forecast',
    name: '新能源功率预测考核评测器',
    version: 'v0.5.0',
    kind: 'custom',
    task: 'power-forecast',
    status: 'ready',
    description: '按新能源场站装机容量归一化计算功率预测 RMSE、MAE 与考核准确率，适用于风电/光伏短期及超短期功率预测算法。',
    entrypoint: 'evaluators/power_forecast.py:evaluate_power',
    runtime: 'Python 3.12 · NumPy 2.x',
    supportedMetrics: [
      { key: 'accuracy_rate', label: '预测准确率', higherIsBetter: true, unit: '%', primary: true },
      { key: 'rmse', label: '归一化 RMSE', higherIsBetter: false, unit: '%' },
      { key: 'mae', label: '归一化 MAE', higherIsBetter: false, unit: '%' },
    ],
    config: [
      { key: 'capacity_mw', label: '装机容量（MW）', type: 'number', value: 100, desc: '用于归一化功率误差的场站额定容量' },
      { key: 'window_hours', label: '考核时间窗口（h）', type: 'number', value: 24, desc: '单次预测滚动考核时长' },
    ],
    script: `def evaluate_power(y_true, y_pred, capacity_mw=100.0):
    n = max(1, len(y_true))
    rmse = (sum(((a - b) / capacity_mw) ** 2 for a, b in zip(y_true, y_pred)) / n) ** 0.5
    mae = sum(abs(a - b) / capacity_mw for a, b in zip(y_true, y_pred)) / n
    return {"accuracy_rate": round(max(0.0, (1.0 - rmse) * 100), 2), "rmse": round(rmse * 100, 2), "mae": round(mae * 100, 2)}`,
    updatedAt: '2026-11-20T10:30:00+08:00',
    updatedBy: 'admin',
  },
]
