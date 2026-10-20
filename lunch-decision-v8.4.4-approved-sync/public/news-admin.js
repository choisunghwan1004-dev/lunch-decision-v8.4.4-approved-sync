/**
 * 뉴스 관리자 화면: 주제·출처·Fact·초안 목록과 입력/검토 대화상자를 제어합니다.
 * 화면은 입력을 모으고 Python API가 최종 조건을 검사합니다. 버튼 비활성화만을 권한 검사로 믿지 않습니다.
 * 등록·수정 저장 후에는 대화상자를 닫고 목록을 새로 읽어 상태를 확인할 수 있게 합니다.
 */
/* News is namespaced so existing lunch/travel/admin behavior remains intact. */
(() => {
  "use strict";
  const el = (id) => document.getElementById(id),
    root = el("news");
  if (!root) return;
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const labels = {
    generated: "미검토 초안",
    in_review: "검토 중",
    changes_requested: "수정 요청",
    rejected: "반려",
    approved: "최종 승인",
    published: "게시 중",
    candidate: "검증 대기",
    verified: "검증 완료",
    disputed: "이견 있음",
    outdated: "만료",
    supported: "근거 대조 완료",
    unverified: "미검토",
    contradicted: "근거 불일치",
  };
  const pill = (value) =>
    `<span class="news-pill">${escape(labels[value] || value)}</span>`;
  const safeURL = (value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? escape(url.href) : "#";
    } catch {
      return "#";
    }
  };
  let topics = [],
    regions = [],
    sources = [],
    facts = [],
    drafts = [],
    active = 0,
    dialog = null,
    opening = null,
    ready = false,
    loading = false,
    workspaceVersion = 0;
  const status = (message, error = false) => {
    el("newsStatus").textContent = message;
    el("newsStatus").dataset.error = String(error);
  };
  // 목록이 비어 있는 이유를 구분합니다. 연결 오류를 정상적인 빈 목록으로 보이면 안 됩니다.
  function controls() {
    root.querySelector('[data-news-action="new-topic"]').disabled = !ready || !regions.length;
    root.querySelector('[data-news-action="retry"]').disabled = loading;
    el("newsTopic").disabled = !ready || !topics.length;
    el("newsTopicHint").textContent = !ready
      ? "뉴스 연결이 준비되면 시군구와 주제를 선택할 수 있습니다."
      : !regions.length
        ? "등록된 시군구가 없습니다. 지역 관리에서 지역을 등록한 뒤 연결을 다시 확인하세요."
        : !topics.length
          ? "등록된 주제가 없습니다. 새 주제에서 시군구와 제목을 입력해 먼저 저장하세요."
          : `${regions.length}개 시군구 · ${topics.length}개 주제에서 선택할 수 있습니다.`;
  }
  function unavailable(error) {
    ready = false;
    regions = []; topics = []; sources = []; facts = []; drafts = [];
    ++workspaceVersion; // 이전 주제의 느린 응답이 오류 안내를 덮어쓰지 못하게 합니다.
    el("newsTopic").innerHTML = '<option value="">뉴스 연결을 먼저 복구하세요</option>';
    el("newsWorkspace").textContent = "연결을 복구한 뒤 주제 등록·선택을 계속할 수 있습니다.";
    el("newsRecovery").hidden = false;
    status(error.message, true);
    controls();
  }
  function topicSelector() {
    if (!topics.some((t) => Number(t.id) === active)) active = 0;
    el("newsTopic").innerHTML =
      `<option value="">${topics.length ? "주제를 선택하세요" : "새 주제를 먼저 등록하세요"}</option>` +
      topics.map((t) => `<option value="${t.id}">${escape(t.region_name)} · ${escape(t.title)}${t.is_demo ? " [시연]" : ""}</option>`).join("");
    el("newsTopic").value = active || "";
    controls();
  }
  // 동일 출처의 Node 프록시를 호출합니다. 세션 쿠키와 쓰기 확인 헤더를 보내지만 비밀 키는 보내지 않습니다.
  async function api(path, method = "GET", data) {
    const response = await fetch("/api/news" + path, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(path.endsWith("/generate") || path === "/ai/check" ? 60000 : 15000),
      headers: { "Content-Type": "application/json", "X-News-Request": "1" },
      ...(method !== "GET" ? { body: JSON.stringify(data || {}) } : {}),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(result.detail)
        ? result.detail.map((x) => x.msg).join("\n")
        : result.detail || result.message;
      const error = Error(detail || "뉴스 요청에 실패했습니다.");
      error.code = result.code;
      error.status = response.status;
      throw error;
    }
    return result;
  }
  // 입력/검토 팝업을 만들고 저장 중 중복 클릭·실패 안내·저장 후 목록 갱신을 공통 처리합니다.
  function modal(title, body, onSubmit) {
    if (dialog) {
      dialog.close();
      dialog.remove();
    }
    dialog = document.createElement("dialog");
    dialog.className = "news-dialog";
    dialog.innerHTML = `<div class="news-dialog-head"><h2>${escape(title)}</h2><button type="button" data-close aria-label="닫기">닫기</button></div><form>${body}<p class="news-error" role="alert"></p></form>`;
    document.body.append(dialog);
    dialog.querySelector("[data-close]").onclick = () => dialog.close();
    dialog.addEventListener("close", (event) => event.currentTarget.remove(), {
      once: true,
    });
    if (onSubmit)
      dialog.querySelector("form").onsubmit = async (event) => {
        event.preventDefault();
        const form = event.currentTarget,
          button = event.submitter;
        if (button) button.disabled = true;
        try {
          await onSubmit(new FormData(form), form);
          dialog.close();
          status("저장했습니다. 뉴스 목록에서 계속 작업할 수 있습니다.");
          await refresh();
        } catch (error) {
          if (form.isConnected) form.querySelector(".news-error").textContent = error.message;
          else unavailable(error);
        } finally {
          if (button) button.disabled = false;
        }
      };
    else
      dialog.querySelector("form").onsubmit = (event) => event.preventDefault();
    dialog.showModal();
    return dialog;
  }
  function input(name, label, value = "", type = "text", extra = "") {
    return `<label>${label}<input name="${name}" type="${type}" value="${escape(value)}" ${extra}></label>`;
  }
  function text(name, label, value = "", extra = "") {
    return `<label>${label}<textarea name="${name}" ${extra}>${escape(value)}</textarea></label>`;
  }
  const submit = (label) =>
    `<button class="news-submit" type="submit">${label}</button>`;
  // 연결 검사는 주제·DB 기사와 독립적입니다. 키 원문은 브라우저에서 받거나 표시하지 않습니다.
  async function openAICheck() {
    const state = await api("/ai/status");
    const box = modal(
      "OpenAI 연결 확인",
      `<p>모델: ${escape(state.model)} · 키 ${state.key_configured ? "설정됨" : "미설정"} · 모델 설정 ${state.model_configured ? "정상" : "확인 필요"}</p><p>키는 PC의 <b>13_OpenAI_키설정.bat</b>으로 입력하고 FastAPI를 다시 시작하세요.</p><p>아래 버튼은 수업용 가상 Fact 1건을 OpenAI에 한 번 전송합니다. API 비용이 발생합니다. 기사 저장·게시는 하지 않습니다.</p><button type="button" data-live-check ${state.key_configured && state.model_configured ? "" : "disabled"}>실제 API 한 번 호출 (유료)</button><pre data-live-result role="status" aria-live="polite">아직 실제 호출하지 않았습니다.</pre>`,
      null,
    );
    const button = box.querySelector("[data-live-check]"),
      result = box.querySelector("[data-live-result]");
    button.onclick = async () => {
      button.disabled = true;
      result.textContent = "OpenAI 응답을 기다립니다. 자동 재시도하지 않습니다.";
      try {
        const checked = await api("/ai/check", "POST", { confirmation: "CALL_OPENAI" });
        result.textContent = `${checked.message}\n모델: ${checked.model}\n응답 ID: ${checked.usage.request_id}\n입력/출력 토큰: ${checked.usage.input_tokens}/${checked.usage.output_tokens}\n소요: ${checked.elapsed_seconds}초\n\n${checked.article.title}\n${checked.article.body}`;
      } catch (error) {
        result.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    };
  }
  // 주제 목록을 다시 읽고 현재 선택 주제를 유지합니다.
  async function refresh() {
    topics = await api("/topics");
    if (!Array.isArray(topics)) throw Error("뉴스 주제 목록 형식이 올바르지 않습니다. 연결을 다시 확인하세요.");
    topicSelector();
    if (active) await workspace();
    else
      el("newsWorkspace").innerHTML =
        "<p>주제를 만들고 공식 출처와 Fact를 등록하세요. 검증되지 않은 자료는 AI에 전달하지 않습니다.</p>";
  }
  // 선택 주제의 출처·Fact·초안 목록을 독립 요청으로 읽어 단계별로 표시합니다.
  async function workspace() {
    const selected = active, version = ++workspaceVersion;
    const topic = topics.find((t) => Number(t.id) === selected);
    if (!topic) return;
    el("newsWorkspace").textContent = "선택한 주제의 출처·Fact·초안을 불러오고 있습니다.";
    let lists;
    try {
      lists = await Promise.all([
        api(`/topics/${selected}/sources`),
        api(`/topics/${selected}/facts`),
        api(`/topics/${selected}/drafts`),
      ]);
    } catch (error) {
      if (selected === active && version === workspaceVersion) throw error;
      return;
    }
    // 빠르게 주제를 바꿔도 나중에 도착한 이전 주제 응답이 현재 화면에 섞이지 않습니다.
    if (selected !== active || version !== workspaceVersion || !ready) return;
    [sources, facts, drafts] = lists;
    // Fact 저장·검증과 기사 승인·게시는 서로 다른 저장 단계입니다. 현재 DB 상태와 다음 동작을 명시합니다.
    const verified = facts.filter(f => f.status === "verified").length;
    const approved = drafts.filter(d => d.status === "approved").length;
    const published = drafts.filter(d => d.status === "published").length;
    const nextStep = topic.is_demo ? "시연용 주제는 운영 화면에 게시할 수 없습니다."
      : published ? "게시가 저장되었습니다. 사용자 화면에서 같은 지역 또는 전체 지역을 선택해 확인하세요."
      : approved ? "최종 승인이 저장되었습니다. 기사 검토·수정을 열고 승인본 게시를 눌러야 메인에 표시됩니다."
      : drafts.length ? "초안이 저장되었습니다. 문장별 근거 대조 → 최종 승인 → 승인본 게시를 진행하세요."
      : verified ? "Fact 검증이 저장되었습니다. 검증 Fact로 초안 생성 → 기사 검토 → 승인 → 게시를 진행하세요."
      : "출처와 Fact를 저장한 뒤 원문 대조로 Fact를 검증하세요.";
    el("newsWorkspace").innerHTML =
      `<p><b>${escape(topic.title)}</b> · ${escape(topic.region_name)} · 예약 주제 번호 <b>#${topic.id}</b> ${topic.is_demo ? '<span class="news-pill">시연용 · 운영 게시 금지</span>' : ""}</p>
 <section class="news-block" aria-label="메인 노출 상태"><h3>메인 노출 상태</h3><p>출처 ${sources.length}건 · Fact ${facts.length}건 / 검증 ${verified}건 · 기사 ${drafts.length}건 / 승인 ${approved}건 / 게시 ${published}건</p><p>${escape(nextStep)}</p><a href="/?news_scope=all#regionalNews" target="_blank" rel="noopener noreferrer">사용자 화면의 전체 지역 소식 확인 ↗</a></section>
 <section class="news-block"><div class="news-toolbar"><h3>1. 출처와 원자료</h3><button type="button" data-news-action="import">CSV·JSON 가져오기</button><button type="button" data-news-action="source">출처 등록</button></div>${sources.length ? sources.map((s) => `<article class="news-row"><div><b>${escape(s.source_title)}</b><p>${escape(s.organization)} · <a href="${safeURL(s.source_url)}" target="_blank" rel="noopener noreferrer">원문 열기 ↗</a></p><small>공개 시점 ${escape(String(s.published_at || "미입력").replace("T", " "))}</small></div><div class="news-row-actions"><button type="button" data-news-action="source" data-id="${s.id}">수정</button><button type="button" data-news-action="delete-source" data-id="${s.id}">삭제</button></div></article>`).join("") : "<p>등록된 출처가 없습니다.</p>"}</section>
 <section class="news-block"><div class="news-toolbar"><h3>2. Fact Sheet · 사람의 원문 검증</h3><button type="button" data-news-action="fact">Fact 등록</button></div>${facts.length ? facts.map((f) => `<article class="news-row"><div><b>${escape(f.fact_key)}</b> ${pill(f.status)}<p>${escape(f.value_text)}</p><small>출처 ${f.evidence.length}개 · ${escape(f.verification_note || "검증 의견 없음")}</small></div><div class="news-row-actions"><button type="button" data-news-action="fact" data-id="${f.id}">수정</button><button type="button" data-news-action="evidence" data-id="${f.id}">근거 연결</button><button type="button" data-news-action="verify" data-id="${f.id}">원문 대조</button><button type="button" data-news-action="fact-status" data-id="${f.id}">상태 변경</button><button type="button" data-news-action="delete-fact" data-id="${f.id}">삭제</button></div></article>`).join("") : "<p>확인할 사실을 항목별로 등록하세요.</p>"}</section>
 <section class="news-block"><div class="news-toolbar"><div><h3>3. 초안 · 최종 검토 · 게시</h3><small>gpt-6-luna · 생성 시 OpenAI API 비용 발생 · 사실 검증은 별도</small></div><button type="button" data-news-action="generate" ${facts.some((f) => f.status === "verified") ? "" : "disabled"}>검증 Fact로 초안 생성</button></div>${drafts.map((d) => `<article class="news-row"><div><b>${escape(d.title)}</b><p>수정본 ${d.revision_no} · ${pill(d.status)}</p><small>${escape(d.created_by)} · ${escape(String(d.created_at).replace("T", " "))}</small></div><button type="button" data-news-action="draft" data-id="${d.id}">기사 검토·수정</button></article>`).join("") || "<p>저장된 초안이 없습니다.</p>"}</section>`;
  }
  // DB의 실제 시군구를 선택해 새 주제를 등록합니다.
  // 파일을 브라우저에서 읽어 서버의 CSV/JSON 파서로 보냅니다. 검증·승인은 자동 처리하지 않습니다.
  function importForm() {
    modal('CSV·JSON 원자료 가져오기', `<p>예제 파일은 examples 폴더에 있습니다. 시연 자료는 시연용 주제에만 가져올 수 있습니다.</p><label>UTF-8 CSV 또는 JSON 파일<input type="file" name="import_file" accept=".csv,.json" required></label><p>최대 40행·180KB입니다. 같은 Fact Key나 충돌 출처가 있으면 전체 취소합니다. 가져온 Fact는 검증 대기입니다.</p>${submit('파일 가져오기')}`, async (data, form) => {
      const file=form.querySelector('[name=import_file]').files[0];
      if(!file || file.size>180000) throw Error('180KB 이하 파일을 선택하세요.');
      const format=file.name.toLowerCase().endsWith('.csv')?'csv':file.name.toLowerCase().endsWith('.json')?'json':null;
      if(!format) throw Error('CSV 또는 JSON 파일을 선택하세요.');
      const result=await api(`/topics/${active}/import`, 'POST', {format,content:await file.text()});
      status(`${result.facts_created}개 Fact를 가져왔습니다. 원문 대조 후 검증하세요.`);
    });
  }
  function newTopic() {
    if (!ready || !regions.length) {
      status("뉴스 연결과 시군구 목록을 먼저 확인하세요.", true);
      return;
    }
    modal(
      "뉴스 주제 등록",
      `<label>지역<select name="district_id" required><option value="">시군구 선택</option>${regions.map((r) => `<option value="${r.id}">${escape(r.label)}</option>`).join("")}</select></label>${input("title", "주제", "", "text", 'required maxlength="200"')}<label>분류<select name="category"><option value="tourism">관광</option><option value="festival">축제·행사</option><option value="transport">교통</option><option value="culture">문화</option><option value="other">기타</option></select></label><label class="news-check"><input name="is_demo" type="checkbox">시연용 가상 자료 (운영 게시 불가)</label>${submit("주제 저장")}`,
      async (data) => {
        const saved = await api("/topics", "POST", {
          district_id: Number(data.get("district_id")),
          title: data.get("title"),
          category: data.get("category"),
          is_demo: data.has("is_demo"),
        });
        active = saved.id;
      },
    );
  }
  // 원문 URL·공개 시점·관련 구절·이용 조건을 받습니다. 수정 후 근거 재검증이 필요합니다.
  function sourceForm(id) {
    const s = sources.find((x) => Number(x.id) === id) || {};
    modal(
      id ? "출처 수정" : "출처 등록",
      `<p>원문을 직접 열어 필요한 구절과 이용 조건을 기록하세요. 서버가 URL을 자동 수집하지 않습니다.</p><label>자료 종류<select name="source_kind">${[
        ["official", "공식 기관"],
        ["public_api", "공공 API"],
        ["csv", "CSV"],
        ["manual", "직접 등록"],
        ["other", "기타"],
      ]
        .map(
          ([k, v]) =>
            `<option value="${k}" ${s.source_kind === k ? "selected" : ""}>${v}</option>`,
        )
        .join(
          "",
        )}</select></label>${input("organization", "발행 기관", s.organization, "text", 'required maxlength="200"')}${input("source_title", "자료 제목", s.source_title, "text", 'required maxlength="300"')}${input("source_url", "공식 원문 URL (HTTPS)", s.source_url, "url", 'required maxlength="1024"')}${input("published_at", "자료 공개 시점 (UTC)", String(s.published_at || "").slice(0, 16), "datetime-local", "required")}${text("source_excerpt", "원자료의 관련 구절", s.source_excerpt, 'required minlength="10" maxlength="16000"')}${text("license_note", "이용 조건·인용 범위", s.license_note, 'required maxlength="500"')}${id ? '<p class="news-warning">수정하면 연결된 Fact를 다시 검증해야 하며, 이 주제의 승인이 해제되고 게시가 중단됩니다.</p>' : ""}${submit("출처 저장")}`,
      async (data) => {
        const body = Object.fromEntries(data);
        body.published_at += ":00Z";
        await api(
          `/topics/${active}/sources${id ? "/" + id : ""}`,
          id ? "PUT" : "POST",
          body,
        );
      },
    );
  }
  // Fact 내용·유형·수치·기간을 입력받습니다. 수치 칸이 비었으면 null로 전송합니다.
  function factForm(id) {
    const f = facts.find((x) => Number(x.id) === id) || {};
    modal(
      id ? "Fact 수정" : "Fact 등록",
      `${input("fact_key", "Fact Key (예: EVENT_DATE)", f.fact_key, "text", 'required pattern="[A-Za-z0-9_-]{2,80}"')}<label>유형<select name="fact_type">${[
        ["text", "내용"],
        ["date", "날짜"],
        ["date_range", "기간"],
        ["number", "수치"],
        ["price", "가격"],
        ["place", "장소"],
        ["time", "시간"],
      ]
        .map(
          ([k, v]) =>
            `<option value="${k}" ${f.fact_type === k ? "selected" : ""}>${v}</option>`,
        )
        .join(
          "",
        )}</select></label>${text("value_text", "확인할 사실", f.value_text, 'required maxlength="4000"')}${input("value_number", "수치 값 (수치·가격 유형 필수)", f.value_number, "number", 'step="0.0001"')}${input("unit", "단위", f.unit, "text", 'maxlength="30"')}${input("event_start", "시작일", String(f.event_start || "").slice(0, 10), "date")}${input("event_end", "종료일", String(f.event_end || "").slice(0, 10), "date")}${id ? '<p class="news-warning">수정 후 Fact 검증과 기사 승인을 다시 진행해야 합니다. 게시 중인 기사는 즉시 중단됩니다.</p>' : ""}${submit("Fact 저장")}`,
      async (data) => {
        const body = Object.fromEntries(data);
        for (const key of ["value_number", "unit", "event_start", "event_end"])
          if (!body[key]) body[key] = null;
        await api(
          `/topics/${active}/facts${id ? "/" + id : ""}`,
          id ? "PUT" : "POST",
          body,
        );
      },
    );
  }
  // Fact에 같은 주제의 출처와 원문 위치를 연결하거나 해제합니다.
  function evidenceForm(id) {
    const f = facts.find((x) => Number(x.id) === id);
    modal(
      "Fact에 원자료 연결",
      `<p><b>${escape(f.fact_key)}</b> · ${escape(f.value_text)}</p><label>출처<select name="source_id" required>${sources.map((s) => `<option value="${s.id}">${escape(s.source_title)}</option>`).join("")}</select></label>${input("excerpt_reference", "원문 위치 (쪽·절·문단)", "", "text", 'required maxlength="500"')}${text("evidence_note", "이 Fact를 뒷받침하는 구절·대조 내용", "", 'required maxlength="4000"')}<p class="news-warning">근거를 바꾸면 기사 승인이 해제되고 게시가 중단됩니다.</p>${submit("연결 저장")}<h3>현재 연결</h3>${f.evidence.map((e) => `<p>${escape(e.source_title)} · ${escape(e.excerpt_reference)} <button type="button" data-remove-evidence="${e.source_id}">연결 해제</button></p>`).join("")}`,
      async (data) => {
        await api(`/topics/${active}/facts/${id}/evidence`, "POST", {
          ...Object.fromEntries(data),
          source_id: Number(data.get("source_id")),
        });
      },
    );
    dialog.querySelectorAll("[data-remove-evidence]").forEach(
      (button) =>
        (button.onclick = async () => {
          try {
            await api(
              `/topics/${active}/facts/${id}/evidence/${button.dataset.removeEvidence}`,
              "DELETE",
            );
            dialog.close();
            await refresh();
          } catch (e) {
            dialog.querySelector(".news-error").textContent = e.message;
          }
        }),
    );
  }
  // 현재 또는 과거 스냅샷의 근거를 같은 형태로 보여줍니다. 문자열은 HTML 이스케이프합니다.
  function evidenceHTML(f) {
    return `<div class="news-evidence"><b>${escape(f.fact_key)}</b><p>${escape(f.value_text)}</p>${f.evidence.map((e) => `<p><a href="${safeURL(e.source_url)}" target="_blank" rel="noopener noreferrer">${escape(e.source_title)} ↗</a> · ${escape(e.organization)}</p><small>${escape(String(e.published_at || ""))} · ${escape(e.license_note)}</small><blockquote>${escape(e.source_excerpt)}</blockquote><p>${escape(e.excerpt_reference)} · ${escape(e.evidence_note)}</p>`).join("") || "<p>출처 연결이 없습니다.</p>"}</div>`;
  }
  // 사람이 원문을 직접 대조했는지 체크하고 검증 의견을 API로 보냅니다.
  function verifyForm(id) {
    const f = facts.find((x) => Number(x.id) === id);
    modal(
      "Fact 원문 대조 · 사람의 검증",
      `${evidenceHTML(f)}<label class="news-check"><input type="checkbox" name="editor_confirmed" required>원문을 직접 열어 수치·날짜·지역·표현을 대조했습니다.</label>${text("verification_note", "검증 의견", "", 'required minlength="3" maxlength="4000"')}${submit("Fact 검증 완료")}`,
      async (data) => {
        await api(`/topics/${active}/facts/${id}/verify`, "POST", {
          editor_confirmed: data.has("editor_confirmed"),
          verification_note: data.get("verification_note"),
        });
      },
    );
  }
  function factStatus(id) {
    modal(
      "Fact 상태 변경",
      `<label>상태<select name="status"><option value="candidate">검증 대기</option><option value="disputed">이견 있음</option><option value="outdated">만료</option><option value="rejected">반려</option></select></label>${text("reason", "변경 이유", "", 'required minlength="3"')}<p class="news-warning">이 주제의 승인을 해제하고 게시를 중단합니다.</p>${submit("상태 저장")}`,
      async (data) => {
        await api(
          `/topics/${active}/facts/${id}/status`,
          "POST",
          Object.fromEntries(data),
        );
      },
    );
  }
  // 기사 문장과 현재/과거 근거를 나란히 표시하고 검토·승인·게시 동작을 연결합니다.
  async function openDraft(id) {
    const d = await api("/drafts/" + id),
      editable = ["generated", "in_review", "changes_requested"].includes(
        d.status,
      );
    modal(
      `수정본 ${d.revision_no} · ${labels[d.status] || d.status}`,
      `${d.status === "approved" ? '<p class="news-warning">최종 승인은 저장되었습니다. 아래 승인본 게시를 눌러야 사용자 메인에 공개됩니다.</p>' : ""}${!d.evidence_current ? '<p class="news-warning">현재 Fact Sheet와 다른 초안입니다. 새 수정본을 저장한 뒤 재검토하세요.</p>' : ""}<div class="news-review-grid"><div><h3>${escape(d.title)}</h3>${d.claims.map((c) => `<div class="news-sentence" data-claim="${c.id}"><b>${c.sequence_no === 0 ? "제목" : "문장 " + c.sequence_no}</b> ${pill(c.status)}<p>${escape(c.statement_text)}</p><small>근거 ${escape(c.fact_keys.join(", "))}</small>${editable && d.evidence_current ? `<label class="news-check"><input type="checkbox" data-source-checked>연결된 원자료를 직접 대조했습니다.</label><textarea data-claim-note aria-label="문장 검토 의견" placeholder="검토 의견 (3자 이상)">${escape(c.check_note || "")}</textarea><div class="news-review-actions"><button type="button" data-check="supported" data-id="${c.id}">근거 일치</button><button type="button" data-check="contradicted" data-id="${c.id}">불일치</button></div>` : ""}</div>`).join("")}</div><aside><h3>현재 검증된 Fact와 원자료</h3>${d.facts.map(evidenceHTML).join("") || "<p>현재 검증된 Fact가 없습니다.</p>"}<details><summary>이 수정본 저장 당시의 근거</summary>${d.saved_fact_sheet ? d.saved_fact_sheet.facts.map(evidenceHTML).join("") : "<p>구형 초안에는 근거 원문 스냅샷이 없습니다. 새 수정본을 저장하세요.</p>"}</details></aside></div><div class="news-review-actions"><button type="button" data-edit>새 수정본 작성</button></div><h3>최종 검토</h3><p>승인 후 게시 버튼을 눌러 사용자 화면에 공개합니다.</p>${[
        ["numbers", "수치·금액·단위"],
        ["time_and_region", "시점·날짜·지역"],
        ["no_unfounded_causes", "인과·과장·근거 없는 해석"],
        ["sources_and_rights", "출처 표시·이용 조건"],
      ]
        .map(
          ([k, label]) =>
            `<label class="news-check"><input type="checkbox" name="${k}">${label} 확인</label>`,
        )
        .join(
          "",
        )}${text("review_reason", "검토·수정 요청·게시 중단 의견", "", 'minlength="3" maxlength="2000"')}<div class="news-review-actions"><button type="button" data-review="submitted">검토 요청</button><button type="button" data-review="changes_requested">수정 요청</button><button type="button" data-review="rejected">반려</button><button type="button" data-review="approved" ${d.status === "in_review" ? "" : "disabled"}>최종 승인</button><button type="button" data-publish ${d.status === "approved" ? "" : "disabled"}>승인본 게시</button><button type="button" data-unpublish ${d.status === "published" ? "" : "disabled"}>게시 중단</button></div><details><summary>검토 이력 (${d.reviews.length})</summary>${d.reviews.map((r) => `<p><b>${escape(labels[r.action] || r.action)}</b> · ${escape(r.reviewer_key)} · ${escape(String(r.created_at))}<br>${escape(r.reason)}</p>`).join("") || "<p>검토 이력이 없습니다.</p>"}</details>`,
    );
    const current = dialog;
    async function action(fn, close = false) {
      const buttons = current.querySelectorAll("button");
      buttons.forEach((b) => (b.disabled = true));
      try {
        await fn();
        if (close) {
          current.close();
          await refresh();
          status("처리했습니다. 뉴스 목록에서 상태를 확인하세요.");
        } else await openDraft(id);
      } catch (error) {
        current.querySelector(".news-error").textContent = error.message;
        buttons.forEach((b) => (b.disabled = false));
      }
    }
    current.querySelector("[data-edit]").onclick = () => editDraft(d);
    current.querySelectorAll("[data-check]").forEach(
      (button) =>
        (button.onclick = () =>
          action(async () => {
            const row = button.closest("[data-claim]");
            if (!row.querySelector("[data-source-checked]").checked)
              throw Error("원자료 대조 체크가 필요합니다.");
            await api(
              `/drafts/${id}/claims/${button.dataset.id}/review`,
              "POST",
              {
                status: button.dataset.check,
                source_checked: true,
                note: row.querySelector("[data-claim-note]").value,
                expected_content_hash: d.content_hash,
              },
            );
          })),
    );
    current.querySelectorAll("[data-review]").forEach(
      (button) =>
        (button.onclick = () =>
          action(async () => {
            const form = new FormData(current.querySelector("form")),
              body = {
                action: button.dataset.review,
                reason: form.get("review_reason"),
                expected_content_hash: d.content_hash,
              };
            if (body.action === "approved")
              body.checks = Object.fromEntries(
                [
                  "numbers",
                  "time_and_region",
                  "no_unfounded_causes",
                  "sources_and_rights",
                ].map((k) => [k, form.has(k)]),
              );
            await api(`/drafts/${id}/review`, "POST", body);
          }, button.dataset.review !== "approved")),
    );
    current.querySelector("[data-publish]").onclick = () =>
      action(
        async () => {
          await api(`/drafts/${id}/publish`, "POST", {
            confirmation: "PUBLISH",
            expected_content_hash: d.content_hash,
          });
          notifyPublic();
        },
        true,
      );
    current.querySelector("[data-unpublish]").onclick = () =>
      action(
        async () => {
          await api(`/drafts/${id}/unpublish`, "POST", {
            reason: current.querySelector("[name=review_reason]").value,
          });
          notifyPublic();
        },
        true,
      );
  }
  function notifyPublic() {
    try { localStorage.setItem("regional-news-changed", String(Date.now()) + Math.random()); }
    catch { /* 저장소 사용이 막혀도 게시 저장은 성공했습니다. 메인의 새로고침으로 재조회할 수 있습니다. */ }
  }
  // 기존 초안을 덮어쓰지 않고 새 수정본을 저장합니다. Fact Key 목록을 쉼표로 나눠 전송합니다.
  function editDraft(d) {
    const sentence = (c, index) =>
      `<div class="news-sentence">${text("sentence", "본문 문장 " + index, c.statement_text, 'required maxlength="1000"')}${input("fact_keys", "Fact Key (쉼표로 구분)", c.fact_keys.join(", "), "text", "required")}<button type="button" data-remove-sentence>문장 삭제</button></div>`;
    modal(
      "새 수정본 작성",
      `<p>수정하면 새 버전으로 저장되며 제목과 모든 문장을 다시 검토해야 합니다.</p><p>사용 가능한 Fact: ${escape(d.facts.map((f) => f.fact_key).join(", "))}</p>${input("title", "기사 제목", d.title, "text", 'required minlength="5" maxlength="200"')}${input("title_fact_keys", "제목 근거 Fact Key", d.claims[0]?.fact_keys.join(", "), "text", "required")}<div data-sentences>${d.claims
        .slice(1)
        .map((c, i) => sentence(c, i + 1))
        .join(
          "",
        )}</div><button type="button" data-add-sentence>문장 추가</button>${text("reason", "수정 이유", "", 'required minlength="3" maxlength="1000"')}${submit("새 수정본 저장")}`,
      async (data, form) => {
        const split = (value) =>
          String(value)
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean);
        const claims = [
          ...form.querySelectorAll("[data-sentences] .news-sentence"),
        ].map((row) => ({
          sentence: row.querySelector("[name=sentence]").value,
          fact_keys: split(row.querySelector("[name=fact_keys]").value),
        }));
        await api(`/drafts/${d.id}/revisions`, "POST", {
          title: data.get("title"),
          title_fact_keys: split(data.get("title_fact_keys")),
          claims,
          reason: data.get("reason"),
          expected_content_hash: d.content_hash,
        });
      },
    );
    dialog.querySelector("[data-add-sentence]").onclick = () => {
      const list = dialog.querySelector("[data-sentences]");
      list.insertAdjacentHTML(
        "beforeend",
        sentence(
          { statement_text: "", fact_keys: [] },
          list.children.length + 1,
        ),
      );
    };
    dialog.addEventListener("click", (event) => {
      if (event.target.matches("[data-remove-sentence]"))
        event.target.closest(".news-sentence").remove();
    });
  }
  root.addEventListener("click", async (event) => {
    const b = event.target.closest("[data-news-action]");
    if (!b) return;
    const action = b.dataset.newsAction,
      id = Number(b.dataset.id) || null;
    try {
      if (action === "retry") return await window.NewsAdmin.open();
      if (action === "new-topic") return newTopic();
      if (action === "ai-check") return await openAICheck();
      if (!active) return;
      if (action === "import") importForm();
      if (action === "source") sourceForm(id);
      if (action === "fact") factForm(id);
      if (action === "evidence") evidenceForm(id);
      if (action === "verify") verifyForm(id);
      if (action === "fact-status") factStatus(id);
      if (action === "draft") await openDraft(id);
      if (action === "delete-source" || action === "delete-fact") {
        if (!confirm("이 항목을 삭제하시겠습니까?")) return;
        await api(
          `/topics/${active}/${action === "delete-source" ? "sources" : "facts"}/${id}`,
          "DELETE",
        );
        await refresh();
      }
      if (action === "generate") {
        b.disabled = true;
        status("gpt-6-luna가 검증 Fact로 초안을 작성하고 있습니다.");
        const generated = await api(`/topics/${active}/generate`, "POST");
        await refresh();
        status("초안을 저장했습니다. 제목과 각 문장의 원자료를 검토하세요.");
        await openDraft(generated.id);
      }
    } catch (error) {
      status(error.message, true);
    } finally {
      b.disabled = false;
    }
  });
  el("newsTopic").addEventListener("change", async (event) => {
    if (!ready) return;
    active = Number(event.target.value) || 0;
    try {
      if (active) await workspace();
      else {
        ++workspaceVersion;
        el("newsWorkspace").textContent = "작업할 뉴스 주제를 선택하세요.";
      }
    } catch (error) {
      unavailable(error);
    }
  });
  window.NewsAdmin = {
    open: () => {
      if (opening) return opening;
      opening = (async () => {
        loading = true;
        ready = false;
        controls();
        status("뉴스 연결과 시군구·주제 목록을 확인하고 있습니다.");
        try {
          const health = await api("/health");
          const lists = await Promise.all([api("/regions"), api("/topics")]);
          if (lists.some((list) => !Array.isArray(list))) throw Error("뉴스 목록을 확인할 수 없습니다. 연결을 다시 확인하세요.");
          [regions, topics] = lists;
          ready = true;
          el("newsRecovery").hidden = true;
          topicSelector();
          if (active) await workspace();
          else el("newsWorkspace").textContent = "새 주제를 등록하거나 기존 주제를 선택해 작업하세요.";
          status(
            `뉴스 서버 연결됨 · ${health.model} · ${health.openaiConfigured ? "AI 키 설정됨" : "서버에 OPENAI_API_KEY를 설정하면 초안 생성 가능"}${health.modelConfigured ? "" : " · OPENAI_NEWS_MODEL 설정을 확인하세요"}`,
          );
        } catch (error) {
          unavailable(error);
        } finally {
          loading = false;
          opening = null;
          controls();
        }
      })();
      return opening;
    },
  };
  controls();
})();
