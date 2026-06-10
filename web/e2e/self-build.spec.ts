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

    const messageInput = page.getByPlaceholder(/输入消息/)
    await messageInput.fill('这是我的观点')
    await page.getByRole('button', { name: /发送/ }).click()

    // 乐观更新：POST返回后立即显示，不需等SSE
    await expect(page.getByText('这是我的观点')).toBeVisible({ timeout: 5000 })
  })

  test('TC-21.3 验证点3：总结Agent产出摘要', async ({ page }) => {
    const project = await createProject(page, '21_3')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_3')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByRole('button', { name: /请求总结/ }).click()

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

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })

    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 15000 })
  })

  test('TC-21.5 验证点5：人类审批执行计划', async ({ page }) => {
    const project = await createProject(page, '21_5')
    await registerAgents(page, project.id)
    const thread = await createThread(page, project.id, '21_5')

    await page.goto('/workspace')
    await page.getByText(project.name).click()
    await page.getByText(thread.title).click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })

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

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
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

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
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

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()
    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })

    const outputs = await waitForOutputs(page, project.id)
    const headers = await authHeaders(page)

    await page.request.post(`/outputs/${outputs[0].id}/approve`, {
      data: { feedback: '通过审查' },
      headers,
    })

    const gitLogResp = await page.request.get(`/git/${project.id}/git-log`, { headers })
    expect(gitLogResp.ok()).toBeTruthy()
    const gitLog = await gitLogResp.json()
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

    const messageInput = page.getByPlaceholder(/输入消息/)
    await messageInput.fill('实时更新测试消息')
    await page.getByRole('button', { name: /发送/ }).click()
    // 乐观更新：POST返回后立即显示
    await expect(page.getByText('实时更新测试消息')).toBeVisible({ timeout: 5000 })

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 15000 })
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
})