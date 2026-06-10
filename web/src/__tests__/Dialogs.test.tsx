import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CreateProjectDialog from '@/components/CreateProjectDialog'
import CreateThreadDialog from '@/components/CreateThreadDialog'
import AddMemberDialog from '@/components/AddMemberDialog'
import RegisterAgentDialog from '@/components/RegisterAgentDialog'
import * as apiModule from '@/lib/api'

describe('CreateProjectDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  describe('MVP-UI-5.1: 正常创建（含默认线程ID）', () => {
    it('输入名称+描述 → 提交 → onCreateProject收到含default_thread_id的数据；onSelectThread收到项目ID和默认线程ID', async () => {
      const user = userEvent.setup()
      const onCreateProject = vi.fn()
      const onSelectThread = vi.fn()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({ id: 'new-proj', name: '新项目', description: '新描述', role: 'owner', default_thread_id: 'dt-new', created_at: '' })

      render(<CreateProjectDialog open={true} onClose={onClose} onCreateProject={onCreateProject} onSelectThread={onSelectThread} />)

      await user.type(screen.getByLabelText(/项目名称/i), '新项目')
      await user.type(screen.getByLabelText(/项目描述/i), '新描述')
      await user.click(screen.getByRole('button', { name: /创建/i }))

      await waitFor(() => {
        expect(onCreateProject).toHaveBeenCalledWith({ id: 'new-proj', name: '新项目', description: '新描述', role: 'owner', default_thread_id: 'dt-new', created_at: '' })
        expect(onSelectThread).toHaveBeenCalledWith('new-proj', 'dt-new')
        expect(onClose).toHaveBeenCalled()
      })
    })
  })

  describe('MVP-UI-5.2: 同名项目409', () => {
    it('创建项目API返回409 → Dialog显示错误提示，不关闭', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      const onCreateProject = vi.fn()
      const onSelectThread = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockRejectedValue(new apiModule.ApiError(409, '项目名称已存在'))

      render(<CreateProjectDialog open={true} onClose={onClose} onCreateProject={onCreateProject} onSelectThread={onSelectThread} />)

      await user.type(screen.getByLabelText(/项目名称/i), '已存在的项目')
      await user.click(screen.getByRole('button', { name: /创建/i }))

      await waitFor(() => {
        expect(screen.getByText(/项目名称已存在/i)).toBeInTheDocument()
      })
      expect(onCreateProject).not.toHaveBeenCalled()
      expect(onSelectThread).not.toHaveBeenCalled()
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('MVP-UI-5.3: 名称必填', () => {
    it('不输入名称 → 提交按钮disabled', () => {
      render(<CreateProjectDialog open={true} onClose={vi.fn()} onCreateProject={vi.fn()} onSelectThread={vi.fn()} />)
      expect(screen.getByRole('button', { name: /创建/i })).toBeDisabled()
    })
  })

  describe('MVP-UI-5.4: 取消关闭', () => {
    it('点击取消 → onClose被调用', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<CreateProjectDialog open={true} onClose={onClose} onCreateProject={vi.fn()} onSelectThread={vi.fn()} />)
      await user.click(screen.getByRole('button', { name: /取消/i }))
      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('MVP-UI-5.5: 描述可选', () => {
    it('只输入名称 → 提交成功，default_thread_id从响应中获取', async () => {
      const user = userEvent.setup()
      const onCreateProject = vi.fn()
      const onSelectThread = vi.fn()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({ id: 'p1', name: '只名称', description: null, role: 'owner', default_thread_id: 'dt1', created_at: '' })

      render(<CreateProjectDialog open={true} onClose={onClose} onCreateProject={onCreateProject} onSelectThread={onSelectThread} />)

      await user.type(screen.getByLabelText(/项目名称/i), '只名称')
      await user.click(screen.getByRole('button', { name: /创建/i }))

      await waitFor(() => {
        expect(onCreateProject).toHaveBeenCalledWith({ id: 'p1', name: '只名称', description: null, role: 'owner', default_thread_id: 'dt1', created_at: '' })
        expect(onSelectThread).toHaveBeenCalledWith('p1', 'dt1')
        expect(onClose).toHaveBeenCalled()
      })
    })
  })
})

describe('CreateThreadDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  describe('MVP-UI-5.6: 正常创建', () => {
    it('输入标题 → 提交 → apiPost调用+onCreateThread收到数据', async () => {
      const user = userEvent.setup()
      const onCreateThread = vi.fn()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({
        id: 't-new', title: '新线程', status: 'active', type: 'discussion',
        has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '',
      })

      render(<CreateThreadDialog open={true} projectId="proj-1" onClose={onClose} onCreateThread={onCreateThread} />)

      await user.type(screen.getByLabelText(/线程标题/i), '新线程')
      await user.click(screen.getByRole('button', { name: /创建/i }))

      await waitFor(() => {
        expect(apiModule.apiPost).toHaveBeenCalledWith('/projects/proj-1/threads', { title: '新线程', type: 'discussion' })
        expect(onCreateThread).toHaveBeenCalledWith('proj-1', { id: 't-new', title: '新线程', status: 'active', type: 'discussion', has_summary: false, pending_plan_count: 0, message_count: 0, created_at: '' })
      })
    })
  })

  describe('MVP-UI-5.7: 标题必填', () => {
    it('不输入标题 → 提交按钮disabled', () => {
      render(<CreateThreadDialog open={true} projectId="proj-1" onClose={vi.fn()} onCreateThread={vi.fn()} />)
      expect(screen.getByRole('button', { name: /创建/i })).toBeDisabled()
    })
  })

  describe('MVP-UI-5.8: 取消关闭', () => {
    it('点击取消 → onClose被调用', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<CreateThreadDialog open={true} projectId="proj-1" onClose={onClose} onCreateThread={vi.fn()} />)
      await user.click(screen.getByRole('button', { name: /取消/i }))
      expect(onClose).toHaveBeenCalled()
    })
  })
})

