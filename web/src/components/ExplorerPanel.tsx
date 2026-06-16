import { useMemo, useRef, useState, useEffect } from 'react'
import { Tree } from 'react-arborist'
import type { FileNode } from '@/types/api'

interface ExplorerPanelProps {
  fileTree: FileNode[]
  selectedFile: string | null
  onFileSelect: (path: string) => void
}

interface TreeNode {
  id: string
  name: string
  children?: TreeNode[]
}

/** 将扁平 FileNode 列表转为 react-arborist 需要的嵌套树结构 */
function buildTree(files: FileNode[]): TreeNode[] {
  const root: TreeNode[] = []
  const map = new Map<string, TreeNode>()

  // 先创建目录节点，同时确保所有中间目录也存在
  for (const f of files) {
    if (f.type === 'dir') {
      // 确保所有父目录路径都存在节点
      ensurePath(map, f.path)
    }
  }

  // 构建父子关系
  for (const f of files) {
    if (f.type === 'dir') {
      const node = map.get(f.path)!
      const parentPath = f.path.substring(0, f.path.lastIndexOf('/'))
      if (parentPath && map.has(parentPath)) {
        if (!map.get(parentPath)!.children!.some((c) => c.id === f.path)) {
          map.get(parentPath)!.children!.push(node)
        }
      } else {
        if (!root.some((c) => c.id === f.path)) {
          root.push(node)
        }
      }
    } else {
      const fileNode: TreeNode = { id: f.path, name: f.name }
      const parentPath = f.path.substring(0, f.path.lastIndexOf('/'))
      if (parentPath && map.has(parentPath)) {
        map.get(parentPath)!.children!.push(fileNode)
      } else {
        root.push(fileNode)
      }
    }
  }

  return sortNodes(root)
}

/** 文件夹优先，同类型按名称字母序 */
function sortNodes(nodes: TreeNode[]): TreeNode[] {
  return nodes.sort((a, b) => {
    const aDir = a.children !== undefined
    const bDir = b.children !== undefined
    if (aDir !== bDir) return aDir ? -1 : 1
    return a.name.localeCompare(b.name)
  }).map(n => n.children ? { ...n, children: sortNodes(n.children) } : n)
}

/** 递归确保路径上所有目录节点都存在 */
function ensurePath(map: Map<string, TreeNode>, dirPath: string) {
  if (map.has(dirPath)) return
  const name = dirPath.substring(dirPath.lastIndexOf('/') + 1)
  map.set(dirPath, { id: dirPath, name, children: [] })
  const parentPath = dirPath.substring(0, dirPath.lastIndexOf('/'))
  if (parentPath) {
    ensurePath(map, parentPath)
  }
}

export function ExplorerPanel({ fileTree, selectedFile, onFileSelect }: ExplorerPanelProps) {
  const treeData = useMemo(() => buildTree(fileTree), [fileTree])
  const containerRef = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState(400)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setHeight(entry.contentRect.height)
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="h-full overflow-hidden" ref={containerRef} data-testid={fileTree.length === 0 ? 'explorer-empty' : 'explorer-panel'}>
      {fileTree.length === 0 ? (
        <div className="p-4 text-sm text-muted-foreground">
          暂无文件
        </div>
      ) : (
        <Tree
          data={treeData}
          openByDefault={false}
          width="100%"
          height={height}
          indent={16}
          rowHeight={28}
          selection={selectedFile ?? undefined}
          onActivate={(node) => {
            if (node.isLeaf) {
              onFileSelect(node.id)
            }
          }}
        >
          {NodeRenderer}
        </Tree>
      )}
    </div>
  )
}

function NodeRenderer({ node, style }: { node: any; style: React.CSSProperties }) {
  return (
    <div
      style={style}
      className={`flex items-center gap-1 px-2 cursor-pointer hover:bg-accent/50 ${node.isSelected ? 'bg-accent' : ''}`}
      onClick={() => node.handleClick({} as React.MouseEvent)}
      data-testid={`tree-node-${node.id}`}
    >
      {node.isInternal ? (
        <span className="text-muted-foreground text-xs">
          {node.isOpen ? '▼' : '▶'}
        </span>
      ) : (
        <span className="w-3" />
      )}
      <span className="text-sm truncate">{node.data.name}</span>
    </div>
  )
}
