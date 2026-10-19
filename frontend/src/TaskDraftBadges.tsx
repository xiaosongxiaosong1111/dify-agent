type TaskDraftBadgesProps = {
  chat: boolean;
  run: boolean;
};

export default function TaskDraftBadges({ chat, run }: TaskDraftBadgesProps) {
  if (typeof chat !== "boolean" || typeof run !== "boolean") {
    return null;
  }

  if (!chat && !run) {
    return null;
  }

  return (
    <span className="task-draft-badges" aria-label="当前页面草稿状态">
      {chat ? <span title="仅在当前页暂存，刷新或关闭前请另存；尚未发送或试跑。">未发送对话</span> : null}
      {run ? <span title="仅在当前页暂存，刷新或关闭前请另存；尚未发送或试跑。">试跑输入</span> : null}
    </span>
  );
}
