const app = document.getElementById('app');
const drawer = document.getElementById('drawer');
const toast = document.getElementById('toast');
const routes = ['overview', 'ask', 'data', 'retrieval', 'evaluation', 'delivery'];
let DATA = null;
function preferredLanguage() {
  try { return localStorage.getItem('dsc5003.lang') === 'zh' ? 'zh' : 'en'; }
  catch { return 'en'; }
}
const healthCommand = () => `curl "${window.location.origin}/api/health"`;
let state = { route: 'overview', f1Result: null, f1Live: false, f1Topic: '', f2Tab: 'quality', kbTopic: 'all', f3Mode: 'faiss', sqlId: 'Q1', lang: preferredLanguage() };

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const safeUrl = (value) => /^https?:\/\//i.test(value || '') ? value : '#';
const num = (value) => Number(value || 0).toLocaleString('en-US');
const shortSHA = (value) => String(value || '').slice(0, 8);
const fmtMs = (value) => `${num(value)} ms`;
const fmtPct = (value) => `${Math.round(Number(value || 0) * 100)}%`;

function showToast(message) {
  toast.textContent = state.lang === 'zh' ? (typeof translateCore === 'function' ? translateCore(message) : message) : message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3200);
}

function pageHead(eyebrow, title, lede, asideTitle, asideBody, asideCode) {
  return `<section class="page-head">
    <div><div class="eyebrow">${esc(eyebrow)}</div><h1>${title}</h1><p class="lede">${lede}</p></div>
    <aside class="head-aside"><strong>${esc(asideTitle)}</strong>${esc(asideBody)}${asideCode ? `<span class="mono">${esc(asideCode)}</span>` : ''}</aside>
  </section>`;
}

function footer(nextLabel, nextRoute) {
  return `<div class="footer"><span>Frozen evidence, not a live model claim · prepared 21 Nov 2026</span><span>DSC5003 · CityUHK · F1–F5</span></div>
  <div class="pager"><span>Use the tabs above to move through the evidence chain.</span><span>Next <b>${esc(nextLabel)}</b> → ${esc(nextRoute)}</span></div>`;
}

function statusClass(status) {
  if (['answered', 'evidence_sufficient', 'ok'].includes(status)) return 'status';
  if (['clarify', 'abstained', 'no_evidence', 'out_of_scope', 'invalid_input', 'insufficient_evidence', 'stale_evidence', 'draft_retrieval_only', 'answer_incomplete', 'answer_unsupported', 'context_limit'].includes(status)) return 'status warn';
  if (['generation_error', 'invalid_response', 'config_error', 'source_mismatch', 'retrieval_error', 'error'].includes(status)) return 'status bad';
  return 'status neutral';
}

function citationHTML(citation) {
  const sid = citation.source_id || citation.id || 'S';
  return `<button class="citation" data-source="${encodeURIComponent(JSON.stringify(citation))}">
    <span class="source-id">${esc(sid)}</span><span><strong>${esc(citation.title || 'Evidence source')}</strong><small>${esc(citation.url || citation.doc_id || '')}</small></span>
  </button>`;
}

function resultRows(hits, mode) {
  return hits.map((hit, index) => `<button class="result-row ${hit.display_title && hit.display_title.includes('off-topic') ? 'off-topic' : ''}" data-source="${encodeURIComponent(JSON.stringify(hit))}">
    <span class="rank">${String(index + 1).padStart(2, '0')}</span>
    <span class="score">${Number(hit.score).toFixed(4)}</span>
    <span><strong>${esc(hit.display_title || hit.title)}</strong><small>${esc(hit.topic || '')} · ${esc(hit.chunk_id || hit.url || '')}</small></span>
    <span class="chip ${mode === 'rerank' ? 'amber' : 'neutral'}">${mode === 'rerank' ? 'RERANK' : 'FAISS'}</span>
  </button>`).join('');
}

function statPills(items) {
  return items.map(([label, value]) => `<span class="meta-pill">${esc(label)}<b>${esc(value)}</b></span>`).join('');
}

const TOPIC_OPTIONS = [
  ['fees', 'Tuition & payment', '学费与缴费'],
  ['library', 'Library', '图书馆'],
  ['scholarship', 'Scholarships', '奖学金'],
  ['admission', 'Admission', '申请'],
  ['visa', 'Visa', '签证'],
  ['registration', 'Registration', '注册'],
  ['residence', 'Student residence', '宿舍'],
  ['calendar', 'Calendar', '校历'],
];

const F1_MODE_META = {
  'live-llm-reviewed': ['LIVE MODEL + REVIEW', '实时模型 + 证据复核', 'blue'],
  'live-llm': ['LIVE MODEL', '实时模型', 'blue'],
  'offline-extractive': ['OFFLINE EXTRACTIVE', '离线摘录', 'neutral'],
  'clarify': ['CLARIFY', '需要澄清', 'amber'],
  'out_of_scope': ['OUT OF SCOPE', '超出范围', 'amber'],
  'recorded': ['RECORDED N7 REPLAY', '已记录N7回放', 'neutral'],
  'synthetic': ['SYNTHETIC WIRING', '合成接线', 'amber'],
};

const SCOPE_ZH_TEXT = '范围：索引只覆盖8个配置主题下的159篇城大学生服务页面（申请、签证、注册、宿舍、学费、奖学金、图书馆、校历），不是城大网站全量，也不是通用助手。';
const SCOPE_EN_TEXT = 'Scope: 159 CityUHK student-services pages in 8 configured topics (admission, visa, registration, residence, fees, scholarships, library, calendar). It is not the whole CityUHK website and not a general-purpose assistant.';
const OPTION_ZH = {
  'Admission': '入学申请', 'Scholarship': '奖学金', 'Student residence': '学生宿舍', 'Student visa': '学生签证',
  'Tuition / student account': '学费/学生账户退款', 'Admission deposit': '录取留位费退款',
  'Hostel / hall fees': '宿舍费退款', 'Course add/drop': '课程退选退款'
};
function displayScope(text) {
  if (state.lang === 'zh' && /^Scope:/.test(text)) return SCOPE_ZH_TEXT;
  if (state.lang !== 'zh' && /^范围：/.test(text)) return SCOPE_EN_TEXT;
  return text;
}
function displayOption(label) { return state.lang === 'zh' ? (OPTION_ZH[label] || label) : label; }

function f1ModeMeta(result, live) {
  const mode = result.mode || (live ? 'synthetic' : 'recorded');
  const meta = F1_MODE_META[mode] || ['EVIDENCE ANSWER', '证据问答', 'neutral'];
  return {mode, en: meta[0], zh: meta[1], tone: meta[2]};
}

function inlineCitations(html) {
  return html.replace(/\[(S\d+)\]/g, '<button class="inline-cite" data-cite="$1">$1</button>');
}

function answerBlockHTML(result, live) {
  const answer = result.answer || '';
  if (!answer) {
    const text = live
      ? 'No answer text was published for this status. Read the status, trace and citations instead.'
      : 'Answer text is intentionally withheld from this public replay. The run summary keeps the status, latency, citation IDs and call counts; no policy answer is re-created for the demo.';
    return `<div class="answer-box withheld"><p><b>${state.lang === 'zh' ? '这类结果不发布答案正文。' : 'This run does not publish answer text.'}</b></p><p>${esc(text)}</p></div>`;
  }
  const blocks = answer.split(/\n{2,}/).filter(block => block.trim());
  return `<div class="answer-box">${blocks.map(block => {
    const text = block.trim();
    if (text.startsWith('- ')) return `<div class="answer-point">${inlineCitations(esc(text.slice(2)))}</div>`;
    if (/^(Note:|说明：)/.test(text)) return `<p class="answer-note">${inlineCitations(esc(text))}</p>`;
    return `<p>${inlineCitations(esc(text))}</p>`;
  }).join('')}</div>`;
}

function statusLabel(status) {
  const labels = {
    answered: ['answered', '已回答'], clarify: ['clarify', '需要澄清'],
    abstained: ['abstained', '无法回答'], out_of_scope: ['out of scope', '超出范围'],
    no_evidence: ['no evidence', '无证据'], invalid_input: ['invalid input', '输入无效'],
    generation_error: ['generation error', '生成失败'], invalid_response: ['invalid response', '回答格式无效'],
    retrieval_error: ['retrieval error', '检索失败'], source_mismatch: ['source mismatch', '来源版本不一致'],
    error: ['error', '错误'],
  };
  const pair = labels[status] || [status, status];
  return state.lang === 'zh' ? pair[1] : pair[0];
}

function reviewLabel(verdict) {
  const labels = {
    pass: ['pass', '通过'], revise: ['revise', '已修订'], reject: ['reject', '拒绝'],
    unavailable: ['unavailable', '未运行'], invalid: ['invalid verdict', '复核结论无效'],
  };
  const pair = labels[verdict] || [verdict, verdict];
  return state.lang === 'zh' ? pair[1] : pair[0];
}

function wiringBlockHTML(result) {
  const raw = result.answer || '';
  return `<div class="answer-box withheld"><p><b>${state.lang === 'zh' ? '接线检查通过。' : 'Wiring check passed.'}</b></p><p>${state.lang === 'zh' ? '界面成功调用R05并收到响应；返回文本是合成夹具，不作为政策答案展示。' : 'The UI reached R05 and received a response. The returned text is a synthetic fixture; it is not displayed as a policy answer.'}</p>${raw ? `<details class="raw-fixture"><summary>${state.lang === 'zh' ? '查看原始夹具文本（仅供核对）' : 'Show raw fixture text (inspection only)'}</summary><p class="mono small">${esc(raw)}</p></details>` : ''}</div>`;
}

function askResultHTML(result, live, data) {
  const citations = result.citations || [];
  const roundsCount = Array.isArray(result.retrieval_rounds) ? result.retrieval_rounds.length : Number(result.retrieval_rounds || 0);
  const toolEvents = Array.isArray(result.tool_calls) ? result.tool_calls.length : 0;
  const modelCalls = Number(result.llm_calls || 0);
  const tokens = result.usage && result.usage.total_tokens ? result.usage.total_tokens : result.total_tokens;
  const mode = f1ModeMeta(result, live);
  const review = result.review;
  const clarify = result.clarify_options || [];
  const warnings = result.warnings || [];
  const isSynthetic = result.mode === 'synthetic';
  const answerBlock = isSynthetic ? wiringBlockHTML(result) : answerBlockHTML(result, live);
  const scope = displayScope(result.scope_note || '');
  const status = isSynthetic ? (state.lang === 'zh' ? '接线通过' : 'wiring ok') : statusLabel(result.status);
  const statusTone = isSynthetic ? 'status' : statusClass(result.status);
  const clarifyBlock = clarify.length ? `<div class="clarify-block"><div class="eyebrow">${state.lang === 'zh' ? '请选择下一步' : 'Choose the next step'}</div><p>${state.lang === 'zh' ? '点一个选项会带着更具体的问题重新检索。' : 'Pick one option to re-run the retrieval with a more specific question.'}</p><div class="clarify-options">${clarify.map(option => `<button class="clarify-option" data-clarify="${esc(option.query)}">${esc(displayOption(option.label))}</button>`).join('')}</div></div>` : '';
  const reviewBlock = review ? `<div class="review-box ${review.verdict === 'pass' ? 'pass' : review.verdict === 'reject' ? 'reject' : 'warn'}"><div class="eyebrow">${state.lang === 'zh' ? '独立证据复核' : 'Independent evidence review'}</div><b>${esc(reviewLabel(review.verdict))}</b>${review.used_revision ? ` <span class="micro">${state.lang === 'zh' ? '下方答案采用复核后的版本' : 'answer below uses the revised version'}</span>` : ''}${review.issues && review.issues.length ? `<ul>${review.issues.map(issue => `<li>${esc(issue)}</li>`).join('')}</ul>` : `<p class="micro" style="margin:6px 0 0">${state.lang === 'zh' ? '未发现需要修改的重大问题。' : 'No material issue remained.'}</p>`}</div>` : '';
  const warningBlock = warnings.length ? `<div class="notice amber" style="margin-top:12px">${warnings.map(w => esc(w)).join('<br>')}</div>` : '';
  const transport = live && result._transport ? `<div class="notice" style="margin-top:12px">Transport: ${esc(result._transport.backend)} · exit ${esc(result._transport.exit_code)} · ${esc(result._transport.command)}</div>` : '';
  return `<div class="result-intro"><div><div class="eyebrow">${state.lang === 'zh' ? mode.zh : mode.en}</div><h2>${esc(result.question)}</h2><span class="${statusTone}">${esc(status)}${result.stop_reason && !isSynthetic ? ` · ${esc(result.stop_reason)}` : ''}</span></div><span class="chip ${mode.tone}">${esc(state.lang === 'zh' ? mode.zh : mode.en)}</span></div>
  <div class="run-meta">${statPills([
    ['Latency', result.latency_ms ? fmtMs(result.latency_ms) : '—'],
    ['Retrieval rounds', roundsCount || '—'],
    ['Model calls', modelCalls || '—'],
    ['Tokens', tokens ? num(tokens) : '—']
  ])}</div>
  ${answerBlock}
  ${clarifyBlock}
  ${reviewBlock}
  ${scope ? `<div class="scope-line">${esc(scope)}</div>` : ''}
  ${result.note ? `<div class="notice">${esc(result.note)}</div>` : ''}
  ${warningBlock}
  ${transport}
  <div class="card-title" style="margin-top:20px"><div><div class="eyebrow">Trace</div><h3>What the run actually recorded</h3></div><span class="badge">${citations.length} citations</span></div>
  <div class="timeline">
    <div class="timeline-item"><strong>Input received</strong><span>${esc(result.question)}</span></div>
    <div class="timeline-item"><strong>${state.lang === 'zh' ? '意图与范围' : 'Intent and scope'}</strong><span>${result.topic_label || (result.topics && result.topics.length ? result.topics.join(', ') : (state.lang === 'zh' ? '未识别主题' : 'no topic detected'))}${result.language ? ` · ${result.language}` : ''} · ${state.lang === 'zh' ? mode.zh : mode.en}</span></div>
    <div class="timeline-item"><strong>${state.lang === 'zh' ? '检索' : 'Retrieval'}</strong><span>${isSynthetic ? (state.lang === 'zh' ? `合成夹具返回${roundsCount}轮、${toolEvents || 0}个工具事件；没有使用真实索引检索。` : `Synthetic fixture returned ${roundsCount} round(s) and ${toolEvents || 0} tool event(s); the real index was not used.`) : roundsCount ? (state.lang === 'zh' ? `${roundsCount} 轮可见检索返回Top-5候选；记录${toolEvents || 0}次工具事件。` : `${roundsCount} visible retrieval round(s) returned Top-5 candidates; ${toolEvents || 0} tool event(s) recorded.`) : (state.lang === 'zh' ? '此状态没有执行检索。' : 'No retrieval was executed for this status.')}</span></div>
    <div class="timeline-item"><strong>${state.lang === 'zh' ? '生成与复核' : 'Generation and review'}</strong><span>${isSynthetic ? (state.lang === 'zh' ? '接线检查没有模型调用；夹具文本不属于回答质量证据。' : 'No model call in the wiring check; the fixture is not answer-quality evidence.') : modelCalls ? (state.lang === 'zh' ? `记录${modelCalls}次模型调用${review ? `；独立复核：${reviewLabel(review.verdict)}` : ''}。` : `${modelCalls} model call(s) recorded${review ? `; independent review: ${reviewLabel(review.verdict)}` : ''}.`) : (state.lang === 'zh' ? '没有模型调用；这是离线摘录、澄清或范围拒答。' : 'No model call; this is an offline extract, a clarification or a scope refusal.')}</span></div>
    <div class="timeline-item"><strong>${state.lang === 'zh' ? '发布判断' : 'Publication decision'}</strong><span>${isSynthetic ? (state.lang === 'zh' ? '只证明接线成功；夹具文本不作为政策答案发布。' : 'Wiring only; the fixture text is not published as a policy answer.') : `${esc(status)}${result.stop_reason ? ` — ${esc(result.stop_reason)}` : ''}. ${citations.length ? (state.lang === 'zh' ? '引用编号已映射到来源抽屉。' : 'Citation IDs are mapped to the source drawer.') : (state.lang === 'zh' ? '此状态没有发布引用。' : 'No citation was published for this status.')}`}</span></div>
  </div>
  <div class="citation-list">${citations.length ? citations.map(citationHTML).join('') : '<div class="empty">No citation published for this status.</div>'}</div>`;
}


