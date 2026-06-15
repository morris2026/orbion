import { test, expect } from '@playwright/test'

// ---- 固定用户凭据（不随worker重启变化，靠DB清理或409处理保证可用） ----
const ADMIN = {
  username: 'e2e_admin',
  password: 'password12345678',
  displayName: 'E2E Admin',
}

const MEMBER = {
  username: 'e2e_member',
  password: 'password12345678',
  displayName: 'E2E Member',
}

let adminToken: string
let memberToken: string

// ---- 辅助函数 ----

/** 辅助：从localStorage获取JWT token */
async function getToken(page): string | null {
  return await page.evaluate(() => localStorage.getItem('orbion_token'))
}

/** 辅助：带认证的API请求headers（从page localStorage读取） */
async function authHeaders(page) {
  const token = await getToken(page)
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

/** 辅助：UI登录（填写用户名密码，等待跳转workspace） */
async function loginAs(page, username: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL(/\/workspace/)
}

/** 辅助：创建项目（唯一名称，避免跨test数据冲突）
 * Why: createProject的projection异步添加creator为member+default thread，
 * 后续API调用（members/threads）必须等projection完成才能返回正确数据。
 */
async function createProject(page, suffix: string) {
  const name = `E2E项目_${suffix}_${Date.now()}`
  const headers = await authHeaders(page)
  const response = await page.request.post('/projects', {
    data: { name, description: 'E2E测试项目描述' },
    headers,
  })
  expect(response.ok()).toBeTruthy()
  const project = await response.json()

  // 等待projection完成：members API能返回数据
  for (let attempt = 0; attempt < 10; attempt++) {
    const membersResp = await page.request.get(`/projects/${project.id}/members`, { headers })
    if (membersResp.ok()) {
      const members = await membersResp.json()
      if (members.length > 0) return { ...project, name }
    }
    await page.waitForTimeout(500)
  }
  throw new Error(`project members projection not ready after 5s for project ${project.id}`)
}

/** 辅助：注册3种agent到项目（summary/decompose/execute）
 * Why: createProject的projection异步添加creator为member，registerAgents
 * 必须等projection完成才能成功（否则403 "Not a project member"）。
 * 重试3次避免竞态条件。
 */
async function registerAgents(page, projectId: string) {
  const headers = await authHeaders(page)
  for (const agentType of ['summary', 'decompose', 'execute']) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const resp = await page.request.post(`/projects/${projectId}/agents`, {
        data: { agent_type: agentType, model_id: 'e2e-test', display_name: `${agentType}Agent` },
        headers,
      })
      if (resp.ok()) break
      if (resp.status() === 403 && attempt < 2) {
        await page.waitForTimeout(500)
        continue
      }
      const body = await resp.text()
      throw new Error(`Agent registration failed for ${agentType}: ${resp.status()} ${body}`)
    }
  }
}

/** 辅助：轮询outputs API直到投影完成（CQRS最终一致性） */
async function waitForOutputs(page, projectId: string, minCount = 1): Promise<any[]> {
  const headers = await authHeaders(page)
  for (let attempt = 0; attempt < 10; attempt++) {
    const resp = await page.request.get(`/projects/${projectId}/outputs`, { headers })
    if (resp.ok()) {
      const outputs = await resp.json()
      if (outputs.length >= minCount) return outputs
    }
    await page.waitForTimeout(500)
  }
  throw new Error(`outputs projection not ready after 5s for project ${projectId}`)
}

/** 辅助：创建线程（唯一标题，重试等待projection添加creator为member） */
async function createThread(page, projectId: string, suffix: string) {
  const title = `E2E线程_${suffix}_${Date.now()}`
  const headers = await authHeaders(page)
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await page.request.post(`/projects/${projectId}/threads`, {
      data: { title, type: 'discussion' },
      headers,
    })
    if (response.ok()) {
      const thread = await response.json()
      return { ...thread, title }
    }
    if (response.status() === 403 && attempt < 2) {
      await page.waitForTimeout(500)
      continue
    }
    const body = await response.text()
    throw new Error(`createThread failed: ${response.status()} ${body}`)
  }
  throw new Error('createThread: unreachable')
}

