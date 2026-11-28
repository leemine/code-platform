export const useCase = {
  id: 'UC-034-v1',
  title: '还款尾差处理（测试用例）',
  body: '前提：客户有两笔未结清借据。操作：登记一笔包含 0.01 元尾差的还款。预期：差额归入本金余额最大的借据，分摊金额与总金额一致。',
}
export const asset = {
  revisionId: 'interest-allocation-v2',
  sectionId: 'rounding-remainder',
  title: '现行利息分摊（测试资产）',
  body: '当两笔或以上借据需要分摊且出现 0.01 元尾差时，尾差分配给本金余额最小的借据。',
}