function autoGrowQuestion(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 190) + 'px';
}

function bindCopyButtons() {
  if (window.__dscCopyBound) return;
  window.__dscCopyBound = true;
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const text = decodeURIComponent(button.dataset.copy || '');
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = state.lang === 'zh' ? '已复制' : 'Copied';
      showToast(state.lang === 'zh' ? '命令已复制。' : 'Command copied.');
    } catch (error) {
      showToast(state.lang === 'zh' ? '浏览器未允许自动复制，请手动选择命令。' : 'Clipboard permission denied; select the command manually.');
    }
  });
}


function moduleChain() {
  const zh = state.lang === 'zh';
  const nodes = [
    ['R02', zh ? '采集与清洗' : 'Collect + clean', zh ? '159篇 / 8主题' : '159 docs / 8 topics'],
    ['R03', zh ? '切块与索引' : 'Chunk + index', zh ? '881片段 / 384维' : '881 chunks / 384 dims'],
    ['R05', zh ? '检索与Agent' : 'Retrieval + agent', zh ? 'N5/N7 + 引用' : 'N5/N7 + citations'],
    ['F1–F5', zh ? '界面与交付' : 'UI + delivery', zh ? '问/数/检/评/交' : 'ask/data/retrieval/eval/delivery'],
  ];
  return `<div class="module-chain" id="module-chain"><span class="chain-label">${zh ? '模块链' : 'MODULE CHAIN'}</span><div class="chain-row">${nodes.map(([id, title, note], index) => `<div class="chain-node"><b>${id} · ${esc(title)}</b><small>${esc(note)}</small></div>${index < nodes.length - 1 ? '<span class="chain-arrow">→</span>' : ''}`).join('')}</div><div class="chain-loop"><b>R04</b> ${zh ? '评测检索与数据库' : 'evaluates retrieval + database'} <span>↺</span> <b>R06</b> ${zh ? '复核回答与失败归因' : 'reviews answers + failure attribution'} <span>→</span> ${zh ? '反馈到R03/R05与F1–F5' : 'feeds back into R03/R05 and F1–F5'}</div></div>`;
}

function architectureLanes() {
  const zh = state.lang === 'zh';
  return `<section class="card lane-overview" id="architecture">
    <div class="card-title"><div><div class="eyebrow">${zh ? '整体架构' : 'SYSTEM ARCHITECTURE'}</div><h3>${zh ? '离线与在线，共用一条证据契约' : 'Offline and online, one evidence contract'}</h3></div><span class="badge">F1 / 881 chunks</span></div>
    <div class="lane-grid">
      <article class="lane offline">
        <div class="lane-head"><span class="lane-tag">OFFLINE</span><b>${zh ? '无密钥 · 本地检索' : 'No key · local retrieval'}</b></div>
        <div class="lane-step"><span>1</span><div><b>${zh ? '问题与范围' : 'Question + scope'}</b><small>${zh ? '自由输入、可选主题、澄清选项' : 'free text, optional topic, clarify options'}</small></div></div>
        <div class="lane-step"><span>2</span><div><b>${zh ? '本地BM25检索' : 'Local BM25 retrieval'}</b><small>${zh ? '159篇页面 · 881片段 · 8主题 · SHA校验' : '159 pages · 881 chunks · 8 topics · SHA check'}</small></div></div>
        <div class="lane-step"><span>3</span><div><b>${zh ? '摘录式回答' : 'Extractive answer'}</b><small>${zh ? '原文句子 + 来源ID；问题类型不匹配则拒答' : 'quoted sentences + source IDs; abstain on answer-type mismatch'}</small></div></div>
        <div class="lane-step"><span>4</span><div><b>${zh ? '人来核对' : 'Human verifies'}</b><small>${zh ? '打开引用抽屉；不调用模型、不联网' : 'open citation drawer; no model, no network'}</small></div></div>
        <div class="lane-note">${zh ? '入口：不配置密钥；或设置 DSC5003_DISABLE_LLM=1' : 'Use: no key; or set DSC5003_DISABLE_LLM=1'}</div>
      </article>
      <article class="lane online">
        <div class="lane-head"><span class="lane-tag">ONLINE</span><b>${zh ? '模型 + 独立复核' : 'Model + independent review'}</b></div>
        <div class="lane-step"><span>1</span><div><b>${zh ? '问题与范围' : 'Question + scope'}</b><small>${zh ? '同一输入契约；答案语言跟随问题' : 'same input contract; answer language follows the question'}</small></div></div>
        <div class="lane-step"><span>2</span><div><b>${zh ? '先做本地检索' : 'Local retrieval first'}</b><small>${zh ? 'Top-5证据，S1–S5编号由服务器生成' : 'Top-5 evidence; S1–S5 IDs are server-generated'}</small></div></div>
        <div class="lane-step"><span>3</span><div><b>${zh ? '证据约束回答' : 'Evidence-bound answer'}</b><small>${zh ? '模型只看检索片段；不能生成URL或假引用' : 'model sees only retrieved chunks; no URLs or fake citations'}</small></div></div>
        <div class="lane-step"><span>4</span><div><b>${zh ? '独立复核' : 'Independent reviewer'}</b><small>${zh ? 'pass / revise / reject；服务器映射引用' : 'pass / revise / reject; server maps citations'}</small></div></div>
        <div class="lane-note">${zh ? '入口：DEEPSEEK_API_KEY；失败自动回退离线' : 'Use: DEEPSEEK_API_KEY; fallback to offline on failure'}</div>
      </article>
    </div>
    <div class="contract-strip"><span>${zh ? '共同契约' : 'SHARED CONTRACT'}</span><b>${zh ? '范围门' : 'scope gate'}</b> → <b>${zh ? '本地证据' : 'local evidence'}</b> → <b>${zh ? '状态' : 'status'}</b> → <b>${zh ? '服务器引用' : 'server citations'}</b> → <b>${zh ? '人工核对' : 'human check'}</b></div>
    <div class="adaptive-io"><div><b>${zh ? '输入自适应' : 'Adaptive input'}</b><span>${zh ? '输入框随内容增高；主题可选；语言跟随问题' : 'textarea grows with content; topic optional; language follows the question'}</span></div><div><b>${zh ? '回答自适应' : 'Adaptive answer'}</b><span>${zh ? 'answered→要点；clarify→选项；abstained/out_of_scope→拒答；review→问题清单' : 'answered→points; clarify→options; abstained/out_of_scope→refusal; review→issue list'}</span></div></div>
  </section>`;
}

function interactionAndCommands() {
  const zh = state.lang === 'zh';
  const commands = [
    {label: zh ? '启动（自动选端口）' : 'Start (auto port)', command: 'python app.py --open'},
    {label: zh ? '健康检查' : 'Health check', command: healthCommand()},
    {label: zh ? '强制离线' : 'Force offline', command: "$env:DSC5003_DISABLE_LLM='1'"},
  ];
  const steps = zh
    ? [['人', '输入问题、可选主题或点澄清选项'], ['系统', '判断范围与主题；超出范围直接拒答'], ['系统', '本地检索Top-5，保留S1–S5证据身份'], ['系统', '在线：模型回答+复核；离线：摘录+类型门'], ['人', '打开引用抽屉核对；必要时再选下一步']]
    : [['Human', 'ask, choose a topic, or pick a clarify option'], ['System', 'detect scope/topic; refuse out-of-scope'], ['System', 'retrieve Top-5 with S1–S5 evidence identity'], ['System', 'online: model + review; offline: extract + type gate'], ['Human', 'open citation drawer; choose the next step']];
  return `<div class="grid cols-2" style="margin-top:17px">
    <section class="card" id="human-loop"><div class="card-title"><div><div class="eyebrow">${zh ? '人机交互' : 'HUMAN–MACHINE LOOP'}</div><h3>${zh ? '谁在什么时候做什么' : 'Who does what, and when'}</h3></div><span class="badge">${zh ? '自适应' : 'adaptive'}</span></div><div class="flow">${steps.map(([who, what], index) => `<div class="flow-node"><b>${index + 1}. ${esc(who)}</b><br><span class="micro">${esc(what)}</span></div>${index < steps.length - 1 ? '<div class="flow-line"></div>' : ''}`).join('')}</div></section>
    <section class="card" id="core-commands"><div class="card-title"><div><div class="eyebrow">${zh ? '核心命令' : 'CORE COMMANDS'}</div><h3>${zh ? '运行、检查与回退' : 'Run, inspect and fall back'}</h3></div><span class="badge">copyable</span></div><div class="command-list">${commands.map(item => `<div class="command-mini"><b>${esc(item.label)}</b><code>${esc(item.command)}</code><button class="button tiny secondary" data-copy="${encodeURIComponent(item.command)}">Copy</button></div>`).join('')}</div><div class="notice teal" style="margin-top:11px">API: <span class="mono">POST /api/answer {question, topic}</span> · <span class="mono">GET /api/health</span></div><p class="micro" style="margin-top:10px">${zh ? '在线路径失败会自动回退离线摘录；两种路径都只从881片段索引取证据。' : 'If the online path fails, it falls back to offline extraction. Both paths take evidence only from the 881-chunk index.'}</p></section>
  </div>`;
}


function renderOverview(data) {
  const zh = state.lang === 'zh';
  const cards = [
    ['ask', zh ? '01 提问' : '01 Ask', zh ? '问题 → 状态 → 引用' : 'question → status → citations'],
    ['data', zh ? '02 数据' : '02 Data', zh ? '覆盖 → 知识库 → SQL' : 'coverage → knowledge base → SQL'],
    ['retrieval', zh ? '03 检索' : '03 Retrieval', zh ? 'Top-5 → 分数 → 来源' : 'Top-5 → scores → source'],
    ['evaluation', zh ? '04 评估' : '04 Evaluation', zh ? 'R4/R6 → rubric → golden' : 'R4/R6 → rubric → golden'],
    ['delivery', zh ? '05 交付' : '05 Delivery', zh ? '双车道 → 根目录 → 交接' : 'lanes → root map → handoff'],
  ];
  app.innerHTML = `${pageHead('00 · SYSTEM OVERVIEW', zh ? '一条证据链，两条车道，六个模块。' : 'One evidence chain, two lanes, six modules.', zh ? '先看整体：离线与在线如何共用同一套证据契约，R02–R06如何串成模块链，人在哪里核对，核心命令是什么。再进入01–05逐页看细节。' : 'Start with the whole picture: how offline and online share one evidence contract, how R02–R06 form the module chain, where the human checks evidence, and which commands run the demo. Then move through 01–05.', zh ? '阅读顺序' : 'Reading order', zh ? '00 总览 → 01 提问 → 02 数据 → 03 检索 → 04 评估 → 05 交付' : '00 overview → 01 ask → 02 data → 03 retrieval → 04 evaluation → 05 delivery', 'F1–F5')}
  ${architectureLanes()}
  ${moduleChain()}
  ${interactionAndCommands()}
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">${zh ? '从这里进入' : 'START HERE'}</div><h3>${zh ? '按证据链走，不按页面走' : 'Follow the evidence chain, not just the pages'}</h3></div><span class="badge">01–05</span></div><div class="route-map">${cards.map(([route, title, note]) => `<button class="route-card" data-route="${route}"><b>${esc(title)}</b><span>${esc(note)}</span></button>`).join('')}</div></section>
  ${footer(zh ? '从提问开始' : 'Start with the question', 'ask')}`;
  bindCopyButtons();
}

function renderAsk(data) {
  const recorded = state.f1Result || data.f1.recorded;
  const live = state.f1Live;
  const mode = f1ModeMeta(recorded, live);
  const samples = [
    ...data.f1.samples,
    {label: '中文：图书馆', question: '进入图书馆需要什么？', topic: 'library'},
    {label: '中文：学费', question: '学费怎么交？', topic: 'fees'},
    {label: state.lang === 'zh' ? '越界测试' : 'Out-of-scope test', question: 'Who won the World Cup?', topic: ''},
  ];
  const selectedTopic = state.f1Topic || '';
  app.innerHTML = `${pageHead('F1 · ASK WITH EVIDENCE', 'Ask with <em>evidence</em>, not blind trust.', 'Ask a CityUHK student-services question. The interface shows the detected scope, the retrieved evidence, the publication status and the citations. A live model, when configured, is checked by an independent evidence reviewer; otherwise the answer is a direct extract from the indexed pages.', 'Answer contract', 'Scope → evidence → answer → citations.', 'F1 / R05 881 chunks')}
  <div class="reading-hint"><b>${state.lang === 'zh' ? '先看范围，再看答案：' : 'Read the scope before the answer:'}</b> ${state.lang === 'zh' ? '索引只覆盖8个城大学生服务主题、159篇页面。问题超出范围时系统应拒答或澄清，而不是用常识补答；问题有歧义时应先给选项。答案语言跟随问题，界面语言由右上角切换。' : 'The index covers only eight CityUHK student-service topics and 159 pages. Out-of-scope questions should be refused or clarified, not answered from general knowledge; ambiguous questions should produce options first. Answer language follows the question; the interface language follows the top-right toggle.'}</div>
  <div class="ask-layout">
    <section class="card composer">
        <div class="composer-top"><h2>Question workspace</h2><span class="chip ${mode.tone}">${esc(state.lang === 'zh' ? mode.zh : mode.en)}</span></div>
        <div class="editor">
          <label class="field-label" for="question">Student question</label>
          <textarea id="question" class="query-input" aria-label="Student question">${esc(recorded.question || samples[0].question)}</textarea>
          <div class="sample-row">${samples.map(sample => `<button class="sample" data-sample="${esc(sample.question)}" data-topic="${esc(sample.topic || '')}">${esc(sample.label)}</button>`).join('')}</div>
          <div class="editor-foot">
            <div class="form-row"><label class="field-label" for="topic">Topic</label><select id="topic" class="select"><option value="">${state.lang === 'zh' ? '自动识别主题' : 'Auto-detect topic'}</option>${TOPIC_OPTIONS.map(([key, en, zh]) => `<option value="${key}" ${selectedTopic === key ? 'selected' : ''}>${state.lang === 'zh' ? zh : en}</option>`).join('')}</select><span class="micro">${state.lang === 'zh' ? '可选过滤' : 'Optional filter'}</span></div>
            <div class="button-row"><button class="button secondary" id="reset-replay">${state.lang === 'zh' ? '已记录回放' : 'Recorded replay'}</button><button class="button" id="run-answer">${state.lang === 'zh' ? '运行证据问答' : 'Ask evidence index'}</button></div>
          </div>
          <div class="notice teal" style="margin-top:14px">${state.lang === 'zh' ? '<b>运行证据问答</b>会从真实的881片段索引检索；若配置了模型，服务器先要求“只依据证据”的回答，再运行一次独立证据复核；未配置密钥时直接摘录匹配句子。<b>合成接线检查</b>是单独按钮，只证明UI/CLI能连通，不提供政策答案。' : '<b>Ask evidence index</b> retrieves from the real 881-chunk snapshot. If a model key is configured, the server requests an evidence-bound answer and then runs an independent support review; without a key it quotes matching sentences directly. <b>Backend wiring check</b> is a separate button: it only proves the UI/CLI connection and never supplies policy text.'}</div>
          <div class="scope-line">${state.lang === 'zh' ? '范围：8个城大学生服务主题、159篇页面、881个索引片段；不是通用助手。' : 'Scope: eight CityUHK student-service topics, 159 pages, 881 indexed chunks; not a general assistant.'}</div>
          <button class="link-button" id="run-demo">${state.lang === 'zh' ? '后端接线检查（合成夹具）' : 'Backend wiring check (synthetic)'}</button>
        </div>
    </section>
    <section class="card result-shell" id="f1-result" aria-live="polite">${askResultHTML(recorded, live, data)}</section>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Failure is a feature</div><h3>Statuses the UI must not blur</h3></div><span class="badge">F1 contract</span></div><div class="grid cols-2">${data.f1.status_legend.map(([status, note]) => `<div class="trace-stat"><b class="status ${statusClass(status).replace('status ', '')}">${esc(status)}</b><span>${esc(note)}</span></div>`).join('')}</div></section>
  ${footer('What data is inside?', 'data')}`;
  bindAsk(data);
}

