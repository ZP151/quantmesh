export const localCsvCopy = {
  en: {
    title: 'Import your daily data', description: 'Keep a local copy, inspect its coverage and decide what evidence is still needed before research.',
    refresh: 'Refresh CSV imports', file: 'Daily OHLCV CSV', label: 'Dataset label', symbol: 'Symbol', venue: 'Market / calendar', start: 'Coverage starts', end: 'Coverage ends', provider: 'Source provider',
    received: 'Source received at', receivedHint: 'UTC, if known. Receiving a file now does not establish when each historical price was available.',
    format: 'UTF-8 CSV · up to 2 MiB and 10,000 rows · one instrument · daily bars. Required header:',
    timestamp: 'timestamp_utc is the bar opening time, with an explicit UTC offset. Required coverage is the window you want checked, not a claim about file completeness.',
    sourceDetails: 'Source details (optional claims)', sourceHint: 'These are your supplied source facts. They do not verify rights, historical availability or corporate actions.',
    rights: 'Usage rights', rightsEvidence: 'Usage evidence', pit: 'Historical availability / revisions', adjustment: 'Price adjustment', volumeUnit: 'Volume unit', sessions: 'Session semantics',
    unknown: 'Unknown', raw: 'Raw prices', adjusted: 'Adjusted prices', shares: 'Shares', base_units: 'Base units', contracts: 'Contracts',
    submit: 'Import and check data', loading: 'Loading CSV imports…', importing: 'Uploading and checking data…', opening: 'Opening saved report…',
    empty: 'No CSV imports yet', emptyHint: 'Choose a file above. You can inspect issues and keep a planning reference without connecting a market-data provider.',
    result: 'Import result', saved: 'Saved local import', previous: 'Previous saved report', previousHint: 'This report belongs to an earlier saved import. The selected file or changed details have not replaced it.',
    structurePass: 'Structure passed', structureReject: 'Data issues found', insufficient: 'Research qualification insufficient', rejected: 'Research qualification rejected',
    source: 'Source and supplied claims', coverage: 'Coverage and freshness', rows: 'Rows', valid: 'Parseable UTC/OHLCV rows', validHint: 'These rows pass timestamp parsing and OHLCV value checks. Session timing, duplicates and ordering may still fail; this is not a qualification or coverage ratio.', expected: 'Expected sessions', range: 'Observed dates', missing: 'Missing sessions', unexpected: 'Unexpected sessions', age: 'Sessions old', asof: 'Checked as of',
    allowed: 'Allowed next steps', inspect: 'Inspect saved evidence', supplied: 'User-supplied data', fixture: 'Synthetic fixture', qualification: 'Research qualification', qualificationHint: 'A readable, complete price file is not proof of research eligibility. Missing dividend or split data does not mean no corporate actions occurred.',
    issues: 'Data issues', count: 'Count', location: 'Location', comparison: 'Expected / observed', limited: 'Showing a limited set of locations; the count includes all reported issues.',
    unverified: 'Unverified evidence checks', suppliedRefs: 'Supplied evidence references have not been independently verified.', passed: 'Passed technical checks', noIssues: 'No failing technical checks reported. Research qualification still applies.',
    plan: 'Plan an experiment with this reference', planHint: 'The reference is for protocol planning only. The current fixture runner cannot run this uploaded data.',
    fix: 'Correct the located issues in your CSV, then import the corrected file.', reference: 'Data reference and original files', original: 'Download original CSV', report: 'Download validation report', referenceDownload: 'Download planning reference',
    history: 'Saved CSV imports', open: 'Open', retry: 'Try the import again after correcting the file or details.',
    unavailable: 'Local data storage is unavailable. Refresh to retry; if it remains unavailable, start the workstation with its local snapshot storage configured.',
    invalid: 'Check the CSV header and import details, then try again. The previous saved report is unchanged.',
    tooLarge: 'Choose a CSV no larger than 2 MiB.', emptyFile: 'This file is empty. Choose a CSV containing the required header and data rows.',
    requestFailed: 'The request did not finish. Your saved reports remain unchanged. Refresh or try the import again.',
    integrity: 'The saved data could not be verified. Reimport the original file; do not use this reference.', invalidResponse: 'The response could not be verified. Refresh to retry; no new result has been accepted.',
    notFound: 'This saved import was not found. Refresh the list or import the original file again.',
  },
  'zh-CN': {
    title: '导入自己的日线数据', description: '保存本地副本，检查覆盖范围，并了解进入研究前仍缺少哪些证据。',
    refresh: '刷新 CSV 导入记录', file: '日线 OHLCV CSV', label: '数据集名称', symbol: '代码', venue: '市场 / 日历', start: '覆盖开始日期', end: '覆盖结束日期', provider: '数据提供方',
    received: '来源接收时间', receivedHint: '如已知请填写 UTC 时间。现在收到文件，并不代表历史价格当时已可获得。',
    format: 'UTF-8 CSV · 最大 2 MiB、10,000 行 · 单一品种日线。必需表头：',
    timestamp: 'timestamp_utc 表示柱线开始时间，须包含明确 UTC 偏移。所需覆盖范围用于检查，并不声称文件完整。',
    sourceDetails: '来源详情（可选声明）', sourceHint: '这些是您提供的来源信息，不代表使用权、历史可获得时间或公司行动已经核实。',
    rights: '使用权限', rightsEvidence: '使用权限证据', pit: '历史可获得时间 / 修订记录', adjustment: '价格复权方式', volumeUnit: '成交量单位', sessions: '交易时段定义',
    unknown: '未知', raw: '未复权价格', adjusted: '已复权价格', shares: '股', base_units: '基础资产单位', contracts: '合约',
    submit: '导入并检查数据', loading: '正在加载 CSV 导入记录…', importing: '正在上传并检查数据…', opening: '正在打开已保存报告…',
    empty: '尚未导入 CSV', emptyHint: '在上方选择文件。无需连接行情提供方，即可检查问题并保留协议规划引用。',
    result: '导入结果', saved: '已保存本地导入', previous: '上一次保存的报告', previousHint: '此报告属于先前保存的导入。本次选择的文件或修改后的信息尚未替换它。',
    structurePass: '结构检查通过', structureReject: '发现数据问题', insufficient: '研究资格证据不足', rejected: '研究资格不通过',
    source: '来源及用户声明', coverage: '覆盖范围与时效', rows: '数据行数', valid: 'UTC/OHLCV 可解析行', validHint: '这些行通过时间解析和 OHLCV 数值检查，尚未扣除时段、重复或顺序问题，不能作为研究资格或覆盖比率。', expected: '预期交易时段', range: '实际日期范围', missing: '缺失时段', unexpected: '非预期时段', age: '已过去的交易时段', asof: '检查时间',
    allowed: '允许的下一步', inspect: '检查已保存的证据', supplied: '用户提供的数据', fixture: '合成示例数据', qualification: '研究资格', qualificationHint: '文件可读且价格完整，不代表具备研究资格。缺少分红或拆股数据，不等于未发生公司行动。',
    issues: '数据问题', count: '数量', location: '位置', comparison: '预期 / 实际', limited: '仅显示部分问题位置；数量包含全部已报告问题。',
    unverified: '尚未验证的证据检查', suppliedRefs: '所提供的证据引用尚未独立验证。', passed: '已通过的技术检查', noIssues: '未报告失败的技术检查，仍受研究资格限制。',
    plan: '使用此引用规划实验', planHint: '此引用仅供协议规划。当前示例执行器不能运行本次上传的数据。',
    fix: '根据问题位置修正 CSV，然后重新导入。', reference: '数据引用及原始文件', original: '下载原始 CSV', report: '下载校验报告', referenceDownload: '下载规划引用',
    history: '已保存的 CSV 导入', open: '打开', retry: '修正文件或信息后，可再次尝试导入。',
    unavailable: '本地数据存储不可用。请刷新重试；若仍不可用，请启用工作台的本地快照存储。',
    invalid: '请检查 CSV 表头和导入信息后重试。先前保存的报告未改变。', tooLarge: '请选择不超过 2 MiB 的 CSV。', emptyFile: '文件为空。请选择包含必需表头和数据行的 CSV。',
    requestFailed: '请求未完成，已保存报告未改变。请刷新或重新导入。', integrity: '无法验证已保存的数据。请重新导入原始文件，暂勿使用此引用。',
    invalidResponse: '无法验证响应。请刷新重试；未接受任何新结果。', notFound: '未找到此导入记录。请刷新列表或重新导入原始文件。',
  },
}


