/**
 * 사용자용 지역 소식: 원문 대조 후 검증·저장된 공개 기사를 지역 선택과 무관하게 조회합니다.
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
  let timer, request = 0, items = [], detailDialog;
  // 지역 소식은 점심·여행 선택과 무관하게 검증 저장된 최신 기사를 조회합니다.
  async function refresh() {
    const current = ++request;
    el("regionalNewsStatus").textContent = "지역 소식을 불러오고 있습니다.";
    try {
      const response = await fetch("/api/news/public?limit=30", {cache: "no-store"});
      if (!response.ok) throw Error();
      const result = await response.json();
      if (!Array.isArray(result)) throw Error();
      if (current !== request) return;
      items = result;
      el("regionalNewsStatus").textContent = items.length ? `원문 대조 후 검증·저장된 지역 소식 ${items.length}건` : "검증 후 저장된 지역 소식이 아직 없습니다.";
      el("regionalNewsCards").innerHTML = items.map(article => `<article class="news-public-card"><small>${escape(article.region_name)} · ${escape(date(article.published_at))}</small><h3>${escape(article.title)}</h3><p>${escape(article.summary)}</p><button type="button" data-news-detail="${article.id}">소식 읽기 ↗</button></article>`).join("");
    } catch {
      if (current === request) el("regionalNewsStatus").textContent = "지역 소식을 불러올 수 없습니다. 새로고침을 눌러 다시 확인하세요.";
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
  el("regionalNewsCards").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-news-detail]");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await fetch(
        "/api/news/public/" + button.dataset.newsDetail,
        { cache: "no-store" },
      );
      if (!response.ok)
        throw Error("이 기사는 게시가 중단되었거나 변경되었습니다.");
      const article = await response.json();
      detailDialog?.remove();
      detailDialog = document.createElement("dialog");
      detailDialog.className = "news-public-dialog";
      detailDialog.innerHTML = `<button type="button" class="news-close">닫기</button><h2>${escape(article.title)}</h2><p><small>${escape(article.region_name)} · ${escape(date(article.published_at))}</small></p><div class="news-body">${escape(article.body)}</div><div class="news-attribution"><b>원자료 출처</b>${article.sources.map((s) => `<p><a href="${link(s.source_url)}" target="_blank" rel="noopener noreferrer">${escape(s.source_title)} ↗</a><br><small>${escape(s.organization)} · ${escape(date(s.published_at))}</small></p>`).join("")}<small>원문 대조 후 검증·저장한 기사입니다.</small></div>`;
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
