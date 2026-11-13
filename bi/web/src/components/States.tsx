export function Loading({ label = '加载中…' }: { label?: string }) {
  return <div className="state-box"><span className="spinner" />{label}</div>
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-box error">
      <strong>数据加载失败</strong>
      <span>{message}</span>
      {onRetry && <button onClick={onRetry}>重试</button>}
    </div>
  )
}

export function Empty({ label = '当前筛选下没有数据' }: { label?: string }) {
  return <div className="empty-state">{label}</div>
}

export function Suppressed({ n }: { n?: number | null }) {
  return <span className="suppressed" title={`n=${n ?? 0} < 20，统计值已抑制`}>—</span>
}