describe('AddMemberDialog', () => {
  /** mock用户列表 */
  const mockUsers = [
    { user_id: 'u1', username: 'alice', display_name: 'Alice', status: 'active', created_at: '' },
    { user_id: 'u2', username: 'bob', display_name: 'Bob', status: 'active', created_at: '' },
    { user_id: 'u3', username: 'charlie', display_name: 'Charlie', status: 'active', created_at: '' },
  ]

  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  describe('MVP-UI-5.9: 全量用户列表', () => {
    it('Dialog打开 → 显示所有active用户', async () => {
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
        expect(screen.getByText('Bob')).toBeInTheDocument()
        expect(screen.getByText('Charlie')).toBeInTheDocument()
      })
    })
  })

  describe('MVP-UI-5.10: 搜索动态过滤', () => {
    it('输入关键词 → debounce后列表只显示匹配用户', async () => {
      const user = userEvent.setup()
      vi.spyOn(apiModule, 'apiGet').mockImplementation((path: string, params?: Record<string, string>) => {
        if (params?.username) {
          return Promise.resolve([mockUsers[0]])
        }
        return Promise.resolve(mockUsers)
      })

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.type(screen.getByPlaceholderText(/搜索/i), 'ali')

      // 等待debounce自然触发（300ms）
      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
        expect(screen.queryByText('Bob')).not.toBeInTheDocument()
      }, { timeout: 1000 })
    })
  })

  describe('MVP-UI-5.11: 选择用户+角色', () => {
    it('选用户 → 选角色 → 提交 → onAddMember收到数据', async () => {
      const user = userEvent.setup()
      const onAddMember = vi.fn()

      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)
      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({})

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={onAddMember} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Alice'))
      await user.click(screen.getByRole('button', { name: /添加/i }))

      await waitFor(() => {
        expect(onAddMember).toHaveBeenCalledWith('proj-1', { user_id: 'u1', role: 'member' })
      })
    })
  })

  describe('MVP-UI-5.12: 角色默认值', () => {
    it('角色dropdown默认选中member', async () => {
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      expect(screen.getByDisplayValue(/member/i)).toBeInTheDocument()
    })
  })

  describe('MVP-UI-5.13: 搜索无结果', () => {
    it('输入不匹配用户名 → 空列表+无匹配提示', async () => {
      const user = userEvent.setup()
      vi.spyOn(apiModule, 'apiGet').mockImplementation((path: string, params?: Record<string, string>) => {
        if (params?.username) return Promise.resolve([])
        return Promise.resolve(mockUsers)
      })

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.type(screen.getByPlaceholderText(/搜索/i), 'zzz')

      // 等待debounce自然触发
      await waitFor(() => {
        expect(screen.getByText(/无匹配/i)).toBeInTheDocument()
      }, { timeout: 1000 })
    })
  })

  describe('MVP-UI-5.14: 未选用户提交', () => {
    it('不选用户 → 提交按钮disabled', async () => {
      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      expect(screen.getByRole('button', { name: /添加/i })).toBeDisabled()
    })
  })

  describe('MVP-UI-5.15: API返回500', () => {
    it('添加成员API 500 → Dialog显示错误，不关闭', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)
      vi.spyOn(apiModule, 'apiPost').mockRejectedValue(new apiModule.ApiError(500, '服务器错误'))

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={onClose} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Alice'))
      await user.click(screen.getByRole('button', { name: /添加/i }))

      await waitFor(() => {
        expect(screen.getByText(/失败/i)).toBeInTheDocument()
      })
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('MVP-UI-5.16: 搜索API失败', () => {
    it('搜索接口失败 → 回退显示全量列表', async () => {
      const user = userEvent.setup()
      vi.spyOn(apiModule, 'apiGet').mockImplementation((path: string, params?: Record<string, string>) => {
        if (params?.username) return Promise.reject(new apiModule.ApiError(500, '搜索失败'))
        return Promise.resolve(mockUsers)
      })

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={vi.fn()} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.type(screen.getByPlaceholderText(/搜索/i), 'ali')

      // 搜索失败后回退全量列表（debounce自然触发）
      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
        expect(screen.getByText('Bob')).toBeInTheDocument()
      }, { timeout: 1000 })
    })
  })

  describe('MVP-UI-5.17: 添加已存在成员', () => {
    it('后端409 → Dialog显示错误提示', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiGet').mockResolvedValue(mockUsers)
      vi.spyOn(apiModule, 'apiPost').mockRejectedValue(new apiModule.ApiError(409, '成员已存在'))

      render(<AddMemberDialog open={true} projectId="proj-1" onClose={onClose} onAddMember={vi.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Alice')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Alice'))
      await user.click(screen.getByRole('button', { name: /添加/i }))

      await waitFor(() => {
        expect(screen.getByText(/已存在/i)).toBeInTheDocument()
      })
      expect(onClose).not.toHaveBeenCalled()
    })
  })
})