function focusF1Result() {
  const result = document.getElementById('f1-result');
  if (!result) return;
  result.setAttribute('tabindex', '-1');
  const top = result.getBoundingClientRect().top + window.scrollY - 88;
  window.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
  setTimeout(() => result.focus({preventScroll: true}), 250);
}

async function runEvidenceAnswer() {
  const question = document.getElementById('question')?.value.trim();
  const topic = document.getElementById('topic')?.value.trim() || null;
  state.f1Topic = topic || '';
  if (!question) { showToast(state.lang === 'zh' ? '请先输入问题。' : 'Enter a question first.'); return; }
  const button = document.getElementById('run-answer');
  const box = document.getElementById('f1-result');
  if (button) { button.disabled = true; button.textContent = state.lang === 'zh' ? '检索与复核中…' : 'Retrieving and reviewing…'; }
  if (box) box.innerHTML = `<div class="loading-card"><div class="loader"></div><p>${state.lang === 'zh' ? '正在检索真实索引，并按配置运行模型与复核…' : 'Retrieving the real index and running the configured model and review…'}</p></div>`;
  try {
    const response = await fetch('/api/answer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question, topic})});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Evidence answer failed');
    state.f1Result = {...payload, question};
    state.f1Live = true;
    render();
    focusF1Result();
    showToast(state.lang === 'zh' ? `已返回：${payload.status}（${payload.mode}）` : `Returned: ${payload.status} (${payload.mode})`);
  } catch (error) {
    state.f1Result = {question, mode: 'error', status: 'generation_error', latency_ms: 0, llm_calls: 0, citations: [], error: {message: error.message}, warnings: [error.message]};
    state.f1Live = true;
    render();
    focusF1Result();
    showToast(error.message);
  }
}

async function runSyntheticWiring() {
  const question = document.getElementById('question')?.value.trim();
  const topic = document.getElementById('topic')?.value.trim() || null;
  state.f1Topic = topic || '';
  if (!question) { showToast(state.lang === 'zh' ? '请先输入问题。' : 'Enter a question first.'); return; }
  const button = document.getElementById('run-demo');
  const box = document.getElementById('f1-result');
  if (button) { button.disabled = true; button.textContent = state.lang === 'zh' ? '接线检查运行中…' : 'Checking wiring…'; }
  if (box) box.innerHTML = `<div class="loading-card"><div class="loader"></div><p>${state.lang === 'zh' ? '正在调用R05 CLI合成夹具…' : 'Calling the R05 CLI synthetic fixture…'}</p></div>`;
  try {
    const response = await fetch('/api/backend-demo', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question, topic})});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Backend demo failed');
    state.f1Result = {...payload, question, mode: 'synthetic'};
    state.f1Live = true;
    render();
    focusF1Result();
    showToast(state.lang === 'zh' ? '这是接线检查，不是政策答案。' : 'This is a wiring check, not a policy answer.');
  } catch (error) {
    state.f1Result = {question, mode: 'synthetic', status: 'generation_error', latency_ms: 0, llm_calls: 0, citations: [], error: {message: error.message}, warnings: [error.message]};
    state.f1Live = true;
    render();
    focusF1Result();
    showToast(error.message);
  }
}

function bindAsk(data) {
  document.querySelectorAll('[data-sample]').forEach(btn => btn.addEventListener('click', () => {
    const q = document.getElementById('question');
    if (q) { q.value = btn.dataset.sample || ''; autoGrowQuestion(q); }
    state.f1Topic = btn.dataset.topic || '';
    const topic = document.getElementById('topic');
    if (topic) topic.value = state.f1Topic;
  }));
  document.getElementById('question')?.addEventListener('input', (event) => autoGrowQuestion(event.currentTarget));
  document.getElementById('topic')?.addEventListener('change', (event) => {
    state.f1Topic = event.currentTarget.value || '';
  });
  document.getElementById('reset-replay')?.addEventListener('click', () => {
    state.f1Result = null; state.f1Live = false; state.f1Topic = ''; render();
  });
  document.getElementById('run-answer')?.addEventListener('click', runEvidenceAnswer);
  document.getElementById('run-demo')?.addEventListener('click', runSyntheticWiring);
  document.querySelectorAll('[data-clarify]').forEach(btn => btn.addEventListener('click', () => {
    const q = document.getElementById('question');
    if (q) { q.value = btn.dataset.clarify || ''; autoGrowQuestion(q); }
    state.f1Topic = '';
    const topic = document.getElementById('topic');
    if (topic) topic.value = '';
    runEvidenceAnswer();
  }));
}

function renderData(data) {
  app.innerHTML = `${pageHead('F2 · DATA & DATABASE', 'Make the <em>data boundary</em> visible.', 'A reliable answer starts with a trustworthy corpus. This view separates collection quality from query execution: coverage, a cleaning funnel, duplicate aliases, navigation-only exclusions, and the SQLite record.', 'Current snapshot', '159 active documents · 8 topics · 13/13 seeds.', shortSHA(data.meta.corpus_sha256) + ' · db ' + shortSHA(data.meta.database_sha256))}
  <div class="tabs" role="tablist"><button class="tab ${state.f2Tab === 'quality' ? 'active' : ''}" data-f2-tab="quality">Data quality</button><button class="tab ${state.f2Tab === 'database' ? 'active' : ''}" data-f2-tab="database">Database & SQL</button><button class="tab ${state.f2Tab === 'kb' ? 'active' : ''}" data-f2-tab="kb">Knowledge base</button></div>
  <div class="reading-hint"><b>${state.lang === 'zh' ? '怎么看：' : 'How to read:'}</b> ${state.lang === 'zh' ? 'Data quality回答“语料是否可信”；Database & SQL回答“存了什么、怎样查询、索引是否有效”；Knowledge base回答“文档如何变成可引用片段”。' : 'Data quality asks “is the corpus trustworthy?”; Database & SQL asks “what is stored, how is it queried, and does the index help?”; Knowledge base asks “how does a document become a citable chunk?”'}</div><div id="f2-content">${state.f2Tab === 'quality' ? f2Quality(data) : state.f2Tab === 'database' ? f2Database(data) : f2KnowledgeBase(data)}</div>
  ${footer('Compare retrieval modes', 'retrieval')}`;
  document.querySelectorAll('[data-f2-tab]').forEach(btn => btn.addEventListener('click', () => { state.f2Tab = btn.dataset.f2Tab; render(); }));
  document.getElementById('kb-topic')?.addEventListener('change', (event) => { state.kbTopic = event.currentTarget.value; render(); });
  bindSources();
  bindData(data);
}

