const {chromium} = require(process.argv[2]);
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const crypto = require('node:crypto');

const info = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const output = info.output;
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitFor(check, what, timeout = 30000) {
  const started = Date.now();
  for (;;) {
    if (await check().catch(() => false)) return;
    if (Date.now() - started > timeout) throw new Error('等待超时：' + what);
    await sleep(200);
  }
}

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const posts = [];
  let foreign = 0;
  let taskId = null;
  let page = null;
  let stage = '启动浏览器';
  try {
    page = await browser.newPage({viewport: {width: 1530, height: 1150}});
    page.setDefaultTimeout(20000);
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.route('**/*', route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== info.base) {
        foreign++;
        return route.abort();
      }
      if (request.method() !== 'GET') posts.push({method: request.method(), path: url.pathname});
      return route.continue();
    });

    const taskPath = suffix => `/api/tasks/${taskId}${suffix}`;
    const idle = async () => {
      await waitFor(async () => await page.locator('.busy').count() === 0, '后台操作完成', 120000);
    };
    const waitPost = async (suffix, action) => {
      const expected = taskPath(suffix);
      const responsePromise = page.waitForResponse(response =>
        response.request().method() === 'POST' && new URL(response.url()).pathname === expected);
      await action();
      const response = await responsePromise;
      assert.equal(response.status(), 200, `${suffix} 返回 ${response.status()}`);
      return response;
    };
    const chooseStep = async label => {
      await page.locator('.steps button').filter({hasText: label}).click();
    };
    const sendMessage = async (text, expected) => {
      stage = '发送对话';
      await page.locator('.composer textarea').fill(text);
      await waitPost('/messages', () => page.locator('.composer button.send').click());
      await waitFor(async () =>
        await page.locator('.message-body').filter({hasText: expected}).count() > 0,
        '等待助手回复：' + expected, 90000);
      await idle();
    };

    stage = '打开本机页面';
    await page.goto(info.base, {waitUntil: 'networkidle'});

    stage = '新建任务弹窗';
    await page.getByRole('button', {name: '新建任务', exact: true}).click();
    const dialog = page.locator('[data-root-dialog]');
    await dialog.getByLabel('任务名称').fill(info.task_name);
    await dialog.locator('.typecard').filter({hasText: 'Chatflow'}).click();
    await dialog.getByLabel('新任务目标环境').selectOption('__unbound__');
    await dialog.locator('footer').getByRole('button', {name: '创建任务', exact: true}).click();
    await waitFor(async () => await dialog.count() === 0, '新建任务窗口关闭', 60000);

    stage = '读取本机任务并前置公开配置和样例';
    const listed = await page.request.get(info.base + '/api/tasks');
    assert.equal(listed.status(), 200);
    const tasks = await listed.json();
    assert.equal(tasks.length, 1, '临时目录中应只有界面创建的一个任务');
    const created = tasks[0];
    assert.equal(created.name, info.task_name);
    assert.equal(created.app_type, 'advanced-chat');
    assert.equal(created.environment_id, null);
    taskId = created.id;
    const configured = await page.request.patch(info.base + taskPath(''), {
      data: {configuration: info.configuration, expected_revision: created.revision},
    });
    assert.equal(configured.status(), 200);
    const seeded = await page.request.post(info.base + taskPath('/test-cases'), {
      data: {revision: (await configured.json()).revision, cases: info.cases},
    });
    assert.equal(seeded.status(), 200);
    const seededTask = await seeded.json();
    assert.equal(seededTask.test_cases.length, info.cases.length);

    stage = '重新载入并选择任务';
    await page.reload({waitUntil: 'networkidle'});
    await page.locator('.task-item').filter({hasText: info.task_name}).click();
    await waitFor(async () => await page.locator('.composer textarea').isEnabled(), '任务已载入');
    await page.screenshot({path: path.join(output, 'task-created.png')});

    stage = '首轮访谈';
    await sendMessage(info.opening, info.assistant_messages.opening);
    await page.locator('.intake-question').filter({hasText: info.assistant_messages.opening})
      .waitFor({timeout: 30000});

    stage = '提交完整需求';
    await sendMessage(info.requirements, info.assistant_messages.requirements);
    const confirmRequirements = page.getByRole('button', {name: '确认需求', exact: true});
    await waitFor(async () => await confirmRequirements.isEnabled(), '需求可确认', 60000);
    await waitPost('/confirm', () => confirmRequirements.click());
    await waitFor(async () =>
      await page.getByRole('button', {name: '重新确认', exact: true}).count() > 0, '需求已确认');
    await idle();

    stage = '请求模型生成原版流程';
    await chooseStep('流程');
    const generate = page.getByRole('button',
      {name: /请求模型生成流程建议|需要新方案时，请求模型重新生成/});
    await waitFor(async () => await generate.isEnabled(), '流程生成按钮可用');
    await waitPost('/plan/generate', () => generate.click());
    await waitFor(async () =>
      await page.locator('.alert.success').filter({hasText: '模型已返回流程方案'}).count() > 0,
      '原版流程已生成', 120000);
    await idle();

    stage = '确认原版配置与计划';
    await chooseStep('配置');
    const confirmConfiguration = page.getByRole('button', {name: '确认配置与计划', exact: true});
    await waitFor(async () => await confirmConfiguration.isEnabled(), '配置可确认', 60000);
    await waitPost('/confirm', () => confirmConfiguration.click());
    await waitFor(async () =>
      await page.getByRole('button', {name: '重新确认计划', exact: true}).count() > 0, '配置已确认');
    await idle();

    stage = '原版后台静态校验并构建';
    await chooseStep('构建');
    const buildOriginal = page.getByRole('button', {name: '请求后台静态校验并构建', exact: true});
    await waitFor(async () => await buildOriginal.isEnabled(), '构建按钮可用', 60000);
    await waitPost('/build', () => buildOriginal.click());
    await waitFor(async () =>
      await page.locator('.validation').filter({hasText: '静态检查通过'}).count() > 0,
      '原版静态检查通过', 60000);
    await idle();

    stage = '下载原版交付包';
    const originalFile = path.join(output, 'original.zip');
    const originalBundle = page.locator('.delivery-bundle-download')
      .getByRole('button', {name: '下载当前交付包（ZIP）', exact: true});
    await waitFor(async () => await originalBundle.isEnabled(), '原版交付包按钮可用', 60000);
    const [originalDownload] = await Promise.all([
      page.waitForEvent('download', {timeout: 60000}),
      originalBundle.click(),
    ]);
    await originalDownload.saveAs(originalFile);
    const originalMatch = originalDownload.suggestedFilename().match(/-r(\d+)-delivery\.zip$/);
    assert.ok(originalMatch, '原版包名应含修订号');
    const originalRevision = Number(originalMatch[1]);
    await page.screenshot({path: path.join(output, 'original-build.png')});

    stage = '发送自然语言改版请求';
    await chooseStep('需求');
    await sendMessage(info.request, info.assistant_messages.revision);

    stage = '请求改版流程候选';
    await chooseStep('流程');
    const regenerate = page.getByRole('button',
      {name: '需要新方案时，请求模型重新生成', exact: true});
    await waitFor(async () => await regenerate.isEnabled(), '改版生成按钮可用', 60000);
    await regenerate.click();
    const readCandidate = page.getByRole('button', {name: '读取保留流程候选原文', exact: true});
    await waitFor(async () => await readCandidate.count() > 0, '出现保留候选提示', 120000);
    await idle();
    await page.screenshot({path: path.join(output, 'replanning-candidate.png')});
    await readCandidate.click();
    const loadCandidate = page.getByRole('button', {name: '放入未保存流程草稿', exact: true});
    await waitFor(async () => await loadCandidate.isEnabled(), '候选可载入草稿', 60000);
    await loadCandidate.click();
    await waitFor(async () =>
      await page.locator('.alert.success').filter({hasText: '保留候选已放入未保存草稿'}).count() > 0,
      '候选已载入');

    stage = '后台校验并保存改版计划';
    const savePlan = page.getByRole('button', {name: '后台校验并保存计划', exact: true});
    await waitFor(async () => await savePlan.isEnabled(), '改版计划可保存', 60000);
    await waitPost('/plan', () => savePlan.click());
    await waitFor(async () => !(await savePlan.isEnabled().catch(() => false)), '改版计划已保存');
    await idle();

    stage = '重新确认改版需求';
    await chooseStep('需求');
    const confirmRequirementsAgain = page.getByRole('button', {name: '确认需求', exact: true});
    await waitFor(async () => await confirmRequirementsAgain.isEnabled(), '需求可再次确认', 60000);
    await waitPost('/confirm', () => confirmRequirementsAgain.click());
    await waitFor(async () =>
      await page.getByRole('button', {name: '重新确认', exact: true}).count() > 0, '需求已重新确认');

    stage = '通过完整样例JSON编辑器更新 no-hit 期望';
    await chooseStep('运行');
    const editor = page.locator('.case-json-editor');
    await editor.waitFor();
    await editor.locator('summary').filter({hasText: '展开完整JSON编辑'}).click();
    const editorArea = editor.getByLabel('完整样例JSON原文', {exact: true});
    await waitFor(async () => await editorArea.isEnabled(), '样例原文可编辑', 30000);
    const cases = JSON.parse(await editorArea.inputValue());
    const noHit = cases.find(row => row.id === 'no-hit');
    assert.ok(noHit, '当前保存样例应包含 no-hit');
    noHit.expectation.expected = info.new_reply;
    await editorArea.fill(JSON.stringify(cases, null, 2));
    await waitPost('/test-cases/editor', () =>
      editor.getByRole('button', {name: '保存完整JSON', exact: true}).click());
    await waitFor(async () =>
      await page.locator('.alert.success').filter({hasText: '完整样例JSON已保存'}).count() > 0,
      '样例已保存', 60000);
    await idle();
    await page.screenshot({path: path.join(output, 'case-json-updated.png')});

    stage = '样例变更后重新确认需求并保存计划';
    await chooseStep('需求');
    const confirmAfterCases = page.getByRole('button', {name: '确认需求', exact: true});
    await waitFor(async () => await confirmAfterCases.isEnabled(), '需求可确认', 60000);
    await waitPost('/confirm', () => confirmAfterCases.click());
    await waitFor(async () =>
      await page.getByRole('button', {name: '重新确认', exact: true}).count() > 0, '需求已确认');
    await chooseStep('流程');
    const saveStalePlan = page.getByRole('button', {name: '后台校验并保存计划', exact: true});
    await waitFor(async () => await saveStalePlan.isEnabled(), '过期计划可保存', 60000);
    await waitPost('/plan', () => saveStalePlan.click());
    await waitFor(async () => !(await saveStalePlan.isEnabled().catch(() => false)), '计划已保存');
    await idle();

    stage = '确认改版配置';
    await chooseStep('配置');
    const confirmModifiedConfiguration = page.getByRole('button',
      {name: '确认配置与计划', exact: true});
    await waitFor(async () => await confirmModifiedConfiguration.isEnabled(), '改版配置可确认', 60000);
    await waitPost('/confirm', () => confirmModifiedConfiguration.click());
    await waitFor(async () =>
      await page.getByRole('button', {name: '重新确认计划', exact: true}).count() > 0, '改版配置已确认');
    await idle();

    stage = '改版后台静态校验并构建';
    await chooseStep('构建');
    const buildModified = page.getByRole('button', {name: '请求后台静态校验并构建', exact: true});
    await waitFor(async () => await buildModified.isEnabled(), '改版构建按钮可用', 60000);
    await waitPost('/build', () => buildModified.click());
    await waitFor(async () =>
      await page.locator('.validation').filter({hasText: '静态检查通过'}).count() > 0,
      '改版静态检查通过', 60000);
    await idle();

    stage = '下载改版交付包';
    const modifiedFile = path.join(output, 'modified.zip');
    const modifiedBundle = page.locator('.delivery-bundle-download')
      .getByRole('button', {name: '下载当前交付包（ZIP）', exact: true});
    await waitFor(async () => await modifiedBundle.isEnabled(), '改版交付包按钮可用', 60000);
    const [modifiedDownload] = await Promise.all([
      page.waitForEvent('download', {timeout: 60000}),
      modifiedBundle.click(),
    ]);
    await modifiedDownload.saveAs(modifiedFile);
    const modifiedMatch = modifiedDownload.suggestedFilename().match(/-r(\d+)-delivery\.zip$/);
    assert.ok(modifiedMatch, '改版包名应含修订号');
    const modifiedRevision = Number(modifiedMatch[1]);
    await page.screenshot({path: path.join(output, 'modified-build.png')});

    assert.ok(modifiedRevision > originalRevision, '改版修订应大于原版修订');
    assert.notEqual(sha256(originalFile), sha256(modifiedFile), '两版交付包字节应不同');

    const paths = posts.map(row => row.path);
    for (const suffix of ['/messages', '/plan/generate', '/confirm', '/plan', '/build', '/test-cases/editor']) {
      assert.ok(paths.some(value => value.endsWith(suffix)), '界面没有发起 ' + suffix);
    }
    assert.deepEqual(pageErrors, []);
    assert.equal(foreign, 0);
    const proof = {
      state: 'passed',
      ui_flow: 'static_two_revisions',
      task_created_from_ui: true,
      preseed_api_requests: ['GET /api/tasks', 'PATCH /api/tasks/{id}', 'POST /api/tasks/{id}/test-cases'],
      ui_posts: [...new Set(paths)],
      original_revision: originalRevision,
      modified_revision: modifiedRevision,
      zip_revisions_differ: originalRevision !== modifiedRevision,
      original_zip_sha256: sha256(originalFile),
      modified_zip_sha256: sha256(modifiedFile),
      zip_bytes_differ: sha256(originalFile) !== sha256(modifiedFile),
      pageerrors: pageErrors.length,
      foreign_requests: foreign,
    };
    fs.writeFileSync(path.join(output, 'proof.json'), JSON.stringify(proof, null, 2));
    console.log(JSON.stringify({state: 'passed', original_revision: originalRevision,
      modified_revision: modifiedRevision}));
  } catch (error) {
    console.error('界面流程失败于：' + stage);
    if (page) {
      try {
        await page.screenshot({path: path.join(output, 'failure.png')});
      } catch {}
    }
    console.error(error.stack || String(error));
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
