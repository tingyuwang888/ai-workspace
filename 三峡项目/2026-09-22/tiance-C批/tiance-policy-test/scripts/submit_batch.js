/**
 * 天策策略测试 — 批量提交模板
 *
 * 使用方式：
 *   1. 读取本文件全部内容
 *   2. 替换以下占位符（{{...}}）：
 *      - {{POLICY_CODE}}    — 策略编码，来自 strategies/{policyCode}.json
 *      - {{PLATFORM_GUARD}} — 本次平台门禁报告 JSON（ok/platform/policyNameResolution）
 *      - {{POLICY_VERSION}} — 策略版本号
 *      - {{BIZ_TYPE}}       — 业务类型
 *      - {{TEST_CASES}}     — 测试用例 JSON 数组（已序列化为字符串）
 *   3. 将替换后的完整 JS 代码传入浏览器 javascript_tool 执行
 *   4. 设置 timeout: 120 秒
 *
 * 返回格式：JSON 字符串，数组元素：
 *   { id, exp, ok, rs, dt, dtCode, uuid, token, err }
 *   - rs="2" 表示执行成功，rs="-2" 表示执行失败
 *   - ok=false 且 err="SESSION_EXPIRED" 表示会话过期，需重新登录
 *   - ok=false 且 err="RETRY_EXHAUSTED: ..." 表示重试耗尽
 *
 * 可调参数（直接修改下方常量）：
 *   MAX_RETRY   — 单条用例最大重试次数（默认 2）
 *   BATCH_DELAY — 用例间等待毫秒（默认 800，防止数据源缓存干扰）
 *   RETRY_DELAY — 重试间等待毫秒（默认 2000）
 */
(async function(){
  var csrf = sessionStorage.getItem('_csrf_')
    || decodeURIComponent((document.cookie.match(/_csrf_=([^;]+)/)||[])[1]||'');
  if (!csrf) {
    return JSON.stringify([{
      id: '', ok: false, rs: '', err: 'CSRF_MISSING'
    }]);
  }

  /* ── 身份来自配置，显示名称来自本次已通过的平台门禁 ── */
  var POLICY_CODE    = '{{POLICY_CODE}}';
  var POLICY_VERSION = '{{POLICY_VERSION}}';
  var BIZ_TYPE       = '{{BIZ_TYPE}}';
  var guard = {{PLATFORM_GUARD}};
  var platform = guard && guard.platform;
  if (!guard || guard.ok !== true || !platform
      || String(platform.policyCode) !== POLICY_CODE
      || String(platform.policyVersion) !== POLICY_VERSION
      || String(platform.bizType) !== BIZ_TYPE
      || typeof platform.policyName !== 'string' || !platform.policyName.trim()) {
    return JSON.stringify([{id: '', ok: false, rs: '', err: 'PLATFORM_IDENTITY_OR_NAME_INVALID'}]);
  }
  var POLICY_NAME = platform.policyName;
  var nameResolution = guard.policyNameResolution || {
    local: null, platform: POLICY_NAME, submitted: POLICY_NAME, source: 'platform', changed: null
  };
  if (nameResolution.platform !== POLICY_NAME || nameResolution.submitted !== POLICY_NAME) {
    return JSON.stringify([{id: '', ok: false, rs: '', err: 'PLATFORM_NAME_RESOLUTION_INVALID'}]);
  }

  /* ── 测试用例数组（JSON 格式） ── */
  var cases = {{TEST_CASES}};

  /* ── 可调参数 ── */
  var MAX_RETRY   = 2;
  var BATCH_DELAY = 800;
  var RETRY_DELAY = 2000;

  /* ── 提交逻辑 ── */
  var results = [];

  for (var i = 0; i < cases.length; i++) {
    var c = cases[i];
    var body = {
      policyCode: POLICY_CODE, policyName: POLICY_NAME,
      policyVersion: POLICY_VERSION, bizType: BIZ_TYPE,
      testcase: '1', customParams: '{}', params: JSON.stringify(c.params)
    };
    var completed = false;
    var lastError = '';
    for (var retry = 0; retry <= MAX_RETRY && !completed; retry++) {
      try {
        var resp = await fetch('/noahApi/lab/policytest/create', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'X-Cf-Random': csrf, '_csrf_': csrf
          },
          body: new URLSearchParams(body).toString()
        });
        if (resp.status === 401) {
          results.push({ id: c.id, ok: false, err: 'SESSION_EXPIRED',
            policyName: POLICY_NAME, policyNameResolution: nameResolution });
          return JSON.stringify(results);
        }
        if (!resp.ok) {
          throw new Error('HTTP_' + resp.status);
        }
        var d = await resp.json(), dd = d.data || {};
        if (!d.success) {
          throw new Error(
            'API_FAILED: ' + (d.message || d.msg || dd.errorMsg || 'unknown')
          );
        }
        if (String(dd.runStatus || '') === '-2') {
          throw new Error(
            'RUN_FAILED: ' + (dd.errorMsg || 'runStatus=-2')
          );
        }
        results.push({
          id: c.id, exp: c.expected,
          policyName: POLICY_NAME, policyNameResolution: nameResolution,
          ok: String(dd.runStatus || '') === '2',
          rs: dd.runStatus || '', dt: dd.policyDealTypeName || '',
          dtCode: dd.policyDealType || '', uuid: dd.uuid || '',
          token: dd.token || '', err: dd.errorMsg || ''
        });
        completed = true;
      } catch(e) {
        lastError = e.message;
        if (retry < MAX_RETRY) {
          await new Promise(function(r) { setTimeout(r, RETRY_DELAY); });
        }
      }
    }
    if (!completed) {
      results.push({
        id: c.id, exp: c.expected, ok: false, rs: '',
        policyName: POLICY_NAME, policyNameResolution: nameResolution,
        dt: '', dtCode: '', uuid: '', token: '',
        err: 'RETRY_EXHAUSTED: ' + lastError
      });
    }
    await new Promise(function(r) { setTimeout(r, BATCH_DELAY); });
  }
  return JSON.stringify(results);
})()