// Translate only stable, known server reasons. Preserve the full original text
// as title/disclosure evidence; future server reasons remain verbatim.
export function explainCsvReason(reason: string, locale: 'en' | 'zh-CN'): string {
  const c = localCsvCopy[locale]
  const known: [string, string, string][] = [
    ['Source scope/license', 'Usage rights are supplied by you and remain unverified.', '使用权限由您提供，尚未独立验证。'],
    ['Bar/session time and receipt', 'Historical availability and revision history have not been verified.', '历史可获得时间和修订记录尚未验证。'],
    ['Corporate actions, adjustments', 'Dividend and split history, including payment dates, remains unverified.', '分红、拆股历史及支付日期尚未验证。'],
    ['Calendar alignment does not', 'Matching the calendar does not verify the provider’s daily-session definition.', '日历对齐不代表供应商的日线时段定义已验证。'],
    ['Declared adjustment=', 'Price units, currency and adjustment history remain unverified.', '价格单位、币种和复权历史尚未验证。'],
    ['Declared volume unit=', 'Volume units and executable liquidity remain unverified.', '成交量单位和可成交流动性尚未验证。'],
    ['Optional Phase1 preauthorization/', c.suppliedRefs, c.suppliedRefs],
  ]
  const match = known.find(([prefix]) => reason.startsWith(prefix))
  return match ? match[locale === 'en' ? 1 : 2] : reason
}
