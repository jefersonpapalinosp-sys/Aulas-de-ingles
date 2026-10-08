export type DiffPart = {
  kind: 'same' | 'added' | 'removed'
  text: string
}

function words(text: string): string[] {
  return text.trim().match(/[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)?|[^\s]/gu) ?? []
}

/** Diff por palavras baseado na maior subsequência comum. */
export function wordDiff(before: string, after: string): DiffPart[] {
  const left = words(before)
  const right = words(after)
  const lengths = Array.from({ length: left.length + 1 }, () =>
    Array<number>(right.length + 1).fill(0),
  )

  for (let i = 1; i <= left.length; i += 1) {
    for (let j = 1; j <= right.length; j += 1) {
      lengths[i]![j] =
        left[i - 1] === right[j - 1]
          ? lengths[i - 1]![j - 1]! + 1
          : Math.max(lengths[i - 1]![j]!, lengths[i]![j - 1]!)
    }
  }

  const reversed: DiffPart[] = []
  let i = left.length
  let j = right.length
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && left[i - 1] === right[j - 1]) {
      reversed.push({ kind: 'same', text: left[i - 1]! })
      i -= 1
      j -= 1
    } else if (j > 0 && (i === 0 || lengths[i]![j - 1]! >= lengths[i - 1]![j]!)) {
      reversed.push({ kind: 'added', text: right[j - 1]! })
      j -= 1
    } else {
      reversed.push({ kind: 'removed', text: left[i - 1]! })
      i -= 1
    }
  }
  return reversed.reverse()
}