test.describe('自我构建9点验证', () => {

  test.beforeAll(async ({ request }) => {
    // 1. 注册或登录admin
    const adminResp = await request.post('/auth/register', {
      data: {
        username: ADMIN.username,
        password: ADMIN.password,
        display_name: ADMIN.displayName,
      },
    })

    if (adminResp.status() === 409) {
      // admin已存在（DB未清理），直接登录
      const loginResp = await request.post('/auth/login', {
        data: { username: ADMIN.username, password: ADMIN.password },
      })
      expect(loginResp.ok()).toBeTruthy()
      adminToken = (await loginResp.json()).access_token
    } else {
      expect(adminResp.ok()).toBeTruthy()
      const adminData = await adminResp.json()
      if (adminData.status === 'pending') {
        // DB有残留active用户→admin为pending，此场景应靠E2E服务器DB清理避免
        // 如果仍发生，说明DB未正确清理，需要先获取已有admin的token来审批
        throw new Error(`admin注册返回pending，DB有残留数据未清理。请重启E2E服务器。`)
      }
      expect(adminData.status).toBe('active')
      adminToken = adminData.access_token
    }

    // 2. 注册member
    const memberResp = await request.post('/auth/register', {
      data: {
        username: MEMBER.username,
        password: MEMBER.password,
        display_name: MEMBER.displayName,
      },
    })

    if (memberResp.status() === 409) {
      // member已存在且已审批，直接登录
      const loginResp = await request.post('/auth/login', {
        data: { username: MEMBER.username, password: MEMBER.password },
      })
      expect(loginResp.ok()).toBeTruthy()
      memberToken = (await loginResp.json()).access_token
    } else {
      expect(memberResp.ok()).toBeTruthy()
      const memberData = await memberResp.json()
      // 第二个用户必定pending，admin审批后登录
      expect(memberData.status).toBe('pending')
      const approveResp = await request.post(`/auth/users/${memberData.user_id}/approve`, {
        headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
        data: {},
      })
      expect(approveResp.ok()).toBeTruthy()

      const loginResp = await request.post('/auth/login', {
        data: { username: MEMBER.username, password: MEMBER.password },
      })
      expect(loginResp.ok()).toBeTruthy()
      memberToken = (await loginResp.json()).access_token
    }
  })

  test.beforeEach(async ({ page }) => {
    // 默认以admin登录
    await loginAs(page, ADMIN.username, ADMIN.password)
  })

  test('TC-21.1 验证点1：创建项目+添加成员+创建线程', async ({ page }) => {
    const project = await createProject(page, '21_1')
    expect(project.id).toBeTruthy()

    // 创建者自动成为Owner — 通过成员列表API验证（createProject已等投影完成）
    const headers = await authHeaders(page)
    const membersResp = await page.request.get(`/projects/${project.id}/members`, { headers })
    expect(membersResp.ok()).toBeTruthy()
    const members = await membersResp.json()
    const ownerMembers = members.filter((m) => m.role === 'owner')
    expect(ownerMembers.length).toBeGreaterThanOrEqual(1)

    // 创建线程
    const thread = await createThread(page, project.id, '21_1')
    expect(thread.id).toBeTruthy()

    // 前端显示
    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await expect(page.getByText(thread.title)).toBeVisible()
  })

  test('TC-21.2 验证点2：人类在讨论线程中发言', async ({ page }) => {
    const project = await createProject(page, '21_2')
    const thread = await createThread(page, project.id, '21_2')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    const messageInput = page.getByPlaceholder(/输入消息.*\/summarize/)
    await messageInput.fill('这是我的观点')
    await page.getByRole('button', { name: /发送/ }).click()

    // SSE推送后消息可见（单一来源，不会重复）
    await expect(page.getByText('这是我的观点')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('p.whitespace-pre-wrap', { hasText: '这是我的观点' })).toHaveCount(1)
  })

  test('TC-21.3 验证点3：总结Agent产出摘要', async ({ page }) => {
    const project = await createProject(page, '21_3')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_3')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()

    // 等待Agent产出摘要（SSE推送）
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })
    const agentMessage = page.locator('[data-participant-type="agent"]')
    await expect(agentMessage.first()).toBeVisible()

    // API级验证：摘要消息含结构化字段
    const headers = await authHeaders(page)
    const messagesResp = await page.request.get(`/threads/${thread.id}/messages`, { headers })
    expect(messagesResp.ok()).toBeTruthy()
    const messages = await messagesResp.json()
    const summaryMessages = messages.filter((m) => m.event_type === 'DiscussionSummaryGenerated')
    expect(summaryMessages.length).toBeGreaterThanOrEqual(1)
    const summaryContent = summaryMessages[0].content
    expect(summaryContent).toContain('consensus_points')
  })

  test('TC-21.4 验证点4：分解Agent产出执行计划', async ({ page }) => {
    const project = await createProject(page, '21_4')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_4')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })

    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 15000 })
  })

  test('TC-21.5 验证点5：人类审批执行计划', async ({ page }) => {
    const project = await createProject(page, '21_5')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_5')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 20000 })

    const approveBtn = page.getByRole('button', { name: /批准/ })
    await expect(approveBtn).toBeVisible()

    await approveBtn.click()

    await expect(page.getByText('approved')).toBeVisible({ timeout: 15000 })
    await expect(approveBtn).not.toBeVisible()
  })

  test('TC-21.6 验证点6：执行Agent产出代码diff', async ({ page }) => {
    const project = await createProject(page, '21_6')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_6')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()

    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })
  })

  test('TC-21.7 验证点7：人类审查diff → Approve', async ({ page }) => {
    const project = await createProject(page, '21_7')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_7')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()
    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })

    const outputs = await waitForOutputs(page, project.id)
    const headers = await authHeaders(page)

    const approveResp = await page.request.post(`/outputs/${outputs[0].id}/approve`, {
      data: { feedback: '看起来不错' },
      headers,
    })
    expect(approveResp.ok()).toBeTruthy()
    const approveData = await approveResp.json()
    expect(approveData.status).toBe('approved')
  })

  test('TC-21.8 验证点8：审批通过 → Git commit', async ({ page }) => {
    const project = await createProject(page, '21_8')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_8')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByPlaceholder(/输入消息.*\/summarize/).fill('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()
    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })

    const outputs = await waitForOutputs(page, project.id)
    const headers = await authHeaders(page)

    await page.request.post(`/outputs/${outputs[0].id}/approve`, {
      data: { feedback: '通过审查' },
      headers,
    })

    // Git commit 是异步事件处理，轮询等待 commit 完成
    let gitLog: any[] = []
    for (let attempt = 0; attempt < 10; attempt++) {
      const gitLogResp = await page.request.get(`/git/${project.id}/git-log?repo_name=orbion`, { headers })
      expect(gitLogResp.ok()).toBeTruthy()
      gitLog = await gitLogResp.json()
      if (gitLog.length >= 2) break
      await page.waitForTimeout(500)
    }
    expect(gitLog.length).toBeGreaterThanOrEqual(2)
    const latestCommit = gitLog[0]
    expect(latestCommit.message).toContain('approve')
  })

  test('TC-21.9 验证点9：三栏实时展示+SSE推送', async ({ page }) => {
    const project = await createProject(page, '21_9')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_9')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    const messageInput = page.getByPlaceholder(/输入消息.*\/summarize/)
    await messageInput.fill('实时更新测试消息')
    await page.getByRole('button', { name: /发送/ }).click()
    // 乐观更新：POST返回后立即显示
    await expect(page.getByText('实时更新测试消息')).toBeVisible({ timeout: 5000 })

    // 使用斜杠命令/summarize替代旧的请求总结按钮
    await messageInput.click()
    await messageInput.fill('/summarize')
    await expect(messageInput).toHaveValue('/summarize')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })
    await expect(page.locator('#workspace-right').getByText(/计划/).first()).toBeVisible({ timeout: 15000 })
  })

  test('TC-21.10 负面路径：无JWT→受保护端点返回401', async ({ page }) => {
    const resp = await page.request.post('/projects', {
      data: { name: '未认证项目', description: '不应创建' },
    })
    expect(resp.status()).toBe(401)
  })

  test('TC-21.11 负面路径：非成员→发送消息返回403', async ({ page }) => {
    // Admin创建项目+线程
    const project = await createProject(page, '21_11')
    const thread = await createThread(page, project.id, '21_11')

    // Member（已审批active但非项目成员）尝试发消息→403
    const resp = await page.request.post(`/threads/${thread.id}/messages`, {
      data: { content: '非成员消息' },
      headers: { Authorization: `Bearer ${memberToken}`, 'Content-Type': 'application/json' },
    })
    expect(resp.status()).toBe(403)
  })

  test('TC-21.12 权限验证：admin可访问审批页面', async ({ page }) => {
    await page.goto('/approval')
    await expect(page.getByText(/待审批/)).toBeVisible()
  })

  test('TC-21.13 权限验证：普通用户不可访问审批页面', async ({ page }) => {
    await loginAs(page, MEMBER.username, MEMBER.password)
    // 非admin访问/approval → AdminRoute守卫重定向回/workspace
    await page.goto('/approval')
    await page.waitForURL(/\/workspace/)
    expect(page.url()).toContain('/workspace')
  })

  test('TC-21.14 三栏可拖拽布局：Group+Panel+Separator渲染', async ({ page }) => {
    const project = await createProject(page, '21_14')
    await page.goto('/workspace')
    await page.getByText(project.name).click()

    // 三个Panel存在
    const leftPanel = page.locator('#workspace-left[data-panel]')
    const middlePanel = page.locator('#workspace-middle[data-panel]')
    const rightPanel = page.locator('#workspace-right[data-panel]')
    await expect(leftPanel).toBeVisible()
    await expect(middlePanel).toBeVisible()
    await expect(rightPanel).toBeVisible()

    // 两个Separator存在且可交互
    const leftSep = page.locator('#workspace-separator-left[data-separator]')
    const rightSep = page.locator('#workspace-separator-right[data-separator]')
    await expect(leftSep).toBeVisible()
    await expect(rightSep).toBeVisible()
    await expect(leftSep).toHaveAttribute('role', 'separator')
    await expect(rightSep).toHaveAttribute('role', 'separator')
  })

  test('TC-21.15 分隔条hover→变粗高亮，离开→恢复', async ({ page }) => {
    const project = await createProject(page, '21_15')
    await page.goto('/workspace')
    await page.getByText(project.name).click()

    const leftSep = page.locator('#workspace-separator-left[data-separator]')
    await expect(leftSep).toBeVisible()

    // 默认态：data-separator="inactive" + 1px细线border-r
    await expect(leftSep).toHaveAttribute('data-separator', 'inactive')
    await expect(leftSep).toHaveClass(/border-border/)
    await expect(leftSep).toHaveClass(/border-r\b/)

    // hover→库proximity检测→data-separator="hover"→CSS data variant激活
    // 使用page.mouse.move()绕过Playwright的hover()pointer event interception检查
    const sepBox = await leftSep.boundingBox()
    expect(sepBox).toBeTruthy()
    await page.mouse.move(sepBox!.x + sepBox!.width / 2, sepBox!.y + sepBox!.height / 2)
    await expect(leftSep).toHaveAttribute('data-separator', 'hover')
    await expect(leftSep).toHaveClass(/border-r-\[4px\]/)
    await expect(leftSep).toHaveClass(/border-primary/)

    // 移远→data-separator恢复inactive→CSS恢复默认态
    await page.mouse.move(0, 0)
    await expect(leftSep).toHaveAttribute('data-separator', 'inactive')
    await expect(leftSep).toHaveClass(/border-border/)
  })

  test('TC-21.16 分隔条拖拽中→保持高亮粗线，释放→恢复', async ({ page }) => {
    const project = await createProject(page, '21_16')
    await page.goto('/workspace')
    await page.getByText(project.name).click()

    const leftSep = page.locator('#workspace-separator-left[data-separator]')
    const leftPanel = page.locator('#workspace-left[data-panel]')
    await expect(leftSep).toBeVisible()

    const initialWidth = await leftPanel.evaluate(el => el.getBoundingClientRect().width)

    // 拖拽：移入→按下→右移→data-separator切换为"active"
    const sepBox = await leftSep.boundingBox()
    expect(sepBox).toBeTruthy()
    await page.mouse.move(sepBox.x + sepBox.width / 2, sepBox.y + sepBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(sepBox.x + sepBox.width / 2 + 20, sepBox.y + sepBox.height / 2, { steps: 5 })

    // 激活态：data-separator="active" + 2px粗线+border-primary
    await expect(leftSep).toHaveAttribute('data-separator', 'active')
    await expect(leftSep).toHaveClass(/border-r-\[4px\]/)
    await expect(leftSep).toHaveClass(/border-primary/)

    // 继续拖拽→效果持续保持
    await page.mouse.move(sepBox.x + sepBox.width / 2 + 80, sepBox.y + sepBox.height / 2, { steps: 10 })
    await expect(leftSep).toHaveAttribute('data-separator', 'active')

    // 左栏宽度确实变化了
    const draggedWidth = await leftPanel.evaluate(el => el.getBoundingClientRect().width)
    expect(Math.abs(draggedWidth - initialWidth)).toBeGreaterThan(5)

    // 释放鼠标+移远→data-separator恢复inactive或focus（拖拽后可能获焦点）
    await page.mouse.up()
    await page.mouse.move(0, 0)
    await expect(leftSep).toHaveAttribute('data-separator', /^(inactive|focus)$/)
    await expect(leftSep).toHaveClass(/border-border/)
  })

  test('TC-21.17 DiscussionPanel分隔条：hover+拖拽激活+释放恢复', async ({ page }) => {
    const project = await createProject(page, '21_17')
    const thread = await createThread(page, project.id, '21_17')
    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    const vSep = page.locator('#discussion-separator[data-separator]')
    await expect(vSep).toBeVisible()

    // 默认态：data-separator="inactive" + 1px细线border-b
    await expect(vSep).toHaveAttribute('data-separator', 'inactive')
    await expect(vSep).toHaveClass(/border-border/)
    await expect(vSep).toHaveClass(/border-b\b/)

    // hover→库proximity检测→data-separator="hover"→2px粗线+border-primary
    // 使用page.mouse.move()避免Playwright的hover()pointer event interception问题
    const vSepBox = await vSep.boundingBox()
    expect(vSepBox).toBeTruthy()
    await page.mouse.move(vSepBox.x + vSepBox.width / 2, vSepBox.y + vSepBox.height / 2)
    await expect(vSep).toHaveAttribute('data-separator', 'hover')
    await expect(vSep).toHaveClass(/border-b-\[4px\]/)
    await expect(vSep).toHaveClass(/border-primary/)

    // 拖拽：按下→下移→保持激活
    await page.mouse.down()
    await page.mouse.move(vSepBox.x + vSepBox.width / 2, vSepBox.y + vSepBox.height / 2 + 30, { steps: 5 })
    await expect(vSep).toHaveAttribute('data-separator', 'active')

    // 释放+移远→恢复默认态（可能获焦点）
    await page.mouse.up()
    await page.mouse.move(0, 0)
    await expect(vSep).toHaveAttribute('data-separator', /^(inactive|focus)$/)
    await expect(vSep).toHaveClass(/border-border/)
  })
})

