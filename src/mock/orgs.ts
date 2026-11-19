import type { Org, User } from '@/types'

/**
 * 组织分两类：
 * - team：平台内部命名空间，存放数据集与基线算法（由管理员维护，不对应用户归属）
 * - vendor：算法厂商；厂商账号必须归属某个厂商，管理员与演示账号不属于任何组织
 */
export const orgs: Org[] = [
  { id: 'Admin', name: 'Admin', displayName: '管理员上传', description: '管理员上传的数据集统一放在此命名空间。', color: '#111827', members: 0, kind: 'team' },
  { id: 'vision-lab', name: 'vision-lab', displayName: '视觉算法实验室', description: '平台内部团队，维护通用视觉数据集与基线算法。', color: '#4f46e5', members: 4, kind: 'team' },
  { id: 'smart-city', name: 'smart-city', displayName: '智慧城市组', description: '平台内部团队，维护交通场景数据集与基线。', color: '#0891b2', members: 2, kind: 'team' },
  { id: 'medical-ai', name: 'medical-ai', displayName: '医学影像组', description: '平台内部团队，病理与医学影像数据集。', color: '#db2777', members: 1, kind: 'team' },
  { id: 'retail-ai', name: 'retail-ai', displayName: '零售视觉组', description: '平台内部团队，商品识别数据集。', color: '#ea580c', members: 1, kind: 'team' },
  { id: 'signal-team', name: 'signal-team', displayName: '信号与优化组', description: '平台内部团队，振动信号与调度优化。', color: '#65a30d', members: 1, kind: 'team' },
  { id: 'partner-xyz', name: 'partner-xyz', displayName: '星衍科技', enName: 'Xingyan Technology', description: '算法厂商：轻量化检测与分割方案。', color: '#7c3aed', members: 2, kind: 'vendor' },
  { id: 'univ-cvlab', name: 'univ-cvlab', displayName: '启明视觉', enName: 'Qiming Vision', description: '算法厂商：工业质检方案。', color: '#9333ea', members: 1, kind: 'vendor' },
  { id: 'deepsee', name: 'deepsee', displayName: '深鉴智能', enName: 'DeepSee AI', description: '算法厂商：交通场景小目标检测。', color: '#be123c', members: 1, kind: 'vendor' },
]

export const users: User[] = [
  { id: 'u1', username: 'admin', displayName: '平台管理员', email: 'admin@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-06-01T09:00:00+08:00', lastLoginAt: '2026-11-19T09:12:00+08:00' },
  { id: 'u2', username: 'chen.wei', displayName: '陈伟', email: 'chen.wei@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-06-03T10:00:00+08:00', lastLoginAt: '2026-11-19T08:40:00+08:00' },
  { id: 'u3', username: 'li.na', displayName: '李娜', email: 'li.na@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-07-11T10:00:00+08:00', lastLoginAt: '2026-11-18T19:20:00+08:00' },
  { id: 'u4', username: 'zhao.lei', displayName: '赵磊', email: 'zhao.lei@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-08-02T10:00:00+08:00', lastLoginAt: '2026-11-17T15:00:00+08:00' },
  { id: 'u5', username: 'wang.fang', displayName: '王芳', email: 'wang.fang@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-09-15T10:00:00+08:00', lastLoginAt: '2026-11-19T10:02:00+08:00' },
  { id: 'u6', username: 'sun.yu', displayName: '孙宇', email: 'sun.yu@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-10-01T10:00:00+08:00', lastLoginAt: '2026-11-12T11:00:00+08:00' },
  { id: 'u7', username: 'zhou.min', displayName: '周敏', email: 'zhou.min@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-11-20T10:00:00+08:00', lastLoginAt: '2026-11-15T14:00:00+08:00' },
  { id: 'u8', username: 'wu.hao', displayName: '吴昊', email: 'wu.hao@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2025-06-20T10:00:00+08:00', lastLoginAt: '2026-11-18T09:00:00+08:00' },
  { id: 'u20', username: 'demo', displayName: '演示账号', email: 'demo@algohub.local', role: 'demo', orgId: null, active: true, createdAt: '2026-10-01T10:00:00+08:00', lastLoginAt: '2026-11-18T16:00:00+08:00' },
  { id: 'u21', username: 'demo.expo', displayName: '展会演示', email: 'expo@algohub.local', role: 'demo', orgId: null, active: true, createdAt: '2026-09-01T10:00:00+08:00', lastLoginAt: '2026-10-22T10:00:00+08:00' },
  { id: 'u9', username: 'xy.liu', displayName: '刘洋（星衍）', email: 'liu@xingyan.example', role: 'vendor', orgId: 'partner-xyz', active: true, createdAt: '2026-08-01T10:00:00+08:00', lastLoginAt: '2026-11-18T21:00:00+08:00' },
  { id: 'u13', username: 'xy.chen', displayName: '陈静（星衍）', email: 'chen@xingyan.example', role: 'vendor', orgId: 'partner-xyz', active: true, createdAt: '2026-08-05T10:00:00+08:00', lastLoginAt: '2026-11-16T10:00:00+08:00' },
  { id: 'u10', username: 'qm.he', displayName: '何静（启明）', email: 'he@qiming.example', role: 'vendor', orgId: 'univ-cvlab', active: true, createdAt: '2026-09-10T10:00:00+08:00', lastLoginAt: '2026-11-16T16:30:00+08:00' },
  { id: 'u14', username: 'ds.zhang', displayName: '张弛（深鉴）', email: 'zhang@deepsee.example', role: 'vendor', orgId: 'deepsee', active: true, createdAt: '2026-10-08T10:00:00+08:00', lastLoginAt: '2026-11-18T11:00:00+08:00' },
  { id: 'u12', username: 'xy.old', displayName: '已停用厂商账号', email: 'old@xingyan.example', role: 'vendor', orgId: 'partner-xyz', active: false, createdAt: '2026-01-10T10:00:00+08:00', lastLoginAt: '2026-03-01T10:00:00+08:00' },
]

/** 身份切换器中每个角色对应的演示身份 */
export const demoIdentity: Record<string, string> = {
  admin: 'u1',
  demo: 'u20',
  vendor: 'u9',
}
