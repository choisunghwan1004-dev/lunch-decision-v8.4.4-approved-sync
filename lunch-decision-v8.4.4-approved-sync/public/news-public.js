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
  let mode = "lunch",
    timer,
    request = 0,
    items = [],
    detailDialog;
  async function refresh() {
    const region =
        Number(el(mode === "travel" ? "travelCity" : "cityId")?.value) || 0,
      current = ++request;
    el("regionalNewsCards").replaceChildren();
    if (!region) {
      el("regionalNewsStatus").textContent =
        "지역을 선택하면 해당 지역의 소식을 보여드립니다.";
      return;
    }
    el("regionalNewsStatus").textContent = "지역 소식을 불러오고 있습니다.";
    try {
      const response = await fetch(
        `/api/news/public?district_id=${region}&limit=6`,
        { cache: "no-store" },
      );
      if (!response.ok) throw Error();
      const result = await response.json();
      if (current !== request) return;
      items = result;
      el("regionalNewsStatus").textContent = items.length
        ? `${items[0].region_name} · 편집자가 검토한 소식 ${items.length}건`
        : "아직 이 지역에 게시된 소식이 없습니다.";
      el("regionalNewsCards").innerHTML = items
        .map(
          (article) =>
            `<article class="news-public-card"><small>${escape(article.region_name)} · ${escape(date(article.published_at))}</small><h3>${escape(article.title)}</h3><p>${escape(article.summary)}</p><button type="button" data-news-detail="${article.id}">소식 읽기 ↗</button></article>`,
        )
        .join("");
    } catch {
      if (current === request)
        el("regionalNewsStatus").textContent =
          "지역 소식을 불러올 수 없습니다. 잠시 후 다시 확인해 주세요.";
    }
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 150);
  }
  document.querySelectorAll("[data-news-mode]").forEach((button) =>
    button.addEventListener("click", () => {
      mode = button.dataset.newsMode;
      document
        .querySelectorAll("[data-news-mode]")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      schedule();
    }),
  );
  [
    "countryId",
    "provinceId",
    "districtId",
    "townId",
    "areaId",
    "travelCity",
  ].forEach((id) => el(id)?.addEventListener("change", schedule));
  // Existing location initialization fills the options asynchronously and restores saved choices.
  if (el("travelCity"))
    new MutationObserver(schedule).observe(el("travelCity"), {
      childList: true,
    });
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
      detailDialog.innerHTML = `<button type="button" class="news-close">닫기</button><h2>${escape(article.title)}</h2><p><small>${escape(article.region_name)} · ${escape(date(article.published_at))}</small></p><div class="news-body">${escape(article.body)}</div><div class="news-attribution"><b>원자료 출처</b>${article.sources.map((s) => `<p><a href="${link(s.source_url)}" target="_blank" rel="noopener noreferrer">${escape(s.source_title)} ↗</a><br><small>${escape(s.organization)} · ${escape(date(s.published_at))}</small></p>`).join("")}<small>AI가 초안을 작성하고 편집자가 원자료 대조와 최종 검토를 마친 기사입니다.</small></div>`;
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