test.describe('MVP-RE-9.x: 右栏文件编辑器 E2E', () => {
  test.beforeAll(async ({ request }) => {
    const adminResp = await request.post('/auth/register', {
      data: { username: ADMIN.username, password: ADMIN.password, display_name: ADMIN.displayName },
    })
    if (adminResp.status() === 409) {
      const loginResp = await request.post('/auth/login', {
        data: { username: ADMIN.username, password: ADMIN.password },
      })
      expect(loginResp.ok()).toBeTruthy()
      adminToken = (await loginResp.json()).access_token
    } else {
      expect(adminResp.ok()).toBeTruthy()
      const adminData = await adminResp.json()
      if (adminData.status === 'pending') {
        throw new Error('admin注册返回pending，DB有残留数据未清理')
      }
      adminToken = adminData.access_token
    }
  })

  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password)
  })

  test('MVP-RE-9.4: 浏览文件并编辑保存', async ({ page }) => {
    const project = await createProject(page, '9_4')
    const headers = await authHeaders(page)

    // 添加仓库（git init）
    const repoResp = await page.request.post(`/projects/${project.id}/repos`, {
      data: { name: 'test-repo' },
      headers,
    })
    expect(repoResp.ok(), `repos API returned ${repoResp.status()}: ${await repoResp.text()}`).toBeTruthy()

    // 创建测试文件
    const saveResp = await page.request.put(
      `/projects/${project.id}/repos/test-repo/files?path=hello.md`,
      { data: { content: '# Hello World' }, headers },
    )
    expect(saveResp.ok()).toBeTruthy()

    // 导航到 workspace 并选中项目
    await page.goto('/workspace')
    await page.getByText(project.name).click()

    // 验证右栏 Tab 栏存在
    const fileTab = page.getByRole('tab', { name: /文件/ })
    await expect(fileTab).toBeVisible()
    await expect(fileTab).toHaveAttribute('aria-selected', 'true')

    // 验证文件树中出现 hello.md
    const fileNode = page.getByText('hello.md')
    await expect(fileNode).toBeVisible({ timeout: 10000 })

    // 点击文件
    await fileNode.dblclick()

    // 验证 Monaco 编辑器加载（Monaco 渲染后编辑区域有 textarea）
    const editorArea = page.locator('.monaco-editor')
    await expect(editorArea).toBeVisible({ timeout: 10000 })

    // 保存后验证 git status 有变更
    // 直接通过 API 修改文件内容模拟编辑保存
    const editResp = await page.request.put(
      `/projects/${project.id}/repos/test-repo/files?path=hello.md`,
      { data: { content: '# Hello World\n\nEdited content' }, headers },
    )
    expect(editResp.ok()).toBeTruthy()

    // 验证 git status
    const statusResp = await page.request.get(
      `/projects/${project.id}/repos/test-repo/status`,
      { headers },
    )
    expect(statusResp.ok()).toBeTruthy()
    const status = await statusResp.json()
    expect(status.changes.length + status.staged.length).toBeGreaterThanOrEqual(1)
  })

  test('MVP-RE-9.5: Source Control 操作（diff+stage+commit）', async ({ page }) => {
    const project = await createProject(page, '9_5')
    const headers = await authHeaders(page)

    // 添加仓库并创建初始 commit
    const repoResp = await page.request.post(`/projects/${project.id}/repos`, {
      data: { name: 'sc-repo' },
      headers,
    })
    expect(repoResp.ok()).toBeTruthy()

    // 创建文件、stage、commit 初始版本
    await page.request.put(
      `/projects/${project.id}/repos/sc-repo/files?path=app.py`,
      { data: { content: 'print("v1")' }, headers },
    )
    await page.request.post(
      `/projects/${project.id}/repos/sc-repo/stage`,
      { data: { paths: ['app.py'] }, headers },
    )
    await page.request.post(
      `/projects/${project.id}/repos/sc-repo/commit`,
      { data: { message: 'initial' }, headers },
    )

    // 修改文件（制造变更）
    await page.request.put(
      `/projects/${project.id}/repos/sc-repo/files?path=app.py`,
      { data: { content: 'print("v2")' }, headers },
    )

    // 导航到 workspace 并选中项目
    await page.goto('/workspace')
    await page.getByText(project.name).click()

    // 切换到 Source Control 活动栏
    const scBtn = page.getByRole('button', { name: /source.?control/i })
    await expect(scBtn).toBeVisible({ timeout: 10000 })
    await scBtn.click()

    // 验证 Changes 分组中显示 app.py
    const changeFile = page.getByText('app.py')
    await expect(changeFile).toBeVisible({ timeout: 10000 })

    // 点击变更文件 → 主区域切换为 DiffEditor
    await changeFile.click()
    const diffEditor = page.locator('.monaco-diff-editor')
    await expect(diffEditor).toBeVisible({ timeout: 10000 })

    // 通过 API stage 文件
    const stageResp = await page.request.post(
      `/projects/${project.id}/repos/sc-repo/stage`,
      { data: { paths: ['app.py'] }, headers },
    )
    expect(stageResp.ok()).toBeTruthy()

    // 通过 API commit
    const commitResp = await page.request.post(
      `/projects/${project.id}/repos/sc-repo/commit`,
      { data: { message: 'update to v2' }, headers },
    )
    expect(commitResp.ok()).toBeTruthy()

    // 验证 commit 后 staged 清空
    const statusResp = await page.request.get(
      `/projects/${project.id}/repos/sc-repo/status`,
      { headers },
    )
    const status = await statusResp.json()
    expect(status.staged.length).toBe(0)
  })
})