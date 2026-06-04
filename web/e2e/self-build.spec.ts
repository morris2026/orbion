import { test, expect } from '@playwright/test'

/** 辅助：从localStorage获取JWT token */
async function getToken(page): string | null {
  return await page.evaluate(() => localStorage.getItem('orbion_token'))
}

/** 辅助：带认证的API请求headers */
async function authHeaders(page) {
  const token = await getToken(page)
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

/** 辅助：注册+登录获取JWT */
async function registerAndLogin(page, username = `e2e-admin-${Date.now()}`, displayName = 'E2E Admin') {
  await page.goto('/')
  await page.getByRole('button', { name: /注册/ }).click()
  await page.getByLabel(/用户名/).fill(username)
  await page.getByLabel(/密码/).fill('password12345678')
  await page.getByLabel(/显示名称/).fill(displayName)
  await page.getByRole('button', { name: /提交注册/ }).click()
  await page.waitForURL(/\/workspace/)
}

/** 辅助：注册+登录但不加入项目（用于负面路径测试） */
async function registerOutsider(page, username = `e2e-outsider-${Date.now()}`, displayName = 'E2E Outsider') {
  await page.goto('/')
  await page.getByRole('button', { name: /注册/ }).click()
  await page.getByLabel(/用户名/).fill(username)
  await page.getByLabel(/密码/).fill('password12345678')
  await page.getByLabel(/显示名称/).fill(displayName)
  await page.getByRole('button', { name: /提交注册/ }).click()
  await page.waitForURL(/\/workspace/)
}

/** 辅助：创建项目 */
async function createProject(page, name = 'E2E测试项目') {
  const headers = await authHeaders(page)
  const response = await page.request.post('/projects', {
    data: { name, description: 'E2E测试项目描述' },
    headers,
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
}

/** 辅助：创建线程 */
async function createThread(page, projectId, title = 'E2E测试线程') {
  const headers = await authHeaders(page)
  const response = await page.request.post(`/projects/${projectId}/threads`, {
    data: { title, type: 'discussion' },
    headers,
  })
  expect(response.ok()).toBeTruthy()
  return await response.json()
}

test.describe('自我构建9点验证', () => {

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page)
  })

  test('TC-21.1 验证点1：创建项目+添加成员+创建线程', async ({ page }) => {
    const project = await createProject(page)
    expect(project.id).toBeTruthy()

    // 创建者自动成为Owner — 通过成员列表API验证
    const headers = await authHeaders(page)
    const membersResp = await page.request.get(`/projects/${project.id}/members`, { headers })
    expect(membersResp.ok()).toBeTruthy()
    const members = await membersResp.json()
    const ownerMembers = members.filter((m) => m.role === 'owner')
    expect(ownerMembers.length).toBeGreaterThanOrEqual(1)

    // 创建线程
    const thread = await createThread(page, project.id)
    expect(thread.id).toBeTruthy()

    // 前端显示
    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await expect(page.getByText('E2E测试线程')).toBeVisible()
  })

  test('TC-21.2 验证点2：人类在讨论线程中发言', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    const messageInput = page.getByPlaceholder(/输入消息/)
    await messageInput.fill('这是我的观点')
    await page.getByRole('button', { name: /发送/ }).click()

    await expect(page.getByText('这是我的观点')).toBeVisible()
  })

  test('TC-21.3 验证点3：总结Agent产出摘要', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

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
    // 摘要内容含consensus_points
    const summaryContent = summaryMessages[0].content
    expect(summaryContent).toContain('consensus_points')
  })

  test('TC-21.4 验证点4：分解Agent产出执行计划', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })

    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 15000 })
  })

  test('TC-21.5 验证点5：人类审批执行计划', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })

    // 审批前：批准按钮可见
    const approveBtn = page.getByRole('button', { name: /批准/ })
    await expect(approveBtn).toBeVisible()

    await approveBtn.click()

    // 审批后：计划状态变为approved，审批按钮消失
    await expect(page.getByText('approved')).toBeVisible({ timeout: 5000 })
    await expect(approveBtn).not.toBeVisible()
  })

  test('TC-21.6 验证点6：执行Agent产出代码diff', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()

    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })
  })

  test('TC-21.7 验证点7：人类审查diff → Approve', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()
    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })

    // 必须有产出才能审批
    const headers = await authHeaders(page)
    const outputsResp = await page.request.get(`/projects/${project.id}/outputs`, { headers })
    expect(outputsResp.ok()).toBeTruthy()
    const outputs = await outputsResp.json()
    expect(outputs.length).toBeGreaterThan(0)

    const approveResp = await page.request.post(`/outputs/${outputs[0].id}/approve`, {
      data: { feedback: '看起来不错' },
      headers,
    })
    expect(approveResp.ok()).toBeTruthy()
    const approveData = await approveResp.json()
    expect(approveData.status).toBe('approved')
  })

  test('TC-21.8 验证点8：审批通过 → Git commit', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 20000 })
    await page.getByRole('button', { name: /批准/ }).click()
    await expect(page.getByText(/--- a/)).toBeVisible({ timeout: 20000 })

    const headers = await authHeaders(page)
    const outputsResp = await page.request.get(`/projects/${project.id}/outputs`, { headers })
    expect(outputsResp.ok()).toBeTruthy()
    const outputs = await outputsResp.json()
    expect(outputs.length).toBeGreaterThan(0)

    await page.request.post(`/outputs/${outputs[0].id}/approve`, {
      data: { feedback: '通过审查' },
      headers,
    })

    // 验证git commit：通过git-log API确认有新commit
    const gitLogResp = await page.request.get(`/git/${project.id}/git-log`, { headers })
    expect(gitLogResp.ok()).toBeTruthy()
    const gitLog = await gitLogResp.json()
    expect(gitLog.length).toBeGreaterThanOrEqual(2)
    // 最新commit消息含产出信息
    const latestCommit = gitLog[0]
    expect(latestCommit.message).toContain('approve')
  })

  test('TC-21.9 验证点9：三栏实时展示+SSE推送', async ({ page }) => {
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    await page.goto('/workspace')
    await page.getByText('E2E测试项目').click()
    await page.getByText('E2E测试线程').click()

    // 发送消息→中栏自动更新
    const messageInput = page.getByPlaceholder(/输入消息/)
    await messageInput.fill('实时更新测试消息')
    await page.getByRole('button', { name: /发送/ }).click()
    await expect(page.getByText('实时更新测试消息')).toBeVisible()

    // 请求总结→中栏+右栏自动更新（无需刷新）
    await page.getByRole('button', { name: /请求总结/ }).click()
    await expect(page.getByText(/共识/)).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/计划/)).toBeVisible({ timeout: 15000 })
  })

  test('TC-21.10 负面路径：无JWT→受保护端点返回401', async ({ page }) => {
    // 不带Authorization header请求受保护端点
    const resp = await page.request.post('/projects', {
      data: { name: '未认证项目', description: '不应创建' },
    })
    expect(resp.status()).toBe(401)
  })

  test('TC-21.11 负面路径：非成员→发送消息返回403', async ({ page }) => {
    // Owner创建项目+线程
    const project = await createProject(page)
    const thread = await createThread(page, project.id)

    // Outsider注册并登录
    await registerOutsider(page, `e2e-outsider-403-${Date.now()}`, 'E2E Outsider')
    const outsiderHeaders = await authHeaders(page)

    // Outsider尝试在Owner的线程发消息→403
    const resp = await page.request.post(`/threads/${thread.id}/messages`, {
      data: { content: '非成员消息' },
      headers: outsiderHeaders,
    })
    expect(resp.status()).toBe(403)
  })
})