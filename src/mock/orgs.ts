import type { Org, User } from '@/types'
import { VENDOR_ID } from './algorithms'

/**
 * 组织分两类：
 * - team：平台命名空间（Admin：管理员上传的数据集）
 * - vendor：算法厂商；厂商账号必须归属某个厂商，管理员与演示账号不属于任何组织
 *
 * 厂商信息来自《六项巡检算法入库材料》01 厂商材料与算法基础信息申报表（2026-11-18）。
 */
export const orgs: Org[] = [
  { id: 'Admin', name: 'Admin', displayName: '管理员上传', description: '管理员上传的数据集统一放在此命名空间。', color: '#111827', members: 0, kind: 'team' },
  {
    id: VENDOR_ID,
    name: VENDOR_ID,
    displayName: '锋云深蓝',
    description: '新能源场站设备巡检识别算法（六项可见光巡检算法）。',
    color: '#0f766e',
    members: 1,
    kind: 'vendor',
    profile: {
      company: {
        fullName: '浙江锋云深蓝科技有限公司',
        creditCode: '91330110MAG1M9L48K',
        type: '其他有限责任公司',
        foundedAt: '2025-10-23',
        capital: '人民币1000万元',
        status: '开业',
        address: '浙江省杭州市余杭区仓前街道高教路199号1幢304室',
        licenseFile: '1 营业执照-公章.PDF',
      },
      contact: { phone: '13123818169', email: 'jin_cw@hdec.com', website: '/', officeAddress: '杭州市拱墅区潮王路22号' },
      liaison: { name: '张蕾蕾', title: '待填写', phone: '18767120868' },
      // A02 质量管理体系认证证书：证书号 41626Q00805R001，浙江标服认证有限公司，有效至 2029-09-28
      qualification: { file: '质量管理体系认证证书（41626Q00805R001）.pdf', noQualification: false },
      // A03 软件著作权、A04 专利及其他知识产权：材料中未提供
      createdAt: '2026-11-18T10:00:00+08:00',
    },
  },
]

export const users: User[] = [
  { id: 'u1', username: 'admin', displayName: '平台管理员', email: 'admin@algohub.local', role: 'admin', orgId: null, active: true, createdAt: '2026-11-18T09:00:00+08:00', lastLoginAt: '2026-11-20T09:00:00+08:00' },
  { id: 'u4', username: 'regional', displayName: '区域侧账号', email: 'regional@algohub.local', role: 'regional', orgId: null, active: true, createdAt: '2026-11-20T15:25:00+08:00', lastLoginAt: '' },
  { id: 'u2', username: 'demo', displayName: '演示账号', email: 'demo@algohub.local', role: 'demo', orgId: null, active: true, createdAt: '2026-11-18T09:00:00+08:00', lastLoginAt: '' },
  { id: 'u3', username: 'zhang.ll', displayName: '张蕾蕾（锋云深蓝）', email: 'zhang_ll8@hdec.com', role: 'vendor', orgId: VENDOR_ID, active: true, createdAt: '2026-11-18T10:00:00+08:00', lastLoginAt: '' },
]

/** 身份切换器中每个角色对应的演示身份 */
export const demoIdentity: Record<string, string> = {
  admin: 'u1',
  regional: 'u4',
  demo: 'u2',
  vendor: 'u3',
}
