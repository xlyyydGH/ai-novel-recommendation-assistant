const state = {
  userId: "user_xly",
  recommendations: [],
  fanqieItems: [],
  publicItems: [],
  profile: null,
  selectedBookId: null,
  selectedCandidate: null,
  selectedCandidateType: null,
  currentMemory: null,
  txtStories: [],
  txtAnalysis: null,
  llmStatus: null,
  llmAnalysis: null,
};

const $ = (selector) => document.querySelector(selector);

function storedView() {
  return "trial";
}

function setActiveView(view) {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;

  const knownViews = ["trial", "recovery", "recommend"];
  const nextView = knownViews.includes(view) ? view : "trial";
  shell.dataset.view = nextView;

  document.querySelectorAll(".view-tabs [data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === nextView);
  });

  try {
    localStorage.setItem("novelAssistantView", nextView);
  } catch {
    // Ignore storage errors in private or restricted browser contexts.
  }
}

function showTxtResult(selector) {
  const target = $(selector);
  if (target) target.hidden = false;
}

function hideTxtResult(selector) {
  const target = $(selector);
  if (target) target.hidden = true;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function formatScore(score) {
  return `${Math.round(score * 100)}%`;
}

function tagsHtml(tags, className = "tag") {
  return (tags || []).map((tag) => `<span class="${className}">${tag}</span>`).join("");
}

function fanqieBookUrl(book) {
  const id = String(book?.book_id || "").trim();
  return /^\d+$/.test(id) ? `https://fanqienovel.com/page/${id}` : "";
}

function sourceLink(url, label = "打开番茄") {
  if (!url) return "";
  return `<a class="source-link" href="${url}" target="_blank" rel="noreferrer">${label}</a>`;
}

function candidateIdentity(book) {
  return {
    book_id: String(book?.book_id || book?.title || "manual"),
    title: String(book?.title || book?.book_id || "未命名候选"),
  };
}

function trialReportHtml(report) {
  if (!report) return "";
  const meta = [report.hook_level ? `钩子强度：${report.hook_level}` : "", report.novelty ? `新鲜度：${report.novelty}` : ""]
    .filter(Boolean)
    .join(" · ");
  return `
    <details class="trial-report">
      <summary>
        <b>${report.headline || "无剧透选书报告"}</b>
        <span>展开</span>
      </summary>
      <div class="trial-report-body">
        ${meta ? `<small>${meta}</small>` : ""}
        ${report.core_hook ? `<small>${report.core_hook}</small>` : ""}
        ${report.intro_promise ? `<small>${report.intro_promise}</small>` : ""}
        ${(report.fit_points || []).length ? `<small>适合你：${report.fit_points.join(" ")}</small>` : ""}
        ${(report.risk_points || []).length ? `<small>可能不适合：${report.risk_points.join(" ")}</small>` : ""}
        ${report.try_plan ? `<small>${report.try_plan}</small>` : ""}
      </div>
    </details>`;
}

function readingRecapHtml(recap) {
  if (!recap) return "";
  return `
    <details class="trial-report recap-report">
      <summary>
        <b>${recap.headline || "续读恢复"}</b>
        <span>展开</span>
      </summary>
      <div class="trial-report-body">
        <small>${recap.basis || "基于书架记录生成。"}</small>
        <small>${recap.recap || ""}</small>
        ${(recap.memory_points || []).length ? `<small>记忆点：${recap.memory_points.join(" ")}</small>` : ""}
        ${recap.resume_hint ? `<small>${recap.resume_hint}</small>` : ""}
      </div>
    </details>`;
}

function memoryCardHtml(card) {
  return `
    <article class="memory-card">
      <div class="memory-card-head">
        <strong>${escapeHtml(card.chapter_title || `第 ${card.chapter_index} 章`)}</strong>
        <span>第 ${escapeHtml(card.chapter_index)} 章</span>
      </div>
      <p>${escapeHtml(card.summary)}</p>
      <div class="tag-row">${tagsHtml((card.key_events || []).slice(0, 5))}</div>
      <small>人物：${escapeHtml((card.characters || []).join("、") || "待继续识别")}</small>
      <small>伏笔：${escapeHtml((card.open_threads || []).slice(0, 2).join("；"))}</small>
      <span class="component-grid">
        <i>钩子 ${escapeHtml(card.scores?.hook_score ?? "--")}</i>
        <i>节奏 ${escapeHtml(card.scores?.pace_score ?? "--")}</i>
        <i>行动力 ${escapeHtml(card.scores?.protagonist_agency ?? "--")}</i>
      </span>
    </article>`;
}

function renderMemory(memory) {
  state.currentMemory = memory;
  $("#memoryCount").textContent = memory.cards.length ? `${memory.cards.length} 章已记忆` : "";
  if (!memory.cards.length) {
    $("#memoryContent").classList.add("empty-state");
    $("#memoryContent").innerHTML = `${escapeHtml(memory.aggregate.recap)}<br>${escapeHtml(memory.storage_policy)}`;
    return;
  }
  $("#memoryContent").classList.remove("empty-state");
  $("#memoryContent").innerHTML = `
    <div class="memory-aggregate">
      <b>剧情级续读恢复</b>
      <p>${escapeHtml(memory.aggregate.recap)}</p>
      <p>${escapeHtml(memory.aggregate.trial_report)}</p>
      <p><strong>续读提示：</strong>${escapeHtml(memory.aggregate.next_hint)}</p>
      <div class="tag-row">${tagsHtml(memory.aggregate.key_events || [])}</div>
      <small>${escapeHtml(memory.storage_policy)}</small>
    </div>
    <div class="memory-card-list">
      ${memory.cards.map(memoryCardHtml).join("")}
    </div>`;
}

function renderMemoryAssistant(memory) {
  if (!memory?.cards?.length) return false;
  $("#assistantContent").classList.remove("empty-state");
  $("#assistantContent").innerHTML = `
    <div class="chapter-box">
      <h3>剧情级续读恢复</h3>
      <p>${escapeHtml(memory.aggregate.recap)}</p>
      <p><strong>正文级试读判断：</strong>${escapeHtml(memory.aggregate.trial_report)}</p>
      <p><strong>继续阅读提示：</strong>${escapeHtml(memory.aggregate.next_hint)}</p>
      <div class="pill-list">${tagsHtml(memory.aggregate.open_threads || [], "risk-tag")}</div>
      <p><strong>置信度：</strong>${escapeHtml(memory.aggregate.confidence)}，基于 ${memory.cards.length} 章结构化记忆卡。</p>
    </div>`;
  return true;
}

async function loadChapterMemory(book) {
  if (!book) return;
  const identity = candidateIdentity(book);
  const memory = await api(`/api/chapter-memory?book_id=${encodeURIComponent(identity.book_id)}&title=${encodeURIComponent(identity.title)}`);
  renderMemory(memory);
  return memory;
}

function scoreChip(label, value) {
  return `<span class="score-chip"><b>${escapeHtml(label)}</b>${escapeHtml(value ?? "--")}</span>`;
}

function textList(items, className = "txt-list") {
  return `<ul class="${className}">${(items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function objectList(items, renderItem) {
  return `<ul class="txt-list">${(items || []).map((item) => `<li>${renderItem(item)}</li>`).join("")}</ul>`;
}

function renderTxtAnalysis(report) {
  state.txtAnalysis = report;
  const aggregate = report.aggregate;
  $("#txtStoryReport").classList.remove("empty-state");
  $("#txtStoryReport").innerHTML = `
    <section class="reader-report">
      <span class="eyebrow">已读取第 ${escapeHtml(report.story.range_start)} - ${escapeHtml(report.story.range_end)} 章 / 共 ${escapeHtml(report.story.chapter_count)} 章</span>
      <h3>${escapeHtml(report.story.title)}</h3>
      <div class="reader-grid">
        <article class="reader-block">
          <h4>这几章讲了什么</h4>
          <p>${escapeHtml(aggregate.what_happened || aggregate.recap)}</p>
        </article>
        <article class="reader-block">
          <h4>主角人物形象</h4>
          <p>${escapeHtml(aggregate.protagonist_profile || "需要 MiniMax 深度分析后给出更准确的人物形象。")}</p>
        </article>
        <article class="reader-block">
          <h4>剧情推进到哪里</h4>
          <p>${escapeHtml(aggregate.plot_progress || aggregate.next_reading_plan)}</p>
        </article>
        <article class="reader-block">
          <h4>是否值得继续读</h4>
          <p>${escapeHtml(aggregate.trial_verdict)}</p>
        </article>
      </div>
      <small>${escapeHtml(report.source_policy)}</small>
    </section>
  `;
}

function renderLlmStatus(status) {
  state.llmStatus = status;
  $("#txtLlmBtn").title = status.configured
    ? `${status.provider} ${status.model} 已配置`
    : "请先在 app/llm_settings.py 填写 MINIMAX_API_KEY";
  if (!status.configured) {
    showTxtResult("#txtLlmReport");
    $("#txtLlmReport").classList.add("empty-state");
    $("#txtLlmReport").innerHTML = `
      MiniMax M2.7 尚未配置。打开 <code>${escapeHtml(status.config_file)}</code>，
      填写 <code>MINIMAX_API_KEY</code> 后点击“MiniMax 深度判定”。
    `;
  }
}

function renderLlmAnalysis(payload) {
  if (!payload.ok) {
    showTxtResult("#txtLlmReport");
    $("#txtLlmReport").classList.add("empty-state");
    $("#txtLlmReport").innerHTML = `
      <b>MiniMax 未运行</b>
      <p>${escapeHtml(payload.error || "请先配置 API Key。")}</p>
      <small>${escapeHtml(payload.status?.note || "")}</small>
    `;
    return;
  }
  state.llmAnalysis = payload;
  const analysis = payload.analysis;
  const report = analysis.no_spoiler_trial_report || {};
  const recap = analysis.plot_recap || {};
  const protagonist = analysis.protagonist_profile || {};
  const characterFallback = (analysis.characters || [])[0] || {};
  const protagonistText = protagonist.image
    || [characterFallback.name, characterFallback.role, characterFallback.relationship, characterFallback.change].filter(Boolean).join("；")
    || "这段文本里主角形象还需要更多上下文确认。";
  const whatHappened = recap.what_happened || recap.recap || report.verdict || "MiniMax 已完成深度分析。";
  const progress = recap.current_progress || report.continue_plan || "继续阅读后可进一步判断剧情推进。";
  showTxtResult("#txtLlmReport");
  $("#txtLlmReport").classList.remove("empty-state");
  $("#txtLlmReport").innerHTML = `
    <section class="reader-report llm-reader-report">
      <span class="eyebrow">MiniMax ${escapeHtml(payload.model)}${payload.cache_hit ? " · 缓存命中" : ""}</span>
      <h3>${escapeHtml(analysis.story?.title || payload.input.title)}</h3>
      <div class="reader-grid">
        <article class="reader-block">
          <h4>这几章讲了什么</h4>
          <p>${escapeHtml(whatHappened)}</p>
        </article>
        <article class="reader-block">
          <h4>主角人物形象</h4>
          <p>${escapeHtml(protagonistText)}</p>
          ${protagonist.motivation ? `<small>当前动机：${escapeHtml(protagonist.motivation)}</small>` : ""}
        </article>
        <article class="reader-block">
          <h4>剧情推进到哪里</h4>
          <p>${escapeHtml(progress)}</p>
        </article>
        <article class="reader-block">
          <h4>是否值得继续读</h4>
          <p>${escapeHtml(report.verdict || "")}</p>
        </article>
      </div>
    </section>
  `;
}

async function loadTxtStories() {
  const data = await api("/api/txt-stories");
  state.txtStories = data.items;
  const select = $("#txtStorySelect");
  select.innerHTML = data.items
    .map((story) => `<option value="${escapeHtml(story.id)}">${escapeHtml(story.title)} · ${escapeHtml(story.chapter_count)} 章</option>`)
    .join("");
  if (!data.items.length) {
    $("#txtStoryReport").classList.add("empty-state");
    $("#txtStoryReport").textContent = `没有找到 TXT。把合法 TXT 放到 ${data.library_path} 后刷新页面。`;
    return;
  }
  select.value = data.items[0].id;
  syncTxtUptoLimit(data.items[0].id);
  await loadTxtAnalysis(data.items[0].id);
}

function syncTxtUptoLimit(storyId = $("#txtStorySelect").value) {
  const story = state.txtStories.find((item) => item.id === storyId);
  const input = $("#txtUptoInput");
  if (!story || !input) return;
  input.max = story.chapter_count;
  if (!Number(input.value) || Number(input.value) > story.chapter_count) {
    input.value = Math.min(300, story.chapter_count);
  }
  if (Number(input.value) < 1) {
    input.value = 1;
  }
}

async function loadTxtAnalysis(storyId = $("#txtStorySelect").value) {
  if (!storyId) return;
  $("#txtStoryReport").classList.add("empty-state");
  const start = Math.max(1, Number($("#txtStartInput").value || 1));
  const chapters = Math.max(1, Math.min(20, Number($("#txtCountInput").value || 3)));
  $("#txtStoryReport").textContent = `正在读取 TXT 第 ${start} 章起的 ${chapters} 章，并生成正文级报告...`;
  const report = await api(`/api/txt-story-analysis?id=${encodeURIComponent(storyId)}&start=${start}&chapters=${chapters}`);
  renderTxtAnalysis(report);
}

function renderProgressRecap(payload) {
  const recap = payload.recap;
  const story = payload.story;
  showTxtResult("#txtProgressRecap");
  $("#txtProgressRecap").classList.remove("empty-state");
  $("#txtProgressRecap").innerHTML = `
    <section class="reader-report progress-reader-report">
      <span class="eyebrow">读到第 ${escapeHtml(story.upto)} 章 / 共 ${escapeHtml(story.chapter_count)} 章</span>
      <h3>${escapeHtml(story.title)}</h3>
      <div class="reader-grid">
        <article class="reader-block">
          <h4>前面讲了什么</h4>
          <p>${escapeHtml(recap.what_happened)}</p>
        </article>
        <article class="reader-block">
          <h4>主角人物形象</h4>
          <p>${escapeHtml(recap.protagonist_profile)}</p>
        </article>
        <article class="reader-block">
          <h4>剧情推进到哪里</h4>
          <p>${escapeHtml(recap.plot_progress)}</p>
        </article>
        <article class="reader-block">
          <h4>接下来怎么接着读</h4>
          <p>${escapeHtml(recap.resume_hint)}</p>
        </article>
      </div>
    </section>
  `;
}

async function loadProgressRecap() {
  const storyId = $("#txtStorySelect").value;
  if (!storyId) return;
  syncTxtUptoLimit(storyId);
  const maxChapter = Number($("#txtUptoInput").max || 1);
  const upto = Math.max(1, Math.min(maxChapter, Number($("#txtUptoInput").value || 1)));
  $("#txtUptoInput").value = upto;
  $("#txtProgressBtn").disabled = true;
  showTxtResult("#txtProgressRecap");
  $("#txtProgressRecap").classList.add("empty-state");
  $("#txtProgressRecap").textContent = state.llmStatus?.configured
    ? `MiniMax 正在基于抽样章节生成读到第 ${upto} 章的续读恢复...`
    : `正在生成读到第 ${upto} 章的续读恢复...`;
  try {
    const payload = await api(`/api/txt-progress-recap?id=${encodeURIComponent(storyId)}&upto=${upto}&recent=15`);
    renderProgressRecap(payload);
  } catch (error) {
    $("#txtProgressRecap").classList.add("empty-state");
    $("#txtProgressRecap").innerHTML = `<b>续读恢复生成失败</b><p>${escapeHtml(error.message)}</p>`;
  } finally {
    $("#txtProgressBtn").disabled = false;
  }
}

async function loadLlmStatus() {
  const status = await api("/api/llm/status");
  renderLlmStatus(status);
}

async function loadTxtLlmAnalysis() {
  const storyId = $("#txtStorySelect").value;
  if (!storyId) return;
  const start = Math.max(1, Number($("#txtStartInput").value || 1));
  const chapters = Math.max(1, Math.min(20, Number($("#txtCountInput").value || 3)));
  $("#txtLlmBtn").disabled = true;
  $("#txtLlmBtn").textContent = "MiniMax 判定中...";
  showTxtResult("#txtLlmReport");
  $("#txtLlmReport").classList.add("empty-state");
  $("#txtLlmReport").textContent = `MiniMax 正在阅读第 ${start} 章起的 ${chapters} 章，并判断是否值得继续看...`;
  try {
    const payload = await api(`/api/txt-story-llm-analysis?id=${encodeURIComponent(storyId)}&start=${start}&chapters=${chapters}`);
    renderLlmAnalysis(payload);
  } catch (error) {
    $("#txtLlmReport").classList.add("empty-state");
    $("#txtLlmReport").innerHTML = `<b>MiniMax 调用失败</b><p>${escapeHtml(error.message)}</p>`;
  } finally {
    $("#txtLlmBtn").disabled = false;
    $("#txtLlmBtn").textContent = "MiniMax 深度判定";
  }
}

async function loadUsers() {
  const data = await api("/api/users");
  const select = $("#userSelect");
  select.innerHTML = data.items
    .map((user) => `<option value="${user.id}">${user.nickname}</option>`)
    .join("");
  select.value = state.userId;
}

async function loadRecommendations() {
  const data = await api(`/api/recommendations?user_id=${state.userId}&limit=20`);
  state.profile = data.profile;
  state.recommendations = data.items;
  renderProfile(data.profile, data.similar_readers);
  if ($("#recommendationList")) {
    state.selectedBookId = data.items[0]?.book_id || null;
    renderRecommendations(data.items);
    if (state.selectedBookId && !state.selectedCandidate) {
      await renderDetail(state.selectedBookId);
      await renderAssistant(state.selectedBookId);
    }
  }
}

async function loadFanqieProfile() {
  try {
    const [profile, recs] = await Promise.all([
      api("/api/fanqie/profile"),
      api("/api/fanqie/recommendations?limit=8"),
    ]);
    state.fanqieItems = recs.items;
    $("#fanqieCount").textContent = `${recs.items.length} 个书架内候选`;
    const positiveSignals = recs.basis.positive_signals.slice(0, 5).map(([name]) => name);
    const negativeSignals = recs.basis.negative_signals.slice(0, 3).map(([name]) => name);
    const uncertain = recs.basis.progress_uncertain_books.slice(0, 3);
    const loved = recs.basis.positive_books.slice(0, 4);
    const metrics = recs.metrics;
    $("#fanqieProfile").classList.remove("empty-state");
    $("#fanqieProfile").innerHTML = `
      <div class="insight-grid">
        <div class="insight-card"><span>高热爱正样本</span><strong>${recs.basis.positive_books.length} 本</strong></div>
        <div class="insight-card"><span>进度待验证</span><strong>${recs.basis.progress_uncertain_books.length} 本</strong></div>
        <div class="insight-card"><span>候选召回</span><strong>${metrics.candidate_count} 本</strong></div>
        <div class="insight-card"><span>解释覆盖</span><strong>${formatScore(metrics.explain_coverage)}</strong></div>
      </div>
      <div class="tag-row">
        ${tagsHtml(positiveSignals)}
        ${tagsHtml(negativeSignals, "risk-tag")}
        ${tagsHtml(["网页进度不作为负反馈"], "risk-tag")}
      </div>
      <p class="muted">这一组 6 本来自你的真实番茄书架：系统按高热爱样本重排，用来找“已经在书架里但值得优先试读/复核”的书。网页端低进度可能未同步，只作为待验证信号，不直接降权。</p>
      <div class="pipeline-list">
        ${recs.pipeline.map((stage, index) => `
          <div class="pipeline-step">
            <b>${index + 1}. ${stage.name}</b>
            <span>${stage.detail}</span>
          </div>`).join("")}
      </div>
      <div class="metric-strip">
        <span>Top均分 ${formatScore(metrics.top_avg_score)}</span>
        <span>题材多样性 ${metrics.genre_diversity}</span>
        <span>反馈 ${metrics.feedback_total} 条</span>
      </div>
      <div class="book-mini-list">
        ${recs.items.slice(0, 6).map((book) => {
          const url = fanqieBookUrl(book);
          return `
          <div class="book-mini" data-candidate-type="bookshelf" data-book-id="${book.book_id}">
            <span>
              <span class="mini-title-row">
                <strong>${book.title}</strong>
                ${sourceLink(url)}
              </span>
              <small>${book.reason}</small>
              ${readingRecapHtml(book.reading_recap)}
              ${trialReportHtml(book.trial_report)}
              <small class="recall-source">${book.recall_sources.join(" / ")}</small>
              <span class="component-grid">
                ${Object.entries(book.components).slice(0, 4).map(([name, value]) => `<i>${name} ${formatScore(value)}</i>`).join("")}
              </span>
              <span class="fanqie-actions">
                <button data-fanqie-feedback="想看类似" data-book-id="${book.book_id}">想看类似</button>
                <button data-fanqie-feedback="不感兴趣" data-book-id="${book.book_id}">不感兴趣</button>
                <button data-fanqie-feedback="简介不符" data-book-id="${book.book_id}">简介不符</button>
                <button data-fanqie-feedback="节奏太慢" data-book-id="${book.book_id}">节奏慢</button>
                <button data-fanqie-feedback="主角降智" data-book-id="${book.book_id}">主角降智</button>
              </span>
            </span>
            <em>${Math.round(book.score * 100)}%</em>
          </div>`;
        }).join("")}
      </div>
      <p class="muted">高热爱样本：${loved.map((book) => `${book.title}（${book.progress_text || "高兴趣"}）`).join("、")}</p>
      ${uncertain.length ? `<p class="muted">进度待验证：${uncertain.map((book) => `${book.title}（${book.progress_text || "未同步"}）`).join("、")}</p>` : ""}
    `;
    $("#fanqieProfile").querySelectorAll("[data-fanqie-feedback]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        await api("/api/fanqie/feedback", {
          method: "POST",
          body: JSON.stringify({
            book_id: button.dataset.bookId,
            feedback_type: button.dataset.fanqieFeedback,
            reason: button.dataset.fanqieFeedback,
          }),
        });
        await loadFanqieProfile();
      });
    });
    $("#fanqieProfile").querySelectorAll(".book-mini[data-book-id]").forEach((card) => {
      card.addEventListener("click", (event) => {
        if (event.target.closest("a, button, summary")) return;
        const book = state.fanqieItems.find((item) => String(item.book_id) === String(card.dataset.bookId));
        if (book) selectCandidate(book, "bookshelf");
      });
    });
    if (!state.selectedCandidate && recs.items[0]) {
      await selectCandidate(recs.items[0], "bookshelf");
    }
  } catch (error) {
    $("#fanqieProfile").textContent = "暂未导入真实番茄画像。";
  }
}

async function loadPublicRecall() {
  try {
    const data = await api("/api/public-recall/recommendations?limit=8");
    state.publicItems = data.items;
    $("#publicRecallCount").textContent = `${data.counts.after_bookshelf_dedup} 个去重候选`;
    $("#publicRecallContent").classList.remove("empty-state");
    $("#publicRecallContent").innerHTML = `
      <p class="muted">这一组是书架外探索候选：不使用番茄后台数据，只从公开页面/公开推荐候选进入本地候选池，再用你的画像重排。${data.scope_note}</p>
      <div class="tag-row">${tagsHtml(data.keywords.slice(0, 8))}</div>
      <div class="metric-strip">
        <span>种子候选 ${data.counts.seed_candidates}</span>
        <span>缓存候选 ${data.counts.cached_candidates}</span>
        <span>书架去重后 ${data.counts.after_bookshelf_dedup}</span>
      </div>
      <div class="public-candidate-list">
        ${data.items.slice(0, 6).map((book) => `
          <article class="public-candidate" data-candidate-type="public" data-book-id="${book.book_id || book.title}">
            <div>
              <div class="mini-title-row">
                <h3>${book.title}</h3>
                ${sourceLink(book.source_url, book.source_type === "public_page" ? "打开番茄" : "来源页")}
              </div>
              <p class="muted">${book.author || "未知作者"} · ${book.category || "公开候选"} · ${book.word_count_text || "字数待抓取"}</p>
              <p>${book.reason}</p>
              <div class="tag-row">${tagsHtml(book.labels.slice(0, 5))}</div>
              ${trialReportHtml(book.trial_report)}
              <span class="component-grid">
                ${Object.entries(book.score_parts).slice(0, 5).map(([name, value]) => `<i>${name} ${formatScore(value)}</i>`).join("")}
              </span>
            </div>
            <div class="public-score">${formatScore(book.score)}</div>
          </article>`).join("")}
      </div>
    `;
    $("#publicRecallContent").querySelectorAll(".public-candidate[data-book-id]").forEach((card) => {
      card.addEventListener("click", (event) => {
        if (event.target.closest("a, summary")) return;
        const book = state.publicItems.find((item) => String(item.book_id || item.title) === String(card.dataset.bookId));
        if (book) selectCandidate(book, "public");
      });
    });
  } catch (error) {
    $("#publicRecallContent").textContent = "公开候选召回暂不可用。";
  }
}

async function selectCandidate(book, type) {
  state.selectedCandidate = book;
  state.selectedCandidateType = type;
  state.selectedBookId = null;
  renderCandidateDetail(book, type);
  renderCandidateAssistant(book, type);
  const memory = await loadChapterMemory(book);
  renderMemoryAssistant(memory);
}

function renderCandidateDetail(book, type) {
  const isPublic = type === "public";
  const title = book.title;
  const score = book.score ?? book.final_score ?? 0;
  const tags = isPublic ? (book.labels || []) : [...(book.inferred_genres || []), ...(book.inferred_tags || [])];
  const source = isPublic ? sourceLink(book.source_url, book.source_type === "public_page" ? "打开番茄" : "来源页") : sourceLink(fanqieBookUrl(book));
  $("#detailTitle").textContent = title;
  $("#bookDetail").classList.remove("empty-state");
  $("#bookDetail").innerHTML = `
    <h3 class="detail-title">${title}</h3>
    <p class="intro">${isPublic ? "书架外公开候选，用于发现新书和试读判断。" : "真实书架内候选，用于决定是否继续读、从哪里续读。"}</p>
    <div class="tag-row">${tagsHtml(tags.slice(0, 6))}</div>
    <div class="metric-strip">
      <span>综合分 ${formatScore(score)}</span>
      <span>${isPublic ? "书架外发现" : "书架内复核"}</span>
      ${book.risk || book.drop_risk ? `<span>试读风险 ${formatScore(book.risk || book.drop_risk)}</span>` : ""}
    </div>
    <p class="reason">${book.reason || ""}</p>
    ${source ? `<div class="detail-actions">${source}</div>` : ""}
    ${isPublic ? trialReportHtml(book.trial_report) : readingRecapHtml(book.reading_recap)}
  `;
}

function renderCandidateAssistant(book, type) {
  $("#assistantContent").classList.remove("empty-state");
  if (type === "bookshelf") {
    const recap = book.reading_recap;
    $("#assistantContent").innerHTML = `
      <div class="chapter-box">
        <h3>${recap?.headline || "续读恢复"}</h3>
        <p>${recap?.recap || "这本书来自你的真实书架，当前可先作为待验证候选。"}</p>
        <p><strong>继续阅读提示：</strong>${recap?.resume_hint || "先看前 3 章是否兑现设定和悬念。"}</p>
        <div class="pill-list">${tagsHtml(recap?.memory_points || [], "risk-tag")}</div>
        <p><strong>数据边界：</strong>${recap?.basis || "当前不伪造正文剧情。"}</p>
      </div>
    `;
    return;
  }
  const report = book.trial_report;
  $("#assistantContent").innerHTML = `
    <div class="chapter-box">
      <h3>${report?.headline || "无剧透选书报告"}</h3>
      <p>${report?.core_hook || book.intro || "公开候选暂未抓到更多简介。"}</p>
      <p><strong>验证重点：</strong>${report?.intro_promise || "先验证开篇是否兑现标题承诺。"}</p>
      <p><strong>前三章试读计划：</strong>${report?.try_plan || "看设定、冲突和主角行动力。"}</p>
      <div class="pill-list">${tagsHtml(book.keyword_hits || [])}</div>
      <p><strong>可能风险：</strong>${(report?.risk_points || []).join("；") || "暂无明显风险。"}</p>
    </div>
  `;
}

function renderProfile(profile, similarReaders) {
  $("#userSubtitle").textContent = `少踩烂书，快速接回断更书。最近偏好：${profile.preferred_style_tags.slice(0, 4).join(" / ")}`;
  $("#profileTitle").textContent = `${profile.user_id} 的短期阅读口味`;
  $("#genreMetric").textContent = profile.favorite_genres.slice(0, 2).join("、") || "--";
  $("#lovedMetric").textContent = `${profile.recent_loved_books.length} 本`;
  $("#readerMetric").textContent = similarReaders[0]
    ? `${similarReaders[0].user_id} ${Math.round(similarReaders[0].similarity * 100)}%`
    : "--";
  $("#profileTags").innerHTML = [
    ...profile.preferred_style_tags.map((tag) => `<span class="tag">${tag}</span>`),
    ...profile.avoid_tags.slice(0, 3).map((tag) => `<span class="risk-tag">${tag}</span>`),
  ].join("");
}

function renderRecommendations(items) {
  $("#resultCount").textContent = `${items.length} 个候选`;
  $("#recommendationList").innerHTML = items
    .map((item) => {
      const active = item.book_id === state.selectedBookId ? " active" : "";
      return `
        <article class="book-card${active}" data-book-id="${item.book_id}">
          <div class="cover theme-${item.cover_theme}">
            <span>${item.title}</span>
          </div>
          <div class="book-main">
            <div class="book-title-row">
              <h3>${item.title}</h3>
              <div class="score">${formatScore(item.final_score)}</div>
            </div>
            <div class="book-meta">${item.author} · ${item.category} · ${Math.round(item.word_count / 10000)}万字</div>
            <div class="tag-row">${tagsHtml(item.tags.slice(0, 3))}</div>
            <p class="reason">${item.reason}</p>
            <div class="risk-line">${item.risk_note} · 弃读风险 ${formatScore(item.drop_risk)}</div>
          </div>
        </article>`;
    })
    .join("");

  document.querySelectorAll(".book-card").forEach((card) => {
    card.addEventListener("click", async () => {
      state.selectedBookId = card.dataset.bookId;
      renderRecommendations(state.recommendations);
      await renderDetail(state.selectedBookId);
      await renderAssistant(state.selectedBookId);
    });
  });
}

function scoreBar(label, value, max = 10) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return `
    <div class="bar-row">
      <span>${label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <strong>${value.toFixed(1)}</strong>
    </div>`;
}

async function renderDetail(bookId) {
  const data = await api(`/api/books/${bookId}/analysis?user_id=${state.userId}`);
  $("#detailTitle").textContent = data.title;
  $("#bookDetail").classList.remove("empty-state");
  $("#bookDetail").innerHTML = `
    <h3 class="detail-title">${data.title}</h3>
    <p class="intro">${data.intro}</p>
    <div class="tag-row">
      ${tagsHtml(data.positive_tags.slice(0, 5))}
      ${tagsHtml(data.negative_tags.slice(0, 3), "risk-tag")}
    </div>
    <div class="score-bars">
      ${scoreBar("简介一致", data.intro_consistency_score)}
      ${scoreBar("前三章钩子", data.hook_score)}
      ${scoreBar("质量评分", data.quality_score)}
      ${scoreBar("弃读风险", data.drop_risk, 1)}
    </div>
    <div class="analysis-list">
      <div><strong>正文证据：</strong>${data.text_evidence.join("；")}</div>
      <div><strong>潜在风险：</strong>${data.mismatch_points.join("；")}</div>
      <div><strong>评论信号：</strong>${data.comments_signal}</div>
      <div><strong>系统判断：</strong>${data.analysis_summary}</div>
    </div>
    <div class="feedback-row">
      ${["喜欢", "不感兴趣", "节奏太慢", "简介不符", "加入书架"].map((text) => `<button data-feedback="${text}">${text}</button>`).join("")}
    </div>
  `;

  $("#bookDetail").querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          user_id: state.userId,
          book_id: bookId,
          feedback_type: button.dataset.feedback,
          reason: button.dataset.feedback,
        }),
      });
      await loadRecommendations();
    });
  });
}

async function renderAssistant(bookId) {
  const chapters = await api(`/api/books/${bookId}/chapters`);
  if (!chapters.items.length) {
    $("#assistantContent").classList.add("empty-state");
    $("#assistantContent").innerHTML = "这本书暂未录入章节样例，可在数据集中补充章节后展示摘要、人物关系和伏笔提醒。";
    return;
  }
  const chapter = await api(`/api/books/${bookId}/chapters/${chapters.items[0].id}`);
  $("#assistantContent").classList.remove("empty-state");
  $("#assistantContent").innerHTML = `
    <div class="chapter-box">
      <h3>${chapter.title}</h3>
      <p>${chapter.content}</p>
      <p><strong>章节摘要：</strong>${chapter.summary}</p>
      <div class="pill-list">${tagsHtml(chapter.key_events || [])}</div>
      <p><strong>人物：</strong>${(chapter.characters || []).join("、") || "--"}</p>
      <p><strong>伏笔：</strong>${(chapter.foreshadowing || []).join("；") || "--"}</p>
    </div>
  `;
}

async function renderRecap() {
  if (state.selectedCandidate) {
    const memory = await loadChapterMemory(state.selectedCandidate);
    if (!renderMemoryAssistant(memory)) {
      renderCandidateAssistant(state.selectedCandidate, state.selectedCandidateType);
    }
    return;
  }
  if (!state.selectedBookId) return;
  const data = await api(`/api/books/${state.selectedBookId}/recap?user_id=${state.userId}`);
  $("#assistantContent").classList.remove("empty-state");
  $("#assistantContent").innerHTML = `
    <div class="chapter-box">
      <h3>续读恢复</h3>
      <p>${data.recap}</p>
      <p><strong>继续阅读提示：</strong>${data.next_reading_hint}</p>
      <div class="pill-list">${tagsHtml(data.open_threads || [], "risk-tag")}</div>
      <p><strong>关键人物：</strong>${data.important_characters.map((item) => item.name).join("、") || "--"}</p>
    </div>
  `;
}

async function analyzeCurrentChapter() {
  const book = state.selectedCandidate;
  if (!book) {
    $("#memoryContent").classList.add("empty-state");
    $("#memoryContent").textContent = "请先点击一本书架内或书架外候选。";
    return;
  }
  const text = $("#chapterTextInput").value.trim();
  if (text.length < 80) {
    $("#memoryContent").classList.add("empty-state");
    $("#memoryContent").textContent = "正文太短，至少粘贴一段有完整情节的信息。";
    return;
  }
  const identity = candidateIdentity(book);
  $("#analyzeChapterBtn").disabled = true;
  $("#analyzeChapterBtn").textContent = "分析中...";
  try {
    const result = await api("/api/chapter-memory/analyze", {
      method: "POST",
      body: JSON.stringify({
        book_id: identity.book_id,
        title: identity.title,
        chapter_index: Number($("#chapterIndexInput").value || 1),
        chapter_title: $("#chapterTitleInput").value.trim() || `第 ${$("#chapterIndexInput").value || 1} 章`,
        chapter_text: text,
      }),
    });
    $("#chapterTextInput").value = "";
    renderMemory(result.memory);
    renderMemoryAssistant(result.memory);
  } finally {
    $("#analyzeChapterBtn").disabled = false;
    $("#analyzeChapterBtn").textContent = "生成章节记忆";
  }
}

async function init() {
  try {
    setActiveView(storedView());
    hideTxtResult("#txtLlmReport");
    document.querySelectorAll(".view-tabs [data-view]").forEach((button) => {
      button.addEventListener("click", () => setActiveView(button.dataset.view));
    });

    await loadUsers();
    await loadFanqieProfile();
    await loadPublicRecall();
    await loadTxtStories();
    await loadLlmStatus();
    await loadRecommendations();
    $("#userSelect").addEventListener("change", async (event) => {
      state.userId = event.target.value;
      await loadRecommendations();
    });
    $("#refreshBtn").addEventListener("click", async () => {
      state.selectedCandidate = null;
      state.selectedCandidateType = null;
      await loadFanqieProfile();
      await loadPublicRecall();
      await loadRecommendations();
    });
    $("#recapBtn").addEventListener("click", renderRecap);
    $("#analyzeChapterBtn").addEventListener("click", analyzeCurrentChapter);
    $("#txtAnalyzeBtn").addEventListener("click", () => loadTxtAnalysis());
    $("#txtLlmBtn").addEventListener("click", loadTxtLlmAnalysis);
    $("#txtProgressBtn").addEventListener("click", loadProgressRecap);
    $("#txtStorySelect").addEventListener("change", async (event) => {
      syncTxtUptoLimit(event.target.value);
      hideTxtResult("#txtLlmReport");
      showTxtResult("#txtProgressRecap");
      $("#txtProgressRecap").classList.add("empty-state");
      $("#txtProgressRecap").textContent = "输入“读到第几章”后，可以生成 1-N 章续读恢复，不会把几百章原文一次性塞给模型。";
      await loadTxtAnalysis(event.target.value);
    });
  } catch (error) {
    document.body.innerHTML = `<pre>${error.stack || error.message}</pre>`;
  }
}

init();