function f2Quality(data) {
  const max = Math.max(...data.f2.coverage.map(x => x.docs));
  return `<div class="kpi-row">${data.f2.kpis.map(k => `<div class="kpi"><b>${esc(k.value)}</b><span>${esc(k.label)}</span><small>${esc(k.note)}</small></div>`).join('')}</div>
  <div class="grid cols-2">
    <section class="card"><div class="card-title"><div><div class="eyebrow">Coverage</div><h3>Documents by topic</h3></div><span class="badge">after rework</span></div><div class="bar-chart">${data.f2.coverage.map(x => `<div class="bar-row"><span class="label">${esc(state.lang === 'zh' ? x.topic_zh : x.topic_en)}</span><div class="bar-track"><div class="bar-fill" style="width:${(x.docs/max*100).toFixed(1)}%"></div></div><span class="num">${x.docs}</span></div>`).join('')}</div><p class="micro" style="margin-top:14px">Median length ${fmtMs(data.f2.coverage[0].median_chars).replace(' ms',' chars')} for the first topic; headline median is 2,905 characters. Coverage is 8 configured columns, not the whole CityU website.</p></section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">Cleaning funnel</div><h3>What survives to the corpus</h3></div><span class="chip amber">historical + recheck</span></div><div class="funnel">${data.f2.funnel.map((row, i) => `<div class="funnel-row"><span>${esc(row.stage)}</span><span style="display:flex;align-items:center;gap:9px"><b>${num(row.count)}</b>${i < data.f2.funnel.length - 1 ? '<span class="arrow">↓</span>' : ''}</span></div>`).join('')}</div><p class="micro" style="margin-top:10px">The 216/34/23 numbers come from the historical crawl run; 159 active documents were re-verified on 2026-11-11.</p></section>
  </div>
  <div class="grid cols-2" style="margin-top:17px">
    <section class="card"><div class="card-title"><div><div class="eyebrow">Deduplication</div><h3>Alias URLs collapse to one record</h3></div><span class="badge">SHA-256</span></div><div class="table-wrap"><table><thead><tr><th>Raw URL</th><th>Kept canonical</th><th>Reason</th></tr></thead><tbody>${data.f2.dedup.map(x => `<tr><td><span class="url">${esc(x.raw_url)}</span></td><td><span class="url">${esc(x.kept)}</span></td><td>${esc(x.reason)}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">Boundary handling</div><h3>Navigation-only pages stay out</h3></div><span class="chip red">rule fired</span></div><div class="table-wrap"><table><thead><tr><th>Page</th><th>Chars</th><th>Raw layer</th><th>Documents</th></tr></thead><tbody>${data.f2.filtered.map(x => `<tr><td><span class="url">${esc(x.url)}</span></td><td>${x.chars}</td><td>${x.in_records ? 'Yes' : 'No'}</td><td>${x.in_documents ? 'Yes' : 'No'}</td></tr>`).join('')}</tbody></table></div><p class="micro" style="margin-top:14px">Rule: text under 300 chars, or under 400 chars with at least six short lines and no line over 100 chars.</p></section>
  </div>`;
}

function tableFromRows(rows) {
  if (!rows || !rows.length) return '<div class="empty">No rows returned.</div>';
  const columns = Object.keys(rows[0]);
  return `<div class="table-wrap"><table><thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(c => `<td>${esc(row[c] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function sqlResultHTML(query, executed = false) {
  return `${executed ? `<div class="run-meta"><span class="chip">read-only</span><span class="meta-pill">Latency<b>${esc(query.latency_ms)} ms</b></span><span class="meta-pill">Rows<b>${query.rows.length}</b></span></div>` : `<div class="notice teal" style="margin-bottom:10px">Reported result from the frozen evidence file. Press “Run read-only query” to execute this preset against the published SQLite database.</div>`}${tableFromRows(query.rows)}<div class="flow" style="margin-top:12px">${(query.plan || query.explain || []).map(x => `<div class="flow-node micro"><b>PLAN</b><br>${esc(typeof x === 'string' ? x : x.detail)}</div>`).join('')}</div>`;
}


function f2KnowledgeBase(data) {
  const kb = data.f2.knowledge_base;
  const zh = state.lang === 'zh';
  const topics = [...new Set(kb.sample_docs.map(x => x.topic))];
  const docs = state.kbTopic === 'all' ? kb.sample_docs : kb.sample_docs.filter(x => x.topic === state.kbTopic);
  return `<div class="kpi-row">
    <div class="kpi"><b>${num(kb.documents)}</b><span>${zh ? '活动文档' : 'Active documents'}</span><small>corpus.jsonl</small></div>
    <div class="kpi"><b>${num(kb.runtime_chunks)}</b><span>${zh ? '运行片段' : 'Runtime chunks'}</span><small>R05 / N5-N7</small></div>
    <div class="kpi"><b>${num(kb.published_chunks)}</b><span>${zh ? '发布SQLite片段' : 'Published SQLite chunks'}</span><small>${zh ? '不是同一产物' : 'different artifact'}</small></div>
    <div class="kpi"><b>${num(kb.comparison_chunks)}</b><span>${zh ? '对比构建片段' : 'Comparison chunks'}</span><small>R03</small></div>
  </div>
  <div class="gold-status-row" style="margin: -5px 0 15px"><span class="chip">${kb.indexed_documents}/${kb.documents} ${zh ? '文档已进入索引' : 'docs indexed'}</span><span class="chip amber">${kb.unindexed_documents} ${zh ? '篇未索引' : 'unindexed'}</span><span class="chip neutral">SQLite chunks = ${num(kb.published_chunks)}</span></div>
  <div class="grid cols-2">
    <section class="card"><div class="card-title"><div><div class="eyebrow">${zh ? '索引解剖' : 'INDEX ANATOMY'}</div><h3>${zh ? '文档如何变成可引用片段' : 'How a document becomes a citable chunk'}</h3></div><span class="badge">SHA-bound</span></div>
      <div class="flow">
        <div class="flow-node"><b>corpus.jsonl · ${num(kb.documents)} docs</b><br><span class="micro">${zh ? '8主题 / 活动文档 / 原始URL保留' : '8 topics / active docs / original URLs retained'}</span></div><div class="flow-line"></div>
        <div class="flow-node"><b>documents · ${num(kb.documents)} rows · records · ${num(kb.records)}</b><br><span class="micro">${zh ? 'SQLite源文档库；chunks表发布为0' : 'SQLite source store; published chunks table is 0'}</span></div><div class="flow-line"></div>
        <div class="flow-node"><b>R05 runtime · ${num(kb.runtime_chunks)} chunks</b><br><span class="micro">${zh ? '切块后进入向量索引；每个片段保留chunk_id和doc_id；157/159篇进入索引，2篇未索引' : 'chunked into the vector index; each chunk keeps chunk_id and doc_id; 157/159 docs indexed, 2 unindexed'}</span></div><div class="flow-line"></div>
        <div class="flow-node"><b>citation · chunk_id + URL</b><br><span class="micro">${zh ? '前端只展示服务器映射的引用身份' : 'the UI shows only server-mapped citation identity'}</span></div>
      </div>
      <p class="micro" style="margin-top:12px">${esc(kb.chunk_policy)}</p>
    </section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">${zh ? '文档样例' : 'DOCUMENT SAMPLE'}</div><h3>${zh ? '每个主题抽一篇看身份' : 'One document per topic'}</h3></div><div class="form-row"><label class="field-label" for="kb-topic">${zh ? '主题' : 'Topic'}</label><select id="kb-topic" class="select"><option value="all" ${state.kbTopic === 'all' ? 'selected' : ''}>${zh ? '全部主题' : 'All topics'}</option>${topics.map(t => `<option value="${esc(t)}" ${state.kbTopic === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></div></div>
      <div class="table-wrap"><table><thead><tr><th>${zh ? '主题' : 'Topic'}</th><th>${zh ? '标题' : 'Title'}</th><th>${zh ? '学年' : 'Year'}</th><th>${zh ? '字符' : 'Chars'}</th><th>Chunks</th><th>${zh ? '首个片段' : 'First chunk'}</th><th>URL</th></tr></thead><tbody>${docs.map(x => `<tr><td>${esc(x.topic)}</td><td>${esc(x.title).slice(0, 80)}</td><td>${esc(x.academic_year || '—')}</td><td>${num(x.chars)}</td><td>${x.indexed_chunks}</td><td>${x.first_chunks && x.first_chunks.length ? `<button class="link-button" data-source="${encodeURIComponent(JSON.stringify({title: x.title, url: x.url, chunk_id: x.first_chunks[0], topic: x.topic, excerpt: x.first_excerpt}))}">${esc(x.first_chunks[0].split('#').pop())}</button>` : `<span class="chip red">${zh ? '未索引' : 'not indexed'}</span>`}</td><td><a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.url).slice(0, 40)}</a></td></tr>`).join('')}</tbody></table></div>
      <p class="micro" style="margin-top:10px">${zh ? '这是每个主题的样例，不是159篇全量；主题筛选为前端动态过滤。' : 'This is one sample per topic, not all 159 documents; the topic filter is client-side dynamic.'}</p>
    </section>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">${zh ? '三个计数' : 'THREE COUNTS'}</div><h3>${zh ? '不要把它们合并成一个数字' : 'Do not collapse them into one number'}</h3></div><span class="chip amber">${zh ? '版本分层' : 'version lanes'}</span></div><div class="grid cols-3"><div class="flow-node"><b>${zh ? '发布SQLite' : 'Published SQLite'}</b><br><span class="micro">chunks ${num(kb.published_chunks)} · ${zh ? '源文档库' : 'source store'}</span></div><div class="flow-node"><b>R05 ${zh ? '运行库' : 'runtime'}</b><br><span class="micro">${num(kb.runtime_chunks)} chunks · ${zh ? 'N5/N7索引' : 'N5/N7 index'}</span></div><div class="flow-node"><b>R03 ${zh ? '对比构建' : 'comparison'}</b><br><span class="micro">${num(kb.comparison_chunks)} chunks · ${zh ? '检索对比' : 'retrieval comparison'}</span></div></div><p class="micro" style="margin-top:10px">corpus SHA ${esc(shortSHA(kb.corpus_sha256))} · db SHA ${esc(shortSHA(kb.database_sha256))} · ${zh ? 'FAISS是派生索引，不是SQLite表。' : 'FAISS is a derived index, not a SQLite table.'}</p><div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>${zh ? 'JSONL字段' : 'JSONL field'}</th><th>${zh ? 'SQLite字段' : 'SQLite field'}</th><th>${zh ? '用途' : 'Purpose'}</th></tr></thead><tbody>${kb.field_mapping.map(([a,b,c]) => `<tr><td class="mono small">${esc(a)}</td><td class="mono small">${esc(b)}</td><td>${esc(c)}</td></tr>`).join('')}</tbody></table></div><p class="micro" style="margin-top:10px">Snapshot receipt: ${esc(kb.snapshot_receipt.version)} · ${esc(kb.snapshot_receipt.status)} · integrity ${esc(kb.snapshot_receipt.integrity)} · policy ${esc(kb.snapshot_receipt.policy_currency)} · human acceptance ${esc(kb.snapshot_receipt.human_semantic_acceptance)}. ${zh ? '2篇未索引：' : '2 unindexed: '}${kb.unindexed_ids.map(x => `<span class="mono">${esc(x)}</span>`).join(' · ')}</p></section>`;
}

function f2Database(data) {
  const db = data.f2.database;
  const query = db.queries.find(q => q.id === state.sqlId) || db.queries[0];
  return `<div class="grid cols-2">
    <section class="card"><div class="card-title"><div><div class="eyebrow">SQLite record</div><h3>Published database snapshot</h3></div><span class="badge">snapshot integrity ok</span></div><div class="table-wrap"><table><thead><tr><th>Table</th><th>Rows</th><th>Columns</th></tr></thead><tbody>${db.tables.map(t => `<tr><td class="mono">${esc(t.name)}</td><td>${num(t.rows)}</td><td>${t.columns}</td></tr>`).join('')}</tbody></table></div><div class="run-meta">${statPills([['JSONL fields', db.facts.json_fields], ['documents columns', db.facts.schema_columns], ['Secondary indexes', db.facts.indexes], ['Snapshot FK check', db.facts.foreign_key_check]])}</div><div class="notice">${esc(db.normalization_note)}</div><div class="notice" style="margin-top:8px">integrity_check and foreign_key_check describe this snapshot only; they do not prove historical FK enforcement or semantic correctness.</div><div class="notice" style="margin-top:8px">records=83 is the raw collection layer, not a complete source for the 159 documents; 119 documents have no academic_year, which does not mean the current year. Integrity/FK checks apply to this snapshot only.</div></section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">Data model</div><h3>One real relationship</h3></div><span class="chip blue">physical schema</span></div><div class="flow"><div class="flow-node"><b>documents</b> · 159 rows · PK url<br><span class="micro">topic / academic_year / active / index_dirty / corpus_sha256</span></div><div class="flow-line"></div><div class="flow-node"><b>chunks</b> · 0 rows in published DB · PK chunk_id<br><span class="micro">FK doc_id → documents.url, nullable</span></div></div><p class="micro" style="margin-top:14px">FAISS is a derived retrieval artifact, not a SQLite table. The published index has 881 chunks from a different build; the R03 F3 view reports 863 chunks from its new local build. Keep the version labels separate.</p></section>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Version lanes</div><h3>Three artifacts, three different counts</h3></div><span class="badge">do not merge</span></div><div class="run-meta"><span class="chip blue">Published SQLite · source store · chunks 0</span><span class="chip">R05 runtime · N5/N7 index · 881 chunks</span><span class="chip amber">R03 comparison · retrieval run · 863 chunks</span></div><p class="micro" style="margin-top:10px">The published SQLite table has no chunk rows. The R05 backend uses a separate 881-chunk runtime index; R03 reports a separate 863-chunk local comparison. The counts are not a data-quality contradiction; they are different builds.</p></section>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">SQL evidence</div><h3>Pre-set query against the published database</h3></div><span class="badge">read-only</span></div><div class="button-row" style="margin-bottom:12px"><div class="segmented">${db.queries.map(q => `<button class="segment ${state.sqlId === q.id ? 'active' : ''}" data-sql-id="${q.id}">${q.id}</button>`).join('')}</div><button class="button" id="run-sql">Run read-only query</button><span class="chip neutral">server-side preset</span></div><div class="mono small" style="background:#f2f5f0;border:1px solid #dbe4de;border-radius:10px;padding:13px;overflow:auto">${esc(query.sql)}</div><div class="grid cols-2" style="margin-top:13px"><div id="sql-result">${sqlResultHTML(query)}</div><div class="notice teal"><b>Why this is a real execution:</b> the endpoint opens the published SQLite file with <span class="mono">mode=ro</span>, runs only the selected preset and returns rows plus <span class="mono">EXPLAIN QUERY PLAN</span>. The database is not modified.</div></div></section>`;
}

function renderRetrieval(data) {
  const mode = state.f3Mode;
  const hits = mode === 'rerank' ? data.f3.rerank : data.f3.faiss;
  app.innerHTML = `${pageHead('F3 · RETRIEVAL OBSERVATION', 'Inspect the <em>Top-5</em>, not just the answer.', 'The retrieval layer can show the evidence trail: rank, score, title, topic, chunk identity and original URL. The two score scales stay visibly separate, and the failure case stays visible.', 'R03 frozen comparison', data.f3.topic, '159 docs · 863 chunks · 384 dims')}
  <div class="reading-hint"><b>${state.lang === 'zh' ? '怎么看：' : 'How to read:'}</b> ${state.lang === 'zh' ? 'FAISS先按向量相似度排序，Rerank再用cross-encoder重排。用同一个问题比较顺序，不要直接比较两种分数的数值。' : 'FAISS ranks by vector similarity; Rerank reorders with a cross-encoder. Compare the order for the same question, not the raw score values.'}</div>
  <div class="grid cols-2">
    <section class="card"><div class="composer-top" style="padding:0 0 15px;border:0"><div><div class="eyebrow">Query</div><h2 style="margin-top:5px">${esc(data.f3.query)}</h2></div><div class="segmented"><button class="segment ${mode === 'faiss' ? 'active' : ''}" data-f3-mode="faiss">FAISS only</button><button class="segment ${mode === 'rerank' ? 'active' : ''}" data-f3-mode="rerank">+ Rerank</button></div><div class="micro" style="margin-top:5px">${esc(data.f3.index.rerank)}</div></div><div class="result-list">${resultRows(hits, mode)}</div><p class="micro" style="margin-top:14px">${mode === 'faiss' ? 'FAISS similarity scores. The fourth row is an off-topic timetable result—visible, not hidden.' : 'Rerank scores are cross-encoder scores, not comparable with FAISS cosine-like values. This is why the UI labels the scale.'}</p></section>
    <div class="grid">
      <section class="card dark"><div class="card-title"><div><div class="eyebrow">Index identity</div><h3>What the 863 means</h3></div><span class="chip" style="background:#1d4d53;color:#c6efea">R03 build</span></div><div class="index-strip">${[['Corpus', data.meta.documents], ['Chunks', data.f3.index.chunks], ['Vectors', data.f3.index.vectors], ['Dim', data.f3.index.dimension]].map(([a,b]) => `<div class="index-cell"><span>${esc(a)}</span><b>${num(b)}</b></div>`).join('')}</div><p class="mini muted" style="font-size:10px;line-height:1.7;margin:15px 0 0">${esc(data.f3.index.embedding)}<br>${esc(data.f3.index.index_type)} · ${esc(data.f3.index.prefixes)}</p></section>
      <section class="card" id="retrieval-failure"><div class="card-title"><div><div class="eyebrow">Contrast case</div><h3>A real failure stays in view</h3></div><span class="chip red">not fixed</span></div><p class="small"><b>${esc(data.f3.failure.query)}</b></p><div class="result-list"><button class="result-row" data-source="${encodeURIComponent(JSON.stringify(data.f3.failure.faiss))}"><span class="rank">01</span><span class="score">${Number(data.f3.failure.faiss.score).toFixed(4)}</span><span><strong>${esc(data.f3.failure.faiss.display_title)}</strong><small>FAISS · ${esc(data.f3.failure.faiss.topic)}</small></span><span class="chip neutral">FAISS</span></button><button class="result-row" data-source="${encodeURIComponent(JSON.stringify(data.f3.failure.rerank))}"><span class="rank">01</span><span class="score">${Number(data.f3.failure.rerank.score).toFixed(4)}</span><span><strong>${esc(data.f3.failure.rerank.display_title)}</strong><small>Rerank · ${esc(data.f3.failure.rerank.topic)}</small></span><span class="chip amber">RERANK</span></button></div><div class="notice" style="margin-top:12px">${esc(data.f3.failure.conclusion)}</div></section>
    </div>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Read the caveat</div><h3>What this page does not claim</h3></div><span class="badge">boundary</span></div><p class="small">${esc(data.f3.source_note)}</p></section>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Vector index anatomy</div><h3>From FAISS row to a citable chunk</h3></div><span class="chip blue">R05 881 sample</span></div>
    <div class="grid cols-2">
      <div><div class="flow"><div class="flow-node"><b>FAISS IndexFlatIP</b><br><span class="micro">${esc(data.f3.index.index_type)} · ${num(data.f3.index.runtime_chunks)} vectors · ${num(data.f3.index.dimension)} dims (R05 881 sample)</span></div><div class="flow-line"></div><div class="flow-node"><b>index ID → chunk_id</b><br><span class="micro">${esc(data.f3.index.mapping)}</span></div><div class="flow-line"></div><div class="flow-node"><b>chunk_id → doc_id / URL</b><br><span class="micro">${esc(data.f3.index.prefixes)} · embedding ${esc(data.f3.index.embedding)}</span></div></div><div class="run-meta">${statPills([['Runtime', '881 chunks'], ['Comparison', '863 chunks'], ['Model rev', shortSHA(data.f3.index.model_revision)], ['R05 index SHA (881)', shortSHA(data.f3.index.index_sha256)]])}</div><p class="micro" style="margin-top:10px">${state.lang === 'zh' ? 'R05运行索引与R03对比索引是两套产物；FAISS行号不是文档ID，必须经过chunk_id映射。' : 'R05 runtime and R03 comparison are different builds; a FAISS row is not a document ID and must be mapped through chunk_id.'}</p></div>
      <div><div class="table-wrap"><table><thead><tr><th>Sample #</th><th>FAISS ID (0-based)</th><th>chunk_id</th><th>doc / URL</th><th>Topic</th></tr></thead><tbody>${data.f3.index.vector_samples.map(x => `<tr><td>${x.sample}</td><td>${x.faiss_id}</td><td><button class="link-button" data-source="${encodeURIComponent(JSON.stringify({...x, display_title: x.title, excerpt: x.excerpt}))}">${esc(x.chunk_id).slice(0, 56)}</button></td><td><span class="mono small">${esc(x.url).slice(0, 42)}</span></td><td>${esc(x.topic)}</td></tr>`).join('')}</tbody></table></div><p class="micro" style="margin-top:10px">${state.lang === 'zh' ? '样例行仅用于解释映射；点击打开来源抽屉。' : 'Sample rows explain the mapping only; click to open the source drawer.'}</p></div>
    </div>
    <div class="notice teal" style="margin-top:12px">${state.lang === 'zh' ? `R05 index SHA (881) ${esc(shortSHA(data.f3.index.index_sha256))} · corpus SHA ${esc(shortSHA(data.f3.index.corpus_sha256))} · model revision ${esc(shortSHA(data.f3.index.model_revision))} · normalize=${data.f3.index.build_receipt.normalize_embeddings} · max_seq=${data.f3.index.build_receipt.max_seq_length} · DB bound=${data.f3.index.build_receipt.database_chunk_binding}。R03 863只保留冻结分数/标题，未附index SHA。` : `R05 index SHA (881) ${esc(shortSHA(data.f3.index.index_sha256))} · corpus SHA ${esc(shortSHA(data.f3.index.corpus_sha256))} · model revision ${esc(shortSHA(data.f3.index.model_revision))} · normalize=${data.f3.index.build_receipt.normalize_embeddings} · max_seq=${data.f3.index.build_receipt.max_seq_length} · DB bound=${data.f3.index.build_receipt.database_chunk_binding}. R03 863 keeps frozen scores/titles only; no index SHA is packaged.`}</div>
  </section>
  ${footer('Separate retrieval from answer quality', 'evaluation')}`;
  document.querySelectorAll('[data-f3-mode]').forEach(btn => btn.addEventListener('click', () => { state.f3Mode = btn.dataset.f3Mode; render(); }));
  bindSources();
}

function renderEvaluation(data) {
  const core = data.f4.core;
  const agent = data.f4.agent;
  app.innerHTML = `${pageHead('F4 · EVALUATION', 'Keep the <em>denominators</em> honest.', 'Two evaluations are on this page. They use different question sets, different configurations and different judgments. The dashboard keeps them apart instead of turning every number into one “score.”', 'Status', 'Draft retrieval and AI-provisional review.', 'R4-CORE20 Hit@5 17/20 · R6-YP-CORE20 strict 15/20')}
  <div class="reading-hint"><b>${state.lang === 'zh' ? '怎么看：' : 'How to read:'}</b> ${state.lang === 'zh' ? 'Hit@5 只表示前5条里是否命中所需证据，不等于回答正确率；R4-CORE20与R6-YP-CORE20是不同题集；AI初评、人工裁决和正式验收不是同一层级。' : 'Hit@5 only says required evidence appeared in the top five; it is not answer accuracy. R4-CORE20 and R6-YP-CORE20 are different sets; AI review, human adjudication and formal acceptance are different levels.'}</div>
  <div class="eval-assets-strip"><span><b>${state.lang === 'zh' ? 'Golden 20+5' : 'Golden 20+5'}</b> · draft · 0/25 human-reviewed</span><span><b>Rubric starter-v1</b> · calibration required</span><span><b>R4-CORE20 / R6-YP-CORE20</b> · not comparable</span><button class="link-button" data-open-rubric>${state.lang === 'zh' ? '查看 rubric / golden ↓' : 'Open rubric / golden ↓'}</button></div>
  <div class="grid cols-2">
    <section class="card eval-card"><div class="card-title"><div><div class="eyebrow">R4-CORE20 · retrieval only</div><h3>${esc(core.title)}</h3></div><span class="chip amber">${esc(core.status)}</span></div><div class="eval-big">${core.selected_count}<small> / ${core.denominator}</small></div><p class="small">${state.lang === 'zh' ? `<b>${esc(core.metric)}</b>：${esc(core.selected)}。17条命中是证据检索，不是回答准确率。` : `<b>${esc(core.metric)}</b> for ${esc(core.selected)}. The 17 hits are evidence retrieval, not answer accuracy.`}</p><div class="progress-line"><span>Hit@5</span><div class="bar-track"><div class="bar-fill" style="width:85%"></div></div><b>17/20</b></div><p class="micro">${esc(core.note)}</p></section>
    <section class="card eval-card ambertop"><div class="card-title"><div><div class="eyebrow">R6-YP-CORE20 · N5 baseline + AI provisional</div><h3>${esc(agent.title)}</h3></div><span class="chip amber">provisional</span></div><div class="eval-big">${agent.retrieval_hit5}<small> / ${agent.denominator}</small></div><p class="small">${state.lang === 'zh' ? `严格引文跨度检索Hit@5。同一20题产生 <b>${agent.answered}条已回答</b>、<b>${agent.abstained}条拒答</b>；AI初评为 <b>${agent.pass}通过 / ${agent.fail}失败 / ${agent.pending}待裁决</b>。` : `Strict quoted-span retrieval Hit@5. The same 20 cases produced <b>${agent.answered} answered</b> and <b>${agent.abstained} abstained</b>; AI review was <b>${agent.pass} pass / ${agent.fail} fail / ${agent.pending} pending</b>.`}</p><p class="micro">${esc(agent.note)}</p><p class="micro">${state.lang === 'zh' ? `R06人工裁决：${esc(agent.manual_pass)}通过 / ${esc(agent.manual_fail)}失败；2题人工裁决、18题仍为AI-only；④⑥双评尚未完成。` : `R06 manual adjudication: ${esc(agent.manual_pass)} pass / ${esc(agent.manual_fail)} fail; 2 manual, 18 still AI-only; double review pending.`}</p>${agent.hard_fail_candidates ? `<div class="notice" style="border-left-color:var(--red);background:var(--red-soft);color:var(--red);margin-top:8px"><b>${state.lang === 'zh' ? '硬失败候选' : 'Hard-fail candidate'}: ${agent.hard_fail_candidates}</b> · ${state.lang === 'zh' ? '分类/严重等级待人工确认；不能被加权平均抵消。' : 'classification/severity pending human confirmation; cannot be offset by an average.'}</div>` : ''}</section>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Ablation</div><h3>Rerank depth changes the evidence hit rate</h3></div><span class="badge">R4 draft</span></div><div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Depth</th><th>Hit@1</th><th>Hit@5</th><th>Mean latency</th><th>Median latency</th><th>p95 latency*</th></tr></thead><tbody>${core.ablation.map(x => `<tr><td>${esc(x.configuration)}</td><td>${x.depth}</td><td>${x.hit1}/20</td><td><b>${x.hit5}/20</b></td><td>${x.latency_mean.toFixed(3)} s</td><td>${x.latency_median.toFixed(3)} s</td><td>${x.latency_p95.toFixed(3)} s</td></tr>`).join('')}</tbody></table></div><p class="micro" style="margin-top:11px">The rerank depth was selected on the same draft CORE set, so this is configuration-selection evidence, not an unbiased held-out claim.</p><div class="notice" style="margin-top:10px">Source check: the E5-only p95 in R04’s CSV (0.013 s) is lower than its mean (0.164 s). Treat that p95 as unverified; do not quote it in the video until role4 explains the aggregation.</div><div class="notice teal" style="margin-top:8px">18/20 is the rerank@100 ablation; the selected configuration is rerank@50 at 17/20 because it is faster. This is not a held-out optimality claim.</div></section>
  <div class="grid cols-2" style="margin-top:17px">
    <section class="card"><div class="card-title"><div><div class="eyebrow">Database workload supplement</div><h3>Index benefit depends on the query</h3></div><span class="chip amber">R01 supplement</span></div><div class="table-wrap"><table><thead><tr><th>Scale</th><th>Query</th><th>Median no index</th><th>Median indexed</th><th>p95 batch mean no index</th><th>p95 batch mean indexed</th></tr></thead><tbody>${data.f4.db.rows.map(x => `<tr><td>${esc(x.scale)}</td><td>${esc(x.query)}</td><td>${x.no_index.toFixed(6)} ms</td><td><b>${x.indexed.toFixed(6)} ms</b></td><td>${x.no_index_p95.toFixed(6)} ms</td><td>${x.indexed_p95.toFixed(6)} ms</td></tr>`).join('')}</tbody></table></div><p class="micro" style="margin-top:10px">${esc(data.f4.db.method)}</p><div class="notice" style="margin-top:10px">${esc(data.f4.db.takeaway)}</div></section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">Usability</div><h3>Task-based study is still not run</h3></div><span class="chip red">not run</span></div><div class="flow"><div class="flow-node"><b>Planned study</b><br><span class="micro">${esc(data.f4.usability.plan)}</span></div><div class="flow-line"></div><div class="flow-node"><b>No fabricated result</b><br><span class="micro">${esc(data.f4.usability.note)}</span></div></div><p class="micro" style="margin-top:14px">The database workload is a role1 supplemental experiment; it is not role4 independent acceptance. DB and usability are kept separate from retrieval Hit@5.</p></section>
  </div>  <div class="grid cols-2" style="margin-top:17px"><section class="card"><div class="card-title"><div><div class="eyebrow">Failure attribution</div><h3>Named R4 misses</h3></div><span class="chip red">3 shown</span></div><div class="failure-list">${core.failures.map(x => `<div class="failure"><b>${esc(x.case_id)} · ${esc(x.topic)}</b><p>${esc(x.query)}</p><small>${esc(x.reason)}</small></div>`).join('')}</div></section><section class="card" id="boundaries"><div class="card-title"><div><div class="eyebrow">Read the scope</div><h3>What must stay separate</h3></div><span class="badge">boundaries</span></div><div class="timeline">${(state.lang === 'zh' ? ["检索证据、回答状态与暂定任务判断衡量的是不同事情。","R04正式数据库性能与可用性研究尚未运行；这里表格是R01内存副本补充实验，不是独立验收，也不代表生产环境性能。","不主张正式回答准确率或N7验收结果。"] : data.f4.boundaries).map(x => `<div class="timeline-item"><strong>${esc(x)}</strong></div>`).join('')}</div><div class="notice" style="margin-top:6px">Non-retrieval safety: ${agent.nonretrieval_safe}/5 safe, ${agent.nonretrieval_full_action}/5 fully met the expected action. The gap is a task-completion gap, not a fabricated-answer claim.</div></section></div>
  ${f4RubricGold(data)}
  ${footer('Finish with delivery status', 'delivery')}`;
  document.querySelector('[data-open-rubric]')?.addEventListener('click', () => {
    const box = document.getElementById('rubric-gold');
    if (box) { box.open = true; box.scrollIntoView({behavior: 'smooth', block: 'start'}); }
  });
}


function f4RubricGold(data) {
  const zh = state.lang === 'zh';
  const rubric = data.f4.rubric;
  const gold = data.f4.gold;
  const dims = rubric.dimensions || [];
  const roleName = value => String(value || '').replace(/^role/i, 'R0');
  const roleText = `${roleName(rubric.owner_role)} ${zh ? '维护' : 'owner'} → ${roleName(rubric.reviewer_role)} ${zh ? '复核' : 'reviewer'}`;
  const keyRules = zh ? [
    '关键错误触发 hard fail，不能被加权平均抵消。',
    'Hit@5 不从第6条补位；失败题保留在分母。',
    '20题冻结CORE的组内门槛为≥14/20（70%），不是课程官方硬指标。',
    'R4DEV 5题只用于校准，不进入CORE20 Hit@5分母。'
  ] : [
    'A key error triggers hard fail and cannot be offset by a weighted average.',
    'Hit@5 does not backfill from rank 6; failed cases stay in the denominator.',
    'Internal gate for a frozen 20-case CORE is ≥14/20 (70%), not a course-official hard metric.',
    'R4DEV 5 cases are calibration only and are not in the CORE20 Hit@5 denominator.'
  ];
  return `<details class="card rubric-gold" id="rubric-gold" style="margin-top:17px"><summary><span><span class="eyebrow">${zh ? '内测评' : 'INTERNAL EVALUATION'}</span><b>${zh ? 'Rubric 与 golden 题集' : 'Rubric and golden sets'}</b></span><span class="chip amber">${zh ? '点击展开' : 'expand'}</span></summary>
    <div class="rubric-body"><div class="grid cols-2">
      <section class="card nested-card"><div class="card-title"><div><div class="eyebrow">R06 rubric</div><h3>${esc(rubric.version)} · ${zh ? '正式测试前需校准' : 'calibration required'}</h3></div><span class="badge">${esc(roleText)}</span></div>
        <div class="rubric-list">${dims.map(d => `<details class="rubric-dim"><summary><b>${esc(d.id)}</b><span>${d.weight}%</span></summary><div>${Object.entries(d.anchors || {}).sort((a,b) => Number(b[0]) - Number(a[0])).map(([score, text]) => `<p><b>${esc(score)}</b> ${esc(text)}</p>`).join('')}</div></details>`).join('')}</div>
        <div class="notice amber" style="margin-top:10px"><b>${zh ? 'Hard fail：' : 'Hard fail:'}</b> ${rubric.hard_fail_conditions.map(x => esc(x)).join(' · ')}</div>
        <div class="rubric-key-rules"><b>${zh ? '关键规则' : 'Key rules'}</b><ul>${keyRules.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <details class="rubric-dim" style="margin-top:8px"><summary><b>${zh ? '完整评分规则' : 'Full scoring rules'}</b><span>${rubric.scoring_rules.length}</span></summary><div>${rubric.scoring_rules.map(x => `<p>${esc(x)}</p>`).join('')}</div></details>
        <details class="rubric-dim" style="margin-top:6px"><summary><b>${zh ? '检索规则' : 'Retrieval rules'}</b><span>${Object.keys(rubric.retrieval_rules || {}).length}</span></summary><div>${Object.entries(rubric.retrieval_rules || {}).map(([k,v]) => `<p><b>${esc(k)}</b> ${esc(String(v))}</p>`).join('')}</div></details>
        <p class="micro" style="margin-top:9px">${zh ? '维度0–4；N/A单独记录；加权分只在相同适用维度集合内比较。锚点原文为中文。' : 'Dimensions 0–4; N/A is recorded separately; weighted scores are comparable only within the same applicable dimension set. Anchor text is preserved from the Chinese rubric source.'}</p>
      </section>
      <section class="card nested-card"><div class="card-title"><div><div class="eyebrow">Golden sets</div><h3>${zh ? 'CORE20 与 R4DEV 的字段' : 'Fields behind CORE20 and R4DEV'}</h3></div><span class="chip amber">draft</span></div>
        <div class="kpi-row compact">${[['CORE20', gold.core.rows, gold.core.required_facts, gold.core.gold_evidence], ['R4DEV', gold.dev.rows, gold.dev.required_facts, gold.dev.gold_evidence]].map(([name, rows, facts, evidence]) => `<div class="kpi"><b>${rows}</b><span>${name} ${zh ? '题' : 'cases'}</span><small>${facts} facts · ${evidence} evidence</small></div>`).join('')}</div>
        <div class="gold-status-row"><span class="chip">answerable ${gold.core.answerable}/${gold.core.rows}</span><span class="chip neutral">synthetic=false</span><span class="chip neutral">forbidden_claims=0</span><span class="chip amber">human_reviewed=false</span></div>
        <div class="gold-fields"><span><b>query</b> + persona + as_of</span><span><b>required_facts</b> · f1/f2 + critical</span><span><b>gold_evidence</b> · e1 + quote/locator + fact_ids</span><span><b>sufficient_evidence_sets</b> · e1</span><span><b>forbidden_claims</b> · required_clarifications</span><span><b>review_status</b> = draft · <b>human_reviewed</b> = false</span></div>
        <p class="micro" style="margin-top:10px">${zh ? 'golden 是草稿候选集：review_status=draft，human_reviewed=false；R4DEV 只用于校准，不是正式人工验收。' : esc(gold.note)}</p>
      </section>
    </div>
    <section class="card nested-card" style="margin-top:12px"><div class="card-title"><div><div class="eyebrow">Synthetic schema examples</div><h3>${zh ? '题目结构如何被证据支持（示例）' : 'How a case is structured (synthetic example)'}</h3></div><span class="badge">${gold.samples.length} synthetic</span></div>
      ${gold.samples.map(x => `<details class="gold-case"><summary><b>${esc(x.id)}</b><span>${esc(x.query)}</span><span class="chip ${x.human_reviewed ? '' : 'amber'}">${x.human_reviewed ? 'human reviewed' : 'draft / not human-reviewed'}</span></summary><div><p><b>${zh ? '必要事实' : 'Required facts'}</b></p><ol>${(x.required_facts_meta || []).map(f => `<li><b>${esc(f.id)}</b> · ${esc(f.text)} ${f.critical ? `<span class="chip red">critical</span>` : ''}</li>`).join('')}</ol><p><b>${zh ? '金标证据' : 'Gold evidence'}</b></p>${x.gold_evidence.map(e => `<div class="gold-evidence"><span class="mono micro">${esc(e.id)} → ${esc((e.fact_ids || []).join(', '))} · ${esc(e.doc_id)}</span><p>${esc(e.locator)}</p><blockquote>${esc(e.quote)}</blockquote></div>`).join('')}<p class="micro"><b>sufficient_evidence_sets</b>: ${(x.sufficient_evidence_sets || []).map(s => esc(s.join('+'))).join(' · ') || '—'}</p><p class="micro">${zh ? 'forbidden claims' : 'forbidden claims'}: ${x.forbidden_claims.length ? x.forbidden_claims.map(esc).join(' · ') : '—'}</p></div></details>`).join('')}
      <div class="notice teal" style="margin-top:10px">${zh ? '这里只展示结构示例，不是真实 CORE20/R4DEV 题目；真实 gold 受控存放，不上公开前端。' : 'These are schema examples, not real CORE20/R4DEV items. Actual gold is controlled and not shipped to the public frontend.'}</div>
    </section></div>
  </details>`;
}

function renderDelivery(data) {
  app.innerHTML = `${pageHead('F5 · DELIVERY', 'A prototype is only as useful as its <em>handoff</em>.', 'The code, evidence and interface are ready to inspect. The final PDF, the 5–8 minute video and the public video link still need the group to freeze and upload them.', 'Submission deadline', '2026-12-06 23:59 · PDF named XXXX-report.pdf', 'GitHub: /zhewangguaiguaide/5003')}
  <div class="grid cols-2" style="margin-top:17px">
    <section class="card"><div class="card-title"><div><div class="eyebrow">Submission status</div><h3>What is ready now</h3></div><span class="badge">internal draft</span></div>${data.f5.deliverables.map(([title, detail, status]) => `<div class="deliverable"><span><b>${esc(title)}</b><br>${esc(detail)}</span><span class="chip ${status === 'Available locally' ? '' : 'amber'}">${esc(status)}</span></div>`).join('')}</section>
    <section class="card"><div class="card-title"><div><div class="eyebrow">Source snapshot</div><h3>What the package contains</h3></div><span class="badge">c7b067f</span></div><p class="small">${state.lang === 'zh' ? '后端是76个Git跟踪文件；前端是独立可运行层；语料与索引按SHA绑定。' : 'The backend is a 76-file Git snapshot; the frontend is a separate runnable layer; corpus and index are SHA-bound.'}</p><div class="run-meta">${statPills([['Backend', data.meta.commits.backend], ['R4 eval', data.meta.commits.retrieval_eval], ['R6 eval', data.meta.commits.agent_eval], ['Docs', data.meta.documents]])}</div><p><a href="${esc(data.meta.repo)}" target="_blank" rel="noopener">${state.lang === 'zh' ? '打开GitHub仓库 ↗' : 'Open the GitHub repository ↗'}</a></p></section>
  </div>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Architecture / commands</div><h3>Open 00 for the system view</h3></div><span class="badge">00</span></div><p class="small">${state.lang === 'zh' ? '离线/在线双车道、模块链、人机交互与核心命令都在00总览页；本页只保留交付状态、源码快照、三条版本车道和交接。' : 'The two-lane architecture, module chain, human-machine loop and core commands live on the 00 overview page. This page tracks delivery status, source snapshot, version lanes and handoff only.'}</p><button class="button secondary" data-route="overview">${state.lang === 'zh' ? '回到00总览' : 'Back to 00 overview'}</button></section>
  <section class="card" style="margin-top:17px"><div class="card-title"><div><div class="eyebrow">Glossary</div><h3>Internal codes in plain language</h3></div><span class="badge">first-time reader</span></div><div class="grid cols-3">${(state.lang === 'zh' ? [['F1–F5','五个页面：提问、数据、检索、评估、交付'],['R01–R06','六个岗位模块；数字是角色编号，不是模型版本'],['N5 / N7','N5=单轮RAG；N7=有界多轮Agent'],['FAISS','向量相似度检索；863是R03对比构建，881是R05运行快照'],['CORE20','R4的20题检索评估；Hit@5不是回答准确率'],['Synthetic / Replay','合成夹具/历史回放；与真实N5/N7运行分开']] : [['F1–F5','Five views: Ask, Data, Retrieval, Evaluation, Delivery'],['R01–R06','Six role modules; numbers identify owners, not model versions'],['N5 / N7','N5 = one-pass RAG; N7 = bounded multi-round agent'],['FAISS','Vector-similarity retrieval; 863 is the R03 comparison, 881 the R05 runtime'],['CORE20','R4 20-question retrieval evaluation; Hit@5 is not answer accuracy'],['Synthetic / Replay','Fixtures/historical replay, separate from a real N5/N7 run']]).map(([a,b]) => `<div class="flow-node"><b>${esc(a)}</b><br><span class="micro">${esc(b)}</span></div>`).join('')}</div></section>
  <div class="grid cols-3" style="margin-top:17px"><section class="card" id="team-card"><div class="card-title"><div><div class="eyebrow">Team</div><h3>Contribution map</h3></div></div><div class="team-list">${data.f5.team.map(([name, role]) => `<div class="team-row"><b>${esc(name)}</b><span>${esc(role)}</span></div>`).join('')}</div></section><section class="card" id="version-lanes"><div class="card-title"><div><div class="eyebrow">System</div><h3>Three lanes, not one mixed chain</h3></div></div><div class="flow"><div class="flow-node"><b>SQLite source</b><br><span class="micro">documents 159 · records 83 · published chunks 0</span></div><div class="flow-line"></div><div class="flow-node"><b>R05 runtime · ${num(data.f3.index.runtime_chunks)} chunks</b><br><span class="micro">N5 / N7 use this index · R05 SHA ${esc(shortSHA(data.f3.index.index_sha256))}</span></div><div class="flow-line"></div><div class="flow-node"><b>R03 comparison · ${num(data.f3.index.comparison_chunks)} chunks</b><br><span class="micro">F3 only · frozen scores/titles · not the N5/N7 runtime</span></div></div><div class="notice teal" style="margin-top:9px">${state.lang === 'zh' ? '不要把R03的863写成N5/N7运行索引；运行索引是R05的881。' : 'Do not use the R03 863 as the N5/N7 runtime index; the runtime index is R05 881.'}</div></section><section class="card"><div class="card-title"><div><div class="eyebrow">Next moves</div><h3>Before the final upload</h3></div><span class="chip amber">pending</span></div><div class="timeline">${state.lang === 'zh' ? '<div class="timeline-item"><strong>合并报告章节</strong><span>按R01–R06模块索引合并，导出一个PDF并确认命名规则。</span></div><div class="timeline-item"><strong>录制演示</strong><span>按最终镜头表录制，保留冻结/回放标签。</span></div><div class="timeline-item"><strong>上传并验证链接</strong><span>把可访问的视频URL写入最终报告。</span></div>' : '<div class="timeline-item"><strong>Merge report chapters</strong><span>Use the R01–R06 module index; export one PDF and confirm the naming rule.</span></div><div class="timeline-item"><strong>Record the demo</strong><span>Use the final shot list; keep frozen/replay labels visible.</span></div><div class="timeline-item"><strong>Upload and test the link</strong><span>Paste the accessible video URL into the final report.</span></div>'}</div><div class="notice teal" style="margin-top:12px">${state.lang === 'zh' ? '运行入口：' : 'Run this interface with '}<span class="mono">python app.py --open</span>${state.lang === 'zh' ? '。' : '.'}</div></section></div>
  ${footer('Back to overview', 'overview')}`;
  bindDelivery();
}

function bindDelivery() {
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    const text = decodeURIComponent(button.dataset.copy || '');
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = state.lang === 'zh' ? '已复制' : 'Copied';
      showToast(state.lang === 'zh' ? '命令已复制。' : 'Command copied.');
    } catch (error) {
      showToast(state.lang === 'zh' ? '浏览器未允许自动复制，请手动选择命令。' : 'Clipboard permission denied; select the command manually.');
    }
  }));
}

