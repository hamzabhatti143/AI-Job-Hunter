export default function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    matched: 'bg-blue-900 text-blue-300',
    applied: 'bg-green-900 text-green-300',
    rejected: 'bg-red-900 text-red-300',
    pending: 'bg-yellow-900 text-yellow-300',
    sent: 'bg-purple-900 text-purple-300',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] || 'bg-gray-800 text-gray-400'}`}>
      {status}
    </span>
  )
}
