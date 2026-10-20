/**
 * 사용자용 지역 소식: 원문 검증 Fact와 검증·저장된 기사를 지역 선택과 무관하게 조회합니다.
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
  let timer, request = 0, items = [], detailDialog;
  // 검증 Fact만 있어도 조회합니다. 기사 초안을 저장했다는 이유로 검증 전 기사를 공개하지 않습니다.
  async function refresh() {
    const current = ++request;
    el("regionalNewsStatus").textContent = "지역 소식을 불러오고 있습니다.";
    try {
      const result = await read("/public/feed?limit=30");
      if (!Array.isArray(result)) throw Error();
      if (current !== request) return;
      items = result;
      el("regionalNewsStatus").textContent = items.length ? `원문을 대조한 지역 소식 ${items.length}건` : "검증된 지역 소식이 아직 없습니다. 운영용 주제의 Fact를 원문 대조 후 검증하면 표시됩니다.";
      el("regionalNewsCards").innerHTML = items.map(item => `<article class="news-public-card"><small>${escape(item.region_name)} · ${escape(date(item.published_at))} · ${kindLabel(item)}</small><h3>${escape(item.title)}</h3><p>${escape(item.summary)}</p><button type="button" data-news-detail="${escape(item.id)}" data-news-kind="${item.kind === "facts" ? "facts" : "article"}">소식 읽기 ↗</button></article>`).join("");
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
    try {
      // 공개 직후 자료가 바뀌었을 수 있으므로 카드에 남은 본문을 쓰지 않고 서버에서 재검사합니다.
      const isFact = button.dataset.newsKind === "facts";
      const article = await read("/public/" + (isFact ? "facts/" : "") + button.dataset.newsDetail);
      detailDialog?.remove();
      detailDialog = document.createElement("dialog");
      detailDialog.className = "news-public-dialog";
      detailDialog.innerHTML = `<button type="button" class="news-close">닫기</button><h2>${escape(article.title)}</h2><p><small>${escape(article.region_name)} · ${escape(date(article.published_at))} · ${kindLabel(article)}</small></p><div class="news-body">${escape(article.body)}</div><div class="news-attribution"><b>원자료 출처</b>${article.sources.map((s) => `<p><a href="${link(s.source_url)}" target="_blank" rel="noopener noreferrer">${escape(s.source_title)} ↗</a><br><small>${escape(s.organization)} · ${escape(date(s.published_at))}</small></p>`).join("")}<small>${isFact ? "운영자가 원문과 대조한 사실을 정리한 소식입니다." : "원문 대조 후 검증·저장한 기사입니다."}</small></div>`;
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
  schedule();
})();