function bindData(data) {
  document.querySelectorAll('[data-sql-id]').forEach(btn => btn.addEventListener('click', () => { state.sqlId = btn.dataset.sqlId; render(); }));
  const run = document.getElementById('run-sql');
  if (!run) return;
  run.addEventListener('click', async () => {
    const box = document.getElementById('sql-result');
    run.disabled = true; run.textContent = state.lang === 'zh' ? '执行中…' : 'Running…';
    box.innerHTML = '<div class="loading-card"><div class="loader"></div><p>Executing read-only preset…</p></div>';
    try {
      const response = await fetch('/api/sql', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:state.sqlId})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'SQL execution failed');
      box.innerHTML = sqlResultHTML({...payload, explain: payload.plan}, true);
      showToast(state.lang === 'zh' ? `只读查询已执行，返回${payload.rows.length}行。` : `Read-only query returned ${payload.rows.length} rows.`);
    } catch (error) {
      box.innerHTML = `<div class="notice" style="border-left-color:var(--red);background:var(--red-soft);color:var(--red)">${esc(error.message)}</div>`;
    } finally {
      run.disabled = false; run.textContent = state.lang === 'zh' ? '运行只读查询' : 'Run read-only query';
    }
  });
}

function bindSources() {
  if (window.__dscSourcesBound) return;
  window.__dscSourcesBound = true;
  document.addEventListener('click', (event) => {
    const cite = event.target.closest('[data-cite]');
    if (cite) {
      const citation = (state.f1Result?.citations || []).find(item => item.source_id === cite.dataset.cite);
      if (citation) openSource(citation); else showToast('Citation not available in this view.');
      return;
    }
    const source = event.target.closest('[data-source]');
    if (source) {
      try { openSource(JSON.parse(decodeURIComponent(source.dataset.source))); }
      catch (error) { showToast('Could not open this source.'); }
      return;
    }
    if (event.target.closest('[data-close-drawer]')) closeDrawer();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { closeDrawer(); return; }
    if (event.key === 'Tab' && drawer.getAttribute('aria-hidden') === 'false') {
      const focusable = [...drawer.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(x => !x.disabled);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
}

function openSource(source) {
  window.__drawerReturnFocus = document.activeElement;
  document.body.style.overflow = 'hidden';
  const title = source.display_title || source.title || 'Evidence source';
  document.getElementById('drawer-title').textContent = title;
  const body = document.getElementById('drawer-body');
  const citationText = source.excerpt || source.text || 'The source excerpt is available in the evidence package. This interface shows the document identity and provenance.';
  body.innerHTML = `<div class="run-meta">${statPills([['Topic', source.topic || '—'], ['Score', source.score !== undefined ? Number(source.score).toFixed(4) : '—'], ['Chunk', source.chunk_id || 'document'], ['Year', source.academic_year || 'not recorded']])}</div><p><b>${esc(source.source_title || source.title || '')}</b></p><p class="mono small">${esc(source.chunk_id || '')}</p><p><a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener">${esc(source.url || 'No URL supplied')}</a></p><div class="excerpt">${esc(citationText)}</div><p class="micro" style="margin-top:14px">Evidence identity is not the same as semantic support. A URL and chunk ID prove where the text came from; a reviewer still has to decide whether it supports the claim.</p>`;
  drawer.setAttribute('aria-hidden', 'false');
  const close = drawer.querySelector('.icon-btn');
  if (close) close.focus();
}

function closeDrawer() {
  drawer.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
  if (window.__drawerReturnFocus && document.contains(window.__drawerReturnFocus)) window.__drawerReturnFocus.focus();
}

function bindNav() {
  if (window.__dscNavBound) return;
  window.__dscNavBound = true;
  document.addEventListener('click', (event) => {
    const el = event.target.closest('[data-route]');
    if (!el) return;
    event.preventDefault();
    const route = el.dataset.route;
    if (routes.includes(route)) {
      state.route = route;
      history.pushState(null, '', `#${route}`);
      render();
      window.scrollTo({top: 0, behavior: 'instant'});
    }
  });
  window.addEventListener('popstate', () => {
    const route = window.location.hash.replace(/^#/, '');
    if (routes.includes(route)) { state.route = route; render(); window.scrollTo({top: 0, behavior: 'instant'}); }
  });
}

function render() {
  document.getElementById('toast').classList.remove('show');
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.route === state.route));
  if (!DATA) return;
  if (state.route === 'overview') renderOverview(DATA);
  else if (state.route === 'ask') renderAsk(DATA);
  else if (state.route === 'data') renderData(DATA);
  else if (state.route === 'retrieval') renderRetrieval(DATA);
  else if (state.route === 'evaluation') renderEvaluation(DATA);
  else renderDelivery(DATA);
  bindSources();
  bindNav();
  applyLanguage();
  if (window.innerWidth <= 760) setTimeout(() => document.querySelector('.nav-item.active')?.scrollIntoView({inline:'center', block:'nearest'}), 0);
}

async function boot() {
  try {
    const response = await fetch('/data/ui_data.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`Data load failed: ${response.status}`);
    DATA = await response.json();
    const hashRoute = window.location.hash.replace(/^#/, '');
    state.route = routes.includes(hashRoute) ? hashRoute : 'overview';
    bindLanguage();
    render();
  } catch (error) {
    app.innerHTML = `<section class="card"><div class="eyebrow">Load error</div><h1>Evidence data did not load.</h1><p class="lede">${esc(error.message)}</p><p class="small">Start the local server with <span class="mono">python app.py --open</span> and use the HTTP address printed in the launcher window.</p></section>`;
  }
}

// --- Bilingual presentation layer -------------------------------------------------
const UI_ZH = {
  "Published SQLite · source store · chunks 0": "已发布SQLite · 源文档库 · chunks 0",
  "R05 runtime · N5/N7 index · 881 chunks": "R05运行库 · N5/N7索引 · 881片段",
  "R03 comparison · retrieval run · 863 chunks": "R03对比 · 检索运行 · 863片段",

  "Library access": "图书馆进入要求",
  "invalid_input": "输入无效",
  "Three kinds of demo — keep them separate:": "三种演示要分清：",
  "Recorded replay is a historical summary; synthetic live wiring only proves the UI/CLI connection; real N5/N7 needs the model and key. No policy answer is fabricated here.": "已记录回放是历史摘要；合成实时接线只证明UI/CLI能连通；真实N5/N7需要模型和密钥。这里不补造政策答案。",
  "Hit@5 only says required evidence appeared in the top five; it is not answer accuracy. R4 and R6 are different question sets; AI review, human adjudication and formal acceptance are different levels.": "Hit@5只表示前5条是否命中所需证据，不等于回答正确率。R4与R6是不同题集；AI初评、人工裁决和正式验收不是同一层级。",
  "Three artifacts, three different counts": "三个产物、三个不同计数",
  "Published SQLite: chunks 0": "已发布SQLite：chunks 0",
  "R05 runtime: 881 chunks": "R05运行库：881片段",
  "R03 comparison: 863 chunks": "R03对比：863片段",
  "The published SQLite table has no chunk rows. The R05 backend uses a separate 881-chunk runtime index; R03 reports a separate 863-chunk local comparison. The counts are not a data-quality contradiction; they are different builds.": "已发布SQLite没有chunk行；R05后端使用独立的881片段运行索引；R03报告独立的863片段本地对比。三个数字不是数据质量矛盾，而是三个不同构建。",
  "Version lanes: scores and titles are the R03 863-chunk comparison; source-drawer excerpts map to the R05 881-chunk snapshot for inspection. Negative rerank scores are ranking values, not probabilities.": "版本分层：分数和标题来自R03的863片段对比；来源抽屉摘录映射到R05的881片段快照。负的Rerank分数是排序值，不是概率。",
  "Internal codes in plain language": "内部代号白话表",
  "first-time reader": "第一次阅读",

  "New subprocess output": "新的子进程输出",
  "Launch UI": "启动界面",
  "Backend demo (no key)": "后端演示（无需密钥）",
  "Database status": "数据库状态",
  "Real N5/N7 (881 snapshot; model + key required)": "真实N5/N7（881快照；需要模型与密钥）",
  "Health check": "健康检查",
  "Run synthetic backend demo": "运行合成后端演示",
  "fees": "学费支付",
  "library": "图书馆",
  "One sentence on what is proven and what remains": "用一句话说明证明了什么、还缺什么",

  "Group information": "组员信息",
  "Names, undergraduate majors, roles and contribution text": "姓名、本科专业、角色与贡献说明",
  "Pending confirmation": "待本人确认",

  "snapshot integrity ok": "快照完整性正常",
  "Snapshot FK check": "快照外键检查",
  "integrity_check and foreign_key_check describe this snapshot only; they do not prove historical FK enforcement or semantic correctness.": "integrity_check和foreign_key_check只描述当前快照，不能证明历史写入一直启用外键，也不能证明语义正确。",

  "Pre-set query against the published database": "针对已发布数据库的预置查询",
  "Run read-only query": "运行只读查询",
  "Running…": "执行中…",
  "server-side preset": "服务端预置",
  "read-only": "只读",
  "Table": "表",
  "Rows": "行数",
  "Columns": "列数",
  "Reported result from the frozen evidence file. Press “Run read-only query” to execute this preset against the published SQLite database.": "这是冻结证据文件中的报告结果。点击“运行只读查询”会在已发布SQLite库上执行当前预置。",
  "Why this is a real execution: the endpoint opens the published SQLite file with mode=ro, runs only the selected preset and returns rows plus EXPLAIN QUERY PLAN. The database is not modified.": "为什么这是真实执行：接口以mode=ro打开已发布SQLite文件，只运行当前预置，返回行和EXPLAIN QUERY PLAN；数据库不会被修改。",
  "One sentence on what is proven and what remains": "用一句话说明证明了什么、还缺什么",
  "Health check": "健康检查",
  "Copy": "复制",
  "Copied": "已复制",
  "Command copied.": "命令已复制。",

  "Content duplicates removed": "已移除正文重复记录",
  "normalized-content fingerprint": "规范化正文指纹",
  "records=83 is the raw collection layer, not a complete source for the 159 documents; 119 documents have no academic_year, which does not mean the current year. Integrity/FK checks apply to this snapshot only.": "records=83是原始采集层，不是159篇文档的完整来源；119篇没有academic_year，不等于当前学年。完整性与外键检查只针对当前快照。",

  "p95 latency*": "p95延迟*",
  "Source check: the E5-only p95 in R04’s CSV (0.013 s) is lower than its mean (0.164 s). Treat that p95 as unverified; do not quote it in the video until role4 explains the aggregation.": "来源核对：R04的CSV中E5-only的p95为0.013秒，低于均值0.164秒。在该口径未解释前，不把这个p95写进视频。",
  "Health check": "健康检查",
  "Invoke-RestMethod http://127.0.0.1:8501/api/health": "Invoke-RestMethod http://127.0.0.1:8501/api/health",

  "7-minute demo route": "7分钟演示路线",
  "Video order and time budget": "视频顺序与时间预算",
  "430 sec · 50 sec spare": "430秒 · 余50秒",
  "Time": "时间",
  "Module": "模块",
  "Screen / action": "画面 / 操作",
  "Must show": "必须展示",
  "Priority": "优先级",
  "Opening": "开场",
  "F1 Ask": "F1 提问",
  "F2 Data": "F2 数据",
  "F3 Retrieval": "F3 检索",
  "F4 Evaluation": "F4 评估",
  "Architecture & commands": "架构与命令",
  "Delivery": "交付",
  "Close": "收尾",
  "Close source": "关闭",
  "F5 architecture + F1": "F5架构 + F1",
  "Question, topic, answer card, status, citations": "问题、主题、答案卡、状态、引用",
  "Coverage, funnel, Database & SQL tab": "覆盖、漏斗、数据库与SQL页签",
  "FAISS / Rerank toggle, Top-5, source drawer": "FAISS / Rerank切换、Top-5、来源抽屉",
  "CORE20, YP-CORE, DB supplement, boundaries": "CORE20、YP-CORE、数据库补充、边界",
  "F5 flow + command cards": "F5流程 + 命令卡",
  "F5 repository, report, video, test link": "F5仓库、报告、视频、测试链接",
  "Project goal; user → question → evidence → status": "项目目标；用户 → 问题 → 证据 → 状态",
  "Real input; answered vs no-evidence/clarify; citation mapping; synthetic/replay label": "真实输入；answered与无证据/澄清；引用映射；合成/回放标签",
  "159 docs, 8 topics, 216→34→23→159; schema, Q1 SQL and plan": "159文档、8主题、216→34→23→159；模式、Q1 SQL与计划",
  "863 chunks, 384 dims; separate score scales; failure case": "863片段、384维；分开的分数刻度；失败案例",
  "17/20 ≠ answer accuracy; 15/20 different set; DB p95 caveat; usability not run": "17/20 ≠ 回答准确率；15/20是另一题集；DB p95边界；可用性未运行",
  "UI → CLI/API → N5/N7 → Index/DB → JSONL; commands and run status": "UI → CLI/API → N5/N7 → 索引/DB → JSONL；命令与运行状态",
  "GitHub snapshot; final PDF/video/link status; contribution": "GitHub快照；最终PDF/视频/链接状态；贡献",
  "primary": "重点",
  "secondary": "次要",
  "Core architecture": "核心架构",
  "From question to evidence": "从问题到证据",
  "Commands": "命令",
  "What the video can execute": "视频可执行的命令",
  "copyable": "可复制",
  "Copy": "复制",
  "Database workload supplement": "数据库工作负载补充",
  "Index benefit depends on the query": "索引收益取决于查询",
  "R01 supplement": "R01补充",
  "Scale": "规模",
  "Query": "查询",
  "No index": "无二级索引",
  "Indexed": "有索引",
  "p95 no index": "p95无索引",
  "p95 indexed": "p95有索引",
  "Usability": "可用性",
  "Task-based study is still not run": "任务型可用性研究仍未运行",
  "not run": "未运行",
  "Planned study": "计划研究",
  "No fabricated result": "不编造结果",
  "The database workload is a role1 supplemental experiment; it is not role4 independent acceptance. DB and usability are kept separate from retrieval Hit@5.": "数据库工作负载是①的补充实验，不是④的独立验收；数据库与可用性要和检索Hit@5分开。",
  "In-memory read-only copies; 20 warm-ups, 101 paired batches, 100 execute+fetchall per batch; p95 is batch-average, not request tail.": "只读内存副本；20次预热、101组配对批次、每批100次execute+fetchall；p95是批均值，不是请求级尾延迟。",
  "Q2 improves; Q1 is a counterexample. Do not call every query faster.": "Q2改善；Q1是反例。不能宣称所有查询都变快。",
  "3–5 users × 5 tasks: fees, visa, calendar, FAQ, unsupported/personal-state": "3–5名用户 × 5项任务：学费、签证、校历、FAQ、不支持的问题/个人状态",
  "The template exists, but no sessions, success rate or Likert result are claimed.": "模板已存在，但目前没有用户会话、成功率或Likert结果。",
  "The 430-second route leaves 50 seconds below the 8-minute cap. Do not add content; replace or shorten a segment instead.": "430秒路线比8分钟上限少50秒；不要新增内容，只替换或压缩片段。",
  "The first two commands are safe without a model key. The real N5/N7 command needs the model, index and local key; the DB status command is read-only.": "前两条命令可在无密钥时做合成演示；真实N5/N7需要模型、索引和本机密钥；数据库状态命令为只读。",

  "F1 · ASK WITH EVIDENCE": "F1 · 基于证据提问",
  "F2 · DATA & DATABASE": "F2 · 数据与数据库",
  "F3 · RETRIEVAL OBSERVATION": "F3 · 检索观察",
  "F4 · EVALUATION": "F4 · 评估",
  "F5 · DELIVERY": "F5 · 交付",
  "Interface contract": "界面契约",
  "Question → status → citations → boundary.": "问题 → 状态 → 引用 → 边界。",
  "Tuition payment": "学费支付",
  "Chinese library query": "中文图书馆问题",
  "Need clarification": "需要澄清",
  "Frozen summary": "冻结摘要",
  "N7 DEV replay · 2026-11-19": "N7 DEV 回放 · 2026-11-19",
  "Evidence supports every requested fact.": "证据支持每一个被请求的事实。",
  "A user condition is required before retrieval.": "检索前需要补充用户条件。",
  "The available evidence cannot support a complete answer.": "现有证据不足以支持完整回答。",
  "Model or backend failed; no answer published.": "模型或后端失败，未发布答案。",
  "R4 CORE20 · retrieval only": "R4 CORE20 · 仅检索",
  "R6 YP-CORE · N5 baseline + AI provisional": "R6 YP-CORE · N5基线 + AI初评",
  "R6 YP-CORE · N5 one-pass + AI provisional review": "R6 YP-CORE · N5一遍式 + AI初评",
  "R4 CORE20 · retrieval only": "R4 CORE20 · 仅检索",
  "Status": "状态",
  "Draft retrieval and AI-provisional review.": "检索草稿与AI初评。",
  "The 17 hits are evidence retrieval, not answer accuracy.": "17条命中是证据检索，不是回答准确率。",
  "17/20 is evidence retrieval, not answer accuracy. Questions and the answer key are now public, so this is not a private held-out set.": "17/20是证据检索，不是回答准确率。题目和答案键已经公开，因此它不是私有留出集。",
  "AI review is provisional. 15/20 belongs to a different set from R4 CORE20 and cannot be plotted as a rerank comparison.": "AI评审是暂定结果。15/20属于另一套题集，不能与R4 CORE20画成Rerank前后对比。",
  "Retrieval evidence, answer status and provisional task judgment measure different things.": "检索证据、回答状态与暂定任务判断衡量的是不同事情。",
  "DB performance and usability templates exist, but no results are claimed.": "R04正式数据库性能与可用性研究尚未运行；这里表格是R01内存副本补充实验，不是独立验收，也不代表生产环境性能。",
  "No formal answer accuracy or N7 acceptance result is claimed.": "不主张正式回答准确率或N7验收结果。",
  "Evidence source": "证据来源",
  "SOURCE EVIDENCE": "来源证据",
  "Evidence": "证据",
  "Score": "分数",
  "Chunk": "片段",
  "Year": "学年",
  "not recorded": "未记录",
  "No URL supplied": "未提供URL",
  "Evidence identity is not the same as semantic support. A URL and chunk ID prove where the text came from; a reviewer still has to decide whether it supports the claim.": "证据身份不等于语义支持。URL和chunk ID证明文本来自哪里，但是否支持断言仍要由评审者判断。",
  "The source excerpt is available in the evidence package. This interface shows the document identity and provenance.": "原文摘录在证据包中；此界面展示文档身份与来源。",
  "Integration, frontend, database design, demo": "统合、前端、数据库设计与演示",
  "Collection, cleaning, data quality, F1/F2/F3": "采集、清洗、数据质量与F1/F2/F3",
  "Chunking, embedding, FAISS retrieval, F3": "切块、向量化、FAISS检索与F3",
  "Retrieval and database evaluation, F4": "检索与数据库评估、F4",
  "Query adaptation, N5/N7 backend, API": "查询适配、N5/N7后端与API",
  "Agent rubric, CORE review, failure analysis": "Agent rubric、CORE复核与失败归因",
  "The local snapshot contains 76 Git-tracked backend files. This frontend is a separate, runnable interface layer for the final package.": "本地快照包含76个Git跟踪后端文件；本前端是最终包中独立可运行的界面层。",
  "The code, evidence and interface are ready to inspect. The final PDF, the 5–8 minute video and the public video link still need the group to freeze and upload them.": "代码、证据和界面已可检查；最终PDF、5–8分钟视频和公开链接仍需组内冻结并上传。",
  "Source code": "源代码",
  "Yes": "是",
  "No": "否",
  "internal draft": "内部草稿",
  "raw records (crawl run 2026-10-11, all columns)": "原始记录（2026-10-11采集轮，全部栏目）",
  "rejected: failed / empty / navigation-thin": "排除：失败/空/只有导航",
  "removed: canonical-URL duplicates": "移除：规范URL重复",
  "removed: content-fingerprint duplicates": "移除：正文指纹重复",
  "final corpus.jsonl = documents (active)": "最终 corpus.jsonl = 活动 documents",
  "canonical URL (trailing slash)": "规范URL（尾斜杠）",
  "same normalized-content SHA-256 (alias URL: query/locale/path variant)": "规范化正文SHA-256相同（别名URL：查询/语言/路径变体）",
  "GitHub branch snapshot c7b067f + this frontend": "GitHub分支快照c7b067f + 本前端",
  "Available locally": "本地可用",
  "Final report PDF": "最终报告PDF",
  "Merge member chapters and export XXXX-report.pdf": "合并成员章节并导出XXXX-report.pdf",
  "Not yet merged": "尚未合并",
  "Video 5–8 min": "5–8分钟视频",
  "Record UI, query execution, data flow and backend": "录制界面、查询执行、数据流与后端",
  "Not yet recorded": "尚未录制",
  "Working video link": "可用视频链接",
  "Pending upload": "等待上传",
  "Open the GitHub repository ↗": "打开GitHub仓库 ↗",
  "Frozen evidence, not a live model claim · prepared 21 Nov 2026": "冻结证据，不是实时模型结果 · 2026年11月21日",
  "Use the tabs above to move through the evidence chain.": "用顶部标签沿证据链浏览。",  "Evidence-ready demo": "证据就绪演示",
  "CityU student services · DSC5003": "城大学生服务 · DSC5003",
  "Question workspace": "提问工作区",
  "Student question": "学生问题",
  "Topic": "主题",
  "All topics": "全部主题",
  "Optional filter": "可选筛选",
  "Recorded replay": "已记录回放",
  "Run synthetic backend demo": "运行合成后端演示",
  "Running fixture…": "正在运行合成联调…",
  "Synthetic live wiring": "合成实时接线",
  "RECORDED REPLAY": "已记录回放",
  "N7 DEV REPLAY · 2026-11-19": "N7 DEV 回放 · 2026-11-19",
  "FROZEN SUMMARY": "冻结摘要",
  "LIVE SYNTHETIC WIRING": "合成实时接线",
  "NEW SUBPROCESS OUTPUT": "新的子进程输出",
  "RECORDED RUN": "已记录运行",
  "Failure is a feature": "失败也是信息",
  "Statuses the UI must not blur": "界面不能混淆的状态",
  "F1 contract": "F1 契约",
  "Latency": "耗时",
  "Retrieval rounds": "检索轮数",
  "Model calls": "模型调用",
  "Tokens": "Token",
  "not exposed": "未暴露",
  "Trace": "过程",
  "What the run actually recorded": "这次运行实际记录了什么",
  "Input received": "收到输入",
  "Evidence and budget": "证据与预算",
  "Publication decision": "发布判断",
  "No citation published for this status.": "此状态没有发布引用。",
  "Answer text is intentionally withheld from this public replay.": "这次公开回放有意不展示答案正文。",
  "The run summary keeps the status, latency, citation IDs, and call counts. The private raw trace remains in the ignored run directory; no policy answer is re-created for the demo.": "运行摘要保留状态、耗时、引用ID和调用次数；私有原始轨迹仍在被忽略的运行目录中。演示没有重建任何政策答案。",
  "The public Git snapshot records status, counts and citation IDs; the private answer text and raw trace remain in the ignored run directory. This is not a new execution.": "公开Git快照只记录状态、计数和引用ID；私有答案正文与原始轨迹在忽略目录中。这里不是新的执行。",
  "The live button invokes the actual R05 CLI with --rag-demo. It proves the interface wiring; the fixture explicitly says it is not CityU policy or a model-quality result.": "实时按钮会调用真实的R05 CLI，并加上 --rag-demo。它只证明界面接线；夹具明确说明它不是城大政策，也不是模型质量结果。",
  "The public replay records counts and citation IDs only; raw trace stays private.": "公开回放只记录计数和引用ID；原始轨迹保持私有。",
  "The app maps citations to the source drawer.": "页面会把引用映射到来源抽屉。",
  "Statuses": "状态",
  "answered": "已回答",
  "clarify": "需澄清",
  "abstained": "证据不足拒答",
  "no_evidence": "无证据",
  "generation_error": "生成失败",
  "evidence_sufficient": "证据充分",
  "insufficient_evidence": "证据不足",
  "needs_clarification": "需要澄清",
  "invalid_response": "无效响应",
  "config_error": "配置错误",
  "source_mismatch": "来源版本不一致",
  "stale_evidence": "证据失效",
  "draft_retrieval_only": "检索草稿",
  "provisional": "暂定",
  "pending": "待完成",
  "answered · evidence_sufficient": "已回答 · 证据充分",
  "What data is inside?": "数据里面有什么？",
  "Compare retrieval modes": "比较检索模式",
  "Separate retrieval from answer quality": "区分检索与回答质量",
  "Finish with delivery status": "查看交付状态",
  "Answer contract": "回答契约",
  "Scope → evidence → answer → citations.": "范围 → 证据 → 回答 → 引用。",
  "F1 / R05 881 chunks": "F1 / R05 881片段",
  "Intent and scope": "意图与范围",
  "Generation and review": "生成与复核",
  "NO RELEVANT CHUNKS WERE RETURNED.": "没有返回相关片段。",
  "THE RETRIEVER OR SOURCE VALIDATION FAILED.": "检索器或来源校验失败。",
  "THE MODEL OUTPUT FAILED THE CONTRACT.": "模型输出不符合契约。",
  "EVIDENCE VERSION CHANGED BEFORE PUBLICATION.": "发布前证据版本发生变化。",
  "No relevant chunks were returned.": "没有返回相关片段。",
  "The retriever or source validation failed.": "检索器或来源校验失败。",
  "The model output failed the contract.": "模型输出不符合契约。",
  "Evidence version changed before publication.": "发布前证据版本发生变化。",
  "Answer text is intentionally withheld from this public replay. The run summary keeps the status, latency, citation IDs and call counts; no policy answer is re-created for the demo.": "这次公开回放有意不展示答案正文。运行摘要保留状态、耗时、引用ID和调用次数；演示没有重建任何政策答案。",
  "evidence_sufficient": "证据充分",
  "needs_clarification": "需要澄清",
  "repeated_query": "重复查询",
  "time_budget": "时间预算",
  "llm_budget": "模型调用预算",
  "Back to the question": "回到提问",
  "Data quality": "数据质量",
  "Knowledge base": "知识库",
  "Database & SQL": "数据库与SQL",
  "Coverage": "覆盖",
  "Documents by topic": "各主题文档数",
  "after rework": "返工后",
  "Cleaning funnel": "清洗漏斗",
  "What survives to the corpus": "哪些内容进入语料",
  "historical + recheck": "历史数据 + 复核",
  "Deduplication": "去重",
  "Alias URLs collapse to one record": "别名URL合并为一条记录",
  "Boundary handling": "边界处理",
  "Navigation-only pages stay out": "只有导航的页面被排除",
  "rule fired": "规则触发",
  "Active documents": "活动文档",
  "Topics": "主题",
  "Median document": "文档长度中位数",
  "Duplicate aliases": "重复别名",
  "characters": "字符",
  "content-fingerprint removals": "正文指纹去重",
  "13 / 13 configured seeds": "13/13 配置种子成功",
  "8 / 8": "8 / 8",
  "Median length 4,962 chars for the first topic; headline median is 2,905 characters. Coverage is 8 configured columns, not the whole CityU website.": "第一个主题的文档长度中位数为4,962字符；全部文档的中位数为2,905字符。覆盖的是8个配置栏目，不是城大网站全量。",
  "The 216/34/23 numbers come from the historical crawl run; 159 active documents were re-verified on 2026-11-11.": "216/34/23来自历史采集轮；159篇活动文档在2026-11-11重新核验。",
  "Rule: text under 300 chars, or under 400 chars with at least six short lines and no line over 100 chars.": "规则：正文少于300字符，或少于400字符且至少有六行短行、没有超过100字符的行时排除。",
  "SQLite record": "SQLite记录",
  "Published database snapshot": "已发布数据库快照",
  "integrity ok": "完整性正常",
  "Data model": "数据模型",
  "One real relationship": "唯一真实关系",
  "physical schema": "物理模式",
  "FAISS is a derived retrieval artifact, not a SQLite table. The published index has 881 chunks from a different build; the R03 F3 view reports 863 chunks from its new local build. Keep the version labels separate.": "FAISS是派生的检索产物，不是SQLite表。已发布索引是另一构建的881个片段；R03的F3页面报告新本地构建的863个片段。两种版本必须分开标注。",
  "SQLite is the source-document store; FAISS is a derived index. SHA fields are logical provenance, not a foreign key, and the schema does not prove full 3NF.": "SQLite保存源文档；FAISS是派生索引。SHA字段是逻辑溯源，不是外键；当前模式也没有证明完整3NF。",
  "JSONL fields": "JSONL字段",
  "documents columns": "documents列数",
  "Secondary indexes": "二级索引",
  "FK check": "外键检查",
  "empty": "空",
  "SQL evidence": "SQL证据",
  "Topic coverage query and plan": "主题覆盖查询与计划",
  "PLAN": "计划",
  "Docs": "文档数",
  "With year": "有学年",
  "Raw URL": "原始URL",
  "Kept canonical": "保留的规范URL",
  "Reason": "原因",
  "Page": "页面",
  "Chars": "字符数",
  "Raw layer": "原始层",
  "Documents": "活动文档",
  "Current snapshot": "当前快照",
  "159 active documents · 8 topics · 13/13 seeds.": "159篇活动文档 · 8个主题 · 13/13种子成功。",
  "R03 frozen comparison": "R03 冻结对比",
  "No topic filter, matching the R03 frozen run": "无主题过滤，与R03冻结运行一致",
  "Inspect the Top-5, not just the answer.": "检查Top-5，不只盯着答案。",
  "Query": "查询",
  "FAISS only": "仅FAISS",
  "+ Rerank": "+ Rerank",
  "Index identity": "索引身份",
  "What the 863 means": "863代表什么",
  "R03 build": "R03构建",
  "Corpus": "语料",
  "Chunks": "片段",
  "Vectors": "向量",
  "Dim": "维度",
  "Contrast case": "对照案例",
  "A real failure stays in view": "真实失败案例留在页面上",
  "not fixed": "未修复",
  "Read the caveat": "读清楚边界",
  "What this page does not claim": "本页不主张什么",
  "boundary": "边界",
  "FAISS similarity scores. The fourth row is an off-topic timetable result—visible, not hidden.": "FAISS相似度分数。第4行是偏离问题的课程时间冲突结果，故意保留而不隐藏。",
  "Rerank scores are cross-encoder scores, not comparable with FAISS cosine-like values. This is why the UI labels the scale.": "Rerank分数是cross-encoder分数，不能与FAISS的相近度数值直接比较；所以界面单独标注刻度。",
  "Top-1 shown; R03 records no direct answer in either Top-5. Reranking is not a universal fix.": "两种方法的Top-5都没有直接回答中文图书馆问题。Rerank不是通用解药。",
  "Titles and scores follow the R03 frozen comparison. URLs and excerpts are resolved to matching corpus chunks for inspection; FAISS and rerank scores use different scales.": "标题和分数沿用R03冻结对比；URL和摘录映射到对应语料片段供检查。FAISS与Rerank使用不同分数刻度。",
  "Admission": "申请",
  "Tuition & payment": "学费与缴费",
  "Library": "图书馆",
  "Not recorded": "未记录",
  "Ablation": "消融",
  "Rerank depth changes the evidence hit rate": "Rerank深度改变证据命中率",
  "R4 draft": "R4草稿",
  "Failure attribution": "失败归因",
  "Named R4 misses": "R4点名失败题",
  "3 shown": "展示3题",
  "Read the scope": "阅读口径",
  "What must stay separate": "哪些口径必须分开",
  "boundaries": "边界",
  "Configuration": "配置",
  "Depth": "深度",
  "Hit@1": "Hit@1",
  "Hit@5": "Hit@5",
  "Mean latency": "平均延迟",
  "p95 latency": "p95延迟",
  "The rerank depth was selected on the same draft CORE set, so this is configuration-selection evidence, not an unbiased held-out claim.": "Rerank深度是在同一份草稿CORE集上选出的，因此这是配置选择证据，不是无偏的留出集结论。",
  "Non-retrieval safety: 5/5 safe, 2/5 fully met the expected action. The gap is a task-completion gap, not a fabricated-answer claim.": "非检索安全行为：5/5安全，但只有2/5完全达到预期动作。差距是任务完成度，不是编造答案。",
  "Submission deadline": "提交截止",
  "2026-12-06 23:59 · PDF named XXXX-report.pdf": "2026-12-06 23:59 · PDF命名为XXXX-report.pdf",
  "Repository": "代码仓库",
  "Code and evidence": "代码与证据",
  "Submission status": "提交状态",
  "What is ready now": "现在已就绪的内容",
  "Team": "团队",
  "Contribution map": "贡献映射",
  "System": "系统",
  "One evidence chain": "一条证据链",
  "Next moves": "下一步",
  "Before the final upload": "最终上传前",
  "Source code": "源代码",
  "Yes": "是",
  "No": "否",
  "internal draft": "内部草稿",
  "raw records (crawl run 2026-10-11, all columns)": "原始记录（2026-10-11采集轮，全部栏目）",
  "rejected: failed / empty / navigation-thin": "排除：失败/空/只有导航",
  "removed: canonical-URL duplicates": "移除：规范URL重复",
  "removed: content-fingerprint duplicates": "移除：正文指纹重复",
  "final corpus.jsonl = documents (active)": "最终 corpus.jsonl = 活动 documents",
  "canonical URL (trailing slash)": "规范URL（尾斜杠）",
  "same normalized-content SHA-256 (alias URL: query/locale/path variant)": "规范化正文SHA-256相同（别名URL：查询/语言/路径变体）",
  "GitHub branch snapshot c7b067f + this frontend": "GitHub分支快照c7b067f + 本前端",
  "Available locally": "本地可用",
  "Final report PDF": "最终报告PDF",
  "Merge member chapters and export XXXX-report.pdf": "合并成员章节并导出XXXX-report.pdf",
  "Not yet merged": "尚未合并",
  "Video 5–8 min": "5–8分钟视频",
  "Record UI, query execution, data flow and backend": "录制界面、查询执行、数据流与后端",
  "Not yet recorded": "尚未录制",
  "Working video link": "可用视频链接",
  "Google Drive / OneDrive / Dropbox": "Google Drive / OneDrive / Dropbox",
  "Pending upload": "等待上传",
  "Use the R01-R06 module index; export one PDF and confirm the naming rule.": "按R01–R06模块索引合并，导出一个PDF并确认命名规则。",
  "Record the demo": "录制演示",
  "Use F1 → F2 → F3 → F4; keep frozen/replay labels visible.": "按F1 → F2 → F3 → F4演示，保留冻结/回放标签。",
  "Upload and test the link": "上传并验证链接",
  "Paste the accessible video URL into the final report.": "把可访问的视频URL写入最终报告。",
  "Open the GitHub repository ↗": "打开GitHub仓库 ↗",
  "Run this interface with python app.py --open.": "运行入口：python app.py --open。",
  "Frozen evidence, not a live model claim · prepared 21 Nov 2026": "冻结证据，不是实时模型结果 · 2026年11月21日",
  "Use the tabs above to move through the evidence chain.": "用顶部标签沿证据链浏览。",
  "Next": "下一页"
};
const TOPIC_ZH = { "Admission": "申请", "Tuition & payment": "学费与缴费", "Library": "图书馆" };
const H1_ZH = {
  overview: '一条证据链，<em>两条车道</em>，六个模块。',
  ask: '用<em>证据</em>回答问题，不盲信答案。',
  data: '把<em>数据边界</em>讲清楚。',
  retrieval: '看<em>Top-5</em>，不只看答案。',
  evaluation: '守住每个<em>分母</em>的含义。',
  delivery: '原型的价值取决于<em>交接</em>。'
};
const LEDE_ZH = {
  overview: '先看整体：离线与在线如何共用同一套证据契约，R02–R06如何串成模块链，人在哪里核对，核心命令是什么。再进入01–05逐页看细节。',
  ask: '把学生问题转成一条可见的证据链：范围判断、检索、回答与引用。主按钮使用真实的881片段索引；配置模型时会再做一次独立证据复核。合成接线是单独的检查按钮，不提供政策答案。',
  data: '可靠的回答从可信语料开始。本页把采集质量与查询执行分开：覆盖、清洗漏斗、重复别名、导航页排除，以及SQLite记录。',
  retrieval: '检索层要展示证据轨迹：排名、分数、标题、主题、片段身份和原始URL。FAISS与Rerank的分数刻度分开，失败案例也保留。',
  evaluation: '本页有两套评估，它们使用不同题集、配置和判断。界面把它们分开，而不是把所有数字揉成一个“总分”。',
  delivery: '代码、证据和界面已经可以检查；最终PDF、5–8分钟视频和公开链接仍需要组内冻结并上传。'
};
function translateCore(core) {
  if (UI_ZH[core]) return UI_ZH[core];
  let m = core.match(/^(\d+) citations$/);
  if (m) return `${m[1]} 条引用`;
  m = core.match(/^(\d+) visible retrieval rounds returned chunks; (\d+) tool calls recorded\.$/);
  if (m) return `${m[1]} 轮可见检索返回片段；记录${m[2]}次工具调用。`;
  m = core.match(/^(\d+) visible retrieval rounds returned chunks; (\d+) model calls recorded\.$/);
  if (m) return `${m[1]} 轮可见检索返回片段；记录${m[2]}次模型调用。`;
  if (core.includes(' · ')) {
    const parts = core.split(' · ');
    if (parts.every(p => UI_ZH[p])) return parts.map(p => UI_ZH[p]).join(' · ');
  }
  m = core.match(/^answered — evidence_sufficient\. The app maps citations to the source drawer\.$/);
  if (m) return '已回答 — 证据充分。页面会把引用映射到来源抽屉。';
  return null;
}
function translateSubtree(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT','STYLE','TEXTAREA','INPUT'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const original = node.nodeValue;
    const leading = original.match(/^\s*/)[0];
    const trailing = original.match(/\s*$/)[0];
    const core = original.trim();
    const translated = translateCore(core);
    if (translated) node.nodeValue = leading + translated + trailing;
  }
  document.querySelectorAll('[title],[aria-label]').forEach(el => {
    for (const attr of ['title','aria-label']) {
      const value = el.getAttribute(attr);
      if (value && UI_ZH[value]) el.setAttribute(attr, UI_ZH[value]);
    }
  });
}
function applyLanguage() {
  const zh = state.lang === 'zh';
  document.documentElement.lang = zh ? 'zh-Hans' : 'en';
  const navLabels = zh ? ['架构','提问','数据','检索','评估','交付'] : ['Overview','Ask','Data','Retrieval','Evaluation','Delivery'];
  document.querySelectorAll('.nav-item').forEach((el, i) => {
    el.innerHTML = `<span>${String(i).padStart(2, '0')}</span>${navLabels[i]}`;
  });
  const small = document.querySelector('.brand-copy small');
  if (small) small.textContent = zh ? '城大学生服务 · DSC5003' : 'CityU student services · DSC5003';
  const meta = document.querySelector('.top-meta span:not(.live-dot)');
  if (meta) meta.textContent = zh ? '证据就绪演示' : 'Evidence-ready demo';
  document.querySelectorAll('[data-lang]').forEach(el => el.classList.toggle('active', el.dataset.lang === state.lang));
  if (!zh) return;
  const h1 = document.querySelector('.page-head h1');
  if (h1 && H1_ZH[state.route]) h1.innerHTML = H1_ZH[state.route];
  const lede = document.querySelector('.page-head .lede');
  if (lede && LEDE_ZH[state.route]) lede.textContent = LEDE_ZH[state.route];
  translateSubtree(document.body);
}
function bindLanguage() {
  document.querySelectorAll('[data-lang]').forEach(btn => btn.addEventListener('click', () => {
    state.lang = btn.dataset.lang === 'zh' ? 'zh' : 'en';
    try { localStorage.setItem('dsc5003.lang', state.lang); } catch {}
    render();
  }));
}
// ---------------------------------------------------------------------------------
window.addEventListener('hashchange', () => {
  const route = window.location.hash.replace(/^#/, '');
  if (routes.includes(route)) { state.route = route; render(); }
});
boot();









