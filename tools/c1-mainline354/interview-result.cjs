// HTTP 200 can contain a rejected model candidate; never advance to content review.
function assertInterviewApplied(before, after) {
  const attempts = after.interview_attempts || [];
  if (attempts.length > (before.interview_attempts || []).length) {
    const reason = attempts.at(-1).reason || '';
    // Emit only the deterministic contract diagnostic, never model-authored text.
    const count = reason.match(/需求检查主题数量不匹配：当前标准为 (\d{1,3}) 项/);
    throw Error(count
      ? `访谈候选未应用：需求检查主题数量不匹配，当前标准为 ${count[1]} 项；整批停止，不重试。`
      : '访谈候选未应用：本次失败或过期记录已保留；整批停止，不重试。');
  }
  const last = after.messages?.at(-1), record = after.intake_review;
  if (after.id !== before.id || after.messages?.length <= (before.messages || []).length
      || last?.source !== 'model' || last.context_revision !== before.revision
      || record?.source !== 'model' || record.origin_revision !== after.revision
      || !Array.isArray(record.review?.checks) || !Array.isArray(record.review?.questions)) {
    throw Error('访谈未取得本轮有效模型检查；整批停止，不进入复核或后续阶段。');
  }
}
module.exports = {assertInterviewApplied};
