/**
 * 사용자용 지역 소식: 메인에서 선택한 실제 시군구의 검증 소식과 행사일정을 조회합니다.
 * 이 파일은 AI 생성·Fact 검증·승인 권한을 가지지 않으며 비공개 초안을 조회하지 않습니다.
 */
(() => {
  "use strict";
  const el = (id) => document.getElementById(id);
  if (!el("regionalNews")) return;
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
  const date = (value) =>
    value
      ? new Intl.DateTimeFormat("ko-KR", {
          dateStyle: "medium",
          timeZone: "Asia/Seoul",
        }).format(
          new Date(
            /(?:Z|[+-]\d{2}:\d{2})$/.test(String(value))
              ? String(value)
              : String(value) + "Z",
          ),
        )
      : "";
  const link = (value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? escape(url.href) : "#";
    } catch {
      return "#";
    }
  };
  const kindLabel = (item) => item.kind === "facts" ? "원문 검증 소식" : "검증 기사";
  // 행사 날짜는 지역의 달력 날짜이므로 UTC 시각으로 바꾸거나 브라우저 시차를 적용하지 않습니다.
  const calendarDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? String(value).replaceAll('-', '.') : '';
  const eventRange = (event) => {
    const start = calendarDate(event.start_date), end = calendarDate(event.end_date);
    return start ? start + (end && end !== start ? ` ~ ${end}` : '') : '';
  };
  function eventHTML(item, detail = false) {
    const events = (Array.isArray(item.events) ? item.events : []).filter(event => eventRange(event));
    if (!events.length) return '';
    if (detail) return `<section class="news-event-list"><b>행사일정</b>${events.map(event => `<p><strong>${escape(eventRange(event))}</strong><br>${escape(event.label)}</p>`).join('')}</section>`;
    const ranges = [...new Set(events.map(eventRange))];
    return `<p class="news-event-date">행사일정 · ${ranges.map(escape).join(' / ')}</p>`;
  }
  async function read(path) {
    const response = await fetch("/api/news" + path, {cache: "no-store"});
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 404 || response.status === 422)
        throw Error("소식이 변경되었거나 뉴스 서버가 이전 버전입니다. 최신 코드를 적용하고 Node·FastAPI를 모두 다시 시작하세요.");
      throw Error(typeof result.detail === "string" ? result.detail : "지역 소식을 불러올 수 없습니다. 뉴스 서버 실행을 확인하세요.");
    }
    return result;
  }
  let timer, request = 0, items = [], detailDialog, districtId = 0, regionName = '';
  // 이 표시는 실행 진단에서 HTML·JS·Python의 적용 버전을 대조할 때 사용합니다.
  el('regionalNews').dataset.newsView = 'location-news-v1';
  function regionChanged() {
    const root = el('regionalNews'), next = Number(root.dataset.districtId || 0);
    regionName = root.dataset.regionName || '';
    el('regionalNewsRegion').textContent = next ? `선택 지역 · ${regionName}` : '상단에서 국가·시/도·시군구를 선택하세요.';
    if (next === districtId) return;
    districtId = next;
    // 느린 이전 요청의 응답·상세창·카드를 즉시 비워 지역이 섞이지 않게 합니다.
    detailDialog?.remove();
    el('regionalNewsCards').replaceChildren();
    schedule();
  }
  // 검증 Fact만 있어도 조회합니다. 기사 초안을 저장했다는 이유로 검증 전 기사를 공개하지 않습니다.
  async function refresh() {
    const current = ++request;
    if (!districtId) {
      el('regionalNewsStatus').textContent = '시군구를 선택하면 해당 지역의 검증된 뉴스·행사일정을 보여드립니다.';
      el('regionalNewsCards').replaceChildren();
      return;
    }
    const selectedDistrict = districtId, selectedName = regionName;
    el("regionalNewsStatus").textContent = `${selectedName} 소식을 불러오고 있습니다.`;
    try {
      const result = await read(`/public/feed?district_id=${selectedDistrict}&limit=30`);
      if (!Array.isArray(result)) throw Error();
      if (current !== request) return;
      items = result;
      el("regionalNewsStatus").textContent = items.length ? `${selectedName} · 검증된 뉴스·행사 소식 ${items.length}건` : `${selectedName}의 검증된 지역 소식이 아직 없습니다. 이 시군구의 운영용 주제에서 Fact를 원문 대조 후 검증하면 표시됩니다.`;
      el("regionalNewsCards").innerHTML = items.map(item => `<article class="news-public-card"><small>${escape(item.region_name)} · ${kindLabel(item)}</small><h3>${escape(item.title)}</h3>${eventHTML(item)}<p>${escape(item.summary)}</p><small class="news-updated">${item.kind === 'facts' ? '검증' : '게시'} ${escape(date(item.published_at))}</small><button type="button" data-news-detail="${escape(item.id)}" data-news-kind="${item.kind === "facts" ? "facts" : "article"}">소식 읽기 ↗</button></article>`).join("");
    } catch (error) {
      if (current === request) {
        el("regionalNewsStatus").textContent = error.message || "지역 소식을 불러올 수 없습니다. 새로고침을 눌러 다시 확인하세요.";
        el("regionalNewsCards").replaceChildren();
      }
    }
  }
  function schedule() {
    ++request; clearTimeout(timer); timer = setTimeout(refresh, 150);
  }
  el("regionalNewsRefresh")?.addEventListener("click", schedule);
  window.addEventListener('main-region-changed', regionChanged);
  // 게시 알림에는 시각만 사용합니다. 비공개 기사나 내부 토큰을 저장하지 않습니다.
  window.addEventListener("storage", event => {if (event.key === "regional-news-changed") schedule();});
  window.addEventListener("focus", schedule);
  document.addEventListener("visibilitychange", () => {if (document.visibilityState === "visible") schedule();});
  // 다른 브라우저에서 검증하거나 저장소 알림을 쓸 수 없어도 열린 화면이 30초마다 다시 읽습니다.
  window.setInterval(() => {if (document.visibilityState === "visible") schedule();}, 30000);
  el("regionalNewsCards").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-news-detail]");
    if (!button) return;
    button.disabled = true;
    const selectedDistrict = districtId;
    try {
      // 공개 직후 자료가 바뀌었을 수 있으므로 카드에 남은 본문을 쓰지 않고 서버에서 재검사합니다.
      const isFact = button.dataset.newsKind === "facts";
      const article = await read("/public/" + (isFact ? "facts/" : "") + button.dataset.newsDetail + `?district_id=${selectedDistrict}`);
      if (selectedDistrict !== districtId) return;
      detailDialog?.remove();
      detailDialog = document.createElement("dialog");
      detailDialog.className = "news-public-dialog";
      detailDialog.innerHTML = `<button type="button" class="news-close">닫기</button><h2>${escape(article.title)}</h2><p><small>${escape(article.region_name)} · ${isFact ? '검증' : '게시'} ${escape(date(article.published_at))} · ${kindLabel(article)}</small></p>${eventHTML(article, true)}<div class="news-body">${escape(article.body)}</div><div class="news-attribution"><b>원자료 출처</b>${article.sources.map((s) => `<p><a href="${link(s.source_url)}" target="_blank" rel="noopener noreferrer">${escape(s.source_title)} ↗</a><br><small>${escape(s.organization)} · ${escape(date(s.published_at))}</small></p>`).join("")}<small>${isFact ? "운영자가 원문과 대조한 사실을 정리한 소식입니다." : "원문 대조 후 검증·저장한 기사입니다."}</small></div>`;
      document.body.append(detailDialog);
      detailDialog.querySelector("button").onclick = () => detailDialog.close();
      detailDialog.addEventListener(
        "close",
        (event) => event.currentTarget.remove(),
        { once: true },
      );
      detailDialog.showModal();
    } catch (error) {
      el("regionalNewsStatus").textContent =
        error.message || "기사를 불러오지 못했습니다.";
      schedule();
    } finally {
      button.disabled = false;
    }
  });
  regionChanged();
  schedule();
})();
