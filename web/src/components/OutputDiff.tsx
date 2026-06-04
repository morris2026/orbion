interface OutputDiffProps {
  diff: string
}

export default function OutputDiff({ diff }: OutputDiffProps) {
  const lines = diff.split('\n')
  return (
    <div className="text-xs font-mono bg-muted/50 rounded p-2 overflow-x-auto">
      {lines.map((line, i) => {
        let className = 'whitespace-pre'
        if (line.startsWith('+') && !line.startsWith('+++')) className += ' text-green-600 bg-green-50'
        else if (line.startsWith('-') && !line.startsWith('---')) className += ' text-red-600 bg-red-50'
        else if (line.startsWith('@@')) className += ' text-blue-600'
        return <div key={i} className={className}>{line}</div>
      })}
    </div>
  )
}