import { describe, expect, it } from 'vitest'
import {
  mapBitableRows,
  parseNodeDate,
  UPGRADING_STATUS,
} from '../../packages/server/src/services/tahp/verify-plan-nodes-fetch'

const FIELDS = ['项目名称', 'STR4', 'STR4A', 'FR', 'STR 5']

describe('verify-plan-nodes-fetch parseNodeDate', () => {
  it('空值与 NA 归一为 null', () => {
    expect(parseNodeDate(null)).toBeNull()
    expect(parseNodeDate(undefined)).toBeNull()
    expect(parseNodeDate('')).toBeNull()
    expect(parseNodeDate('  ')).toBeNull()
    expect(parseNodeDate('NA')).toBeNull()
    expect(parseNodeDate('—')).toBeNull()
  })

  it('ISO datetime 取日期部分', () => {
    expect(parseNodeDate('2026-11-16T00:00:00.000+08:00')).toBe('2026/11/16')
    expect(parseNodeDate('2027-01-28T00:00:00.000+08:00')).toBe('2027/01/28')
  })

  it('yyyy/m/d 与 yyyy-m-d 补零', () => {
    expect(parseNodeDate('2027/3/18')).toBe('2027/03/18')
    expect(parseNodeDate('2027/03/18')).toBe('2027/03/18')
    expect(parseNodeDate('2026-9-5')).toBe('2026/09/05')
  })

  it('毫秒时间戳按 UTC+8 取日', () => {
    // 2026-11-16 00:00:00 +08:00
    expect(parseNodeDate(Date.UTC(2026, 10, 15, 16, 0, 0))).toBe('2026/11/16')
  })

  it('美式短日期回退 Date 解析', () => {
    expect(parseNodeDate('9/20/26')).toBe('2026/09/20')
  })

  it('无法解析的文本 → null', () => {
    expect(parseNodeDate('待定')).toBeNull()
  })
})

describe('verify-plan-nodes-fetch mapBitableRows', () => {
  it('映射节点列并补 STR6 null', () => {
    const projects = mapBitableRows(
      [
        ['X6879', '2026-11-16T00:00:00.000+08:00', '2027-01-28T00:00:00.000+08:00', '2027-03-04T00:00:00.000+08:00', '2027/03/18'],
        ['CN6c', '2026-11-16T00:00:00.000+08:00', null, '2027-03-07T00:00:00.000+08:00', '2027/3/18'],
      ],
      FIELDS,
    )
    expect(projects).toHaveLength(2)
    expect(projects[0]).toEqual({
      name: 'X6879',
      status: UPGRADING_STATUS,
      nodes: { STR4: '2026/11/16', STR4A: '2027/01/28', FR: '2027/03/04', STR5: '2027/03/18', STR6: null },
    })
    expect(projects[1].nodes.STR4A).toBeNull()
    expect(projects[1].nodes.STR5).toBe('2027/03/18')
  })

  it('跳过空项目名行', () => {
    const projects = mapBitableRows(
      [
        ['  ', '2026-11-16T00:00:00.000+08:00', null, null, null],
        [null, null, null, null, null],
        ['X6887', '2026-11-16T00:00:00.000+08:00', null, null, 'NA'],
      ],
      FIELDS,
    )
    expect(projects).toHaveLength(1)
    expect(projects[0].name).toBe('X6887')
    expect(projects[0].nodes.STR5).toBeNull()
  })

  it('缺列时对应节点为 null', () => {
    const projects = mapBitableRows([['X1', '2026/11/16']], ['项目名称', 'STR4'])
    expect(projects[0].nodes.STR4).toBe('2026/11/16')
    expect(projects[0].nodes.FR).toBeNull()
  })
})