describe('RegisterAgentDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  describe('MVP-UI-5.18: 正常注册', () => {
    it('选类型→选模型→输入名称→提交 → onRegisterAgent收到数据', async () => {
      const user = userEvent.setup()
      const onRegisterAgent = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockResolvedValue({})

      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={onRegisterAgent} />)

      await user.click(screen.getByRole('button', { name: /summary/i }))
      await user.click(screen.getByRole('combobox', { name: /模型/i }))
      await user.click(screen.getByText(/claude-haiku/i))
      await user.click(screen.getByRole('button', { name: /注册/i }))

      await waitFor(() => {
        expect(onRegisterAgent).toHaveBeenCalledWith('proj-1', {
          agent_type: 'summary',
          model_id: expect.stringContaining('claude-haiku'),
          display_name: '总结Agent',
        })
      })
    })
  })

  describe('MVP-UI-5.19: 类型单选', () => {
    it('只能选择一种类型，不能多选', async () => {
      const user = userEvent.setup()
      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: /summary/i }))
      expect(screen.getByRole('button', { name: /summary/i })).toHaveAttribute('data-selected', 'true')

      await user.click(screen.getByRole('button', { name: /decompose/i }))
      expect(screen.getByRole('button', { name: /summary/i })).not.toHaveAttribute('data-selected', 'true')
      expect(screen.getByRole('button', { name: /decompose/i })).toHaveAttribute('data-selected', 'true')
    })
  })

  describe('MVP-UI-5.20: 模型下拉选项', () => {
    it('包含 claude-haiku-4-5-20251001 和 claude-sonnet-4-6', async () => {
      const user = userEvent.setup()
      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={vi.fn()} />)

      await user.click(screen.getByRole('combobox', { name: /模型/i }))
      expect(screen.getByText(/claude-haiku-4-5-20251001/i)).toBeInTheDocument()
      expect(screen.getByText(/claude-sonnet-4-6/i)).toBeInTheDocument()
    })
  })

  describe('MVP-UI-5.21: display_name预填', () => {
    it('选summary → 预填"总结Agent"', async () => {
      const user = userEvent.setup()
      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: /summary/i }))
      expect(screen.getByLabelText(/显示名称/i)).toHaveValue('总结Agent')
    })
  })

  describe('MVP-UI-5.22: 不选类型提交', () => {
    it('不选类型 → 提交按钮disabled', () => {
      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={vi.fn()} />)
      expect(screen.getByRole('button', { name: /注册/i })).toBeDisabled()
    })
  })

  describe('MVP-UI-5.23: 注册API失败', () => {
    it('mock 500 → 显示错误，不关闭', async () => {
      const user = userEvent.setup()
      const onClose = vi.fn()

      vi.spyOn(apiModule, 'apiPost').mockRejectedValue(new apiModule.ApiError(500, '服务器错误'))

      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={onClose} onRegisterAgent={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: /summary/i }))
      await user.click(screen.getByRole('button', { name: /注册/i }))

      await waitFor(() => {
        expect(screen.getByText(/失败/i)).toBeInTheDocument()
      })
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('MVP-UI-5.24: 空名称提交', () => {
    it('清空预填名称 → 提交按钮disabled', async () => {
      const user = userEvent.setup()
      render(<RegisterAgentDialog open={true} projectId="proj-1" onClose={vi.fn()} onRegisterAgent={vi.fn()} />)

      await user.click(screen.getByRole('button', { name: /summary/i }))
      const nameInput = screen.getByLabelText(/显示名称/i)
      await user.clear(nameInput)

      expect(screen.getByRole('button', { name: /注册/i })).toBeDisabled()
    })
  })
})