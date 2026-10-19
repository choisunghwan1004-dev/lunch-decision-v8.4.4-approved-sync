"use strict";
// Only this server holds the internal key. Existing admin sessions authorize newsroom writes.
const express = require("express");

function createNewsProxy(options = {}) {
  const router = express.Router();
  router.use(async (req, res) => {
    const publicRead =
      req.method === "GET" && /^\/public(?:\/[1-9]\d*)?$/.test(req.path);
    const routes = {
      GET: [
        /^\/health$/,
        /^\/regions$/,
        /^\/topics$/,
        /^\/topics\/[1-9]\d*\/(sources|facts|fact-sheet|drafts)$/,
        /^\/drafts\/[1-9]\d*$/,
      ],
      POST: [
        /^\/topics$/,
        /^\/topics\/[1-9]\d*\/(sources|facts|generate)$/,
        /^\/topics\/[1-9]\d*\/facts\/[1-9]\d*\/(evidence|verify|status)$/,
        /^\/drafts\/[1-9]\d*\/(revisions|review|publish|unpublish)$/,
        /^\/drafts\/[1-9]\d*\/claims\/[1-9]\d*\/review$/,
      ],
      PUT: [/^\/topics\/[1-9]\d*\/(sources|facts)\/[1-9]\d*$/],
      DELETE: [
        /^\/topics\/[1-9]\d*\/(sources|facts)\/[1-9]\d*$/,
        /^\/topics\/[1-9]\d*\/facts\/[1-9]\d*\/evidence\/[1-9]\d*$/,
      ],
    };
    if (!publicRead && !req.session?.adminId)
      return res
        .status(401)
        .json({ ok: false, detail: "관리자 로그인이 필요합니다." });
    if (
      !publicRead &&
      !(routes[req.method] || []).some((pattern) => pattern.test(req.path))
    )
      return res
        .status(404)
        .json({ ok: false, detail: "뉴스 경로가 없습니다." });
    const write = !["GET", "HEAD"].includes(req.method);
    if (write) {
      const origin = req.get("origin");
      if (
        (origin && origin !== `${req.protocol}://${req.get("host")}`) ||
        req.get("x-news-request") !== "1" ||
        !req.is("application/json")
      )
        return res
          .status(403)
          .json({ ok: false, detail: "뉴스 요청 인증을 확인하세요." });
    }
    const token = options.token ?? process.env.NEWS_INTERNAL_TOKEN ?? "";
    let base;
    try {
      base = new URL(
        options.upstream ??
          process.env.NEWS_SERVICE_URL ??
          "http://127.0.0.1:8001",
      );
      if (
        base.protocol !== "http:" ||
        !["127.0.0.1", "localhost"].includes(base.hostname) ||
        base.pathname !== "/" ||
        base.search ||
        base.hash ||
        base.username ||
        base.password
      )
        throw Error();
    } catch {
      return res
        .status(503)
        .json({
          ok: false,
          detail: "NEWS_SERVICE_URL은 로컬 FastAPI 주소여야 합니다.",
        });
    }
    if (!/^[a-fA-F0-9]{64}$/.test(token))
      return res
        .status(503)
        .json({
          ok: false,
          detail: "뉴스 설치 후 Node와 FastAPI를 다시 시작하세요.",
        });
    const target = new URL(req.path, base);
    if (publicRead) {
      for (const key of Object.keys(req.query)) {
        const value = req.query[key];
        if (
          !["district_id", "limit"].includes(key) ||
          typeof value !== "string" ||
          !/^\d+$/.test(value)
        )
          return res
            .status(422)
            .json({ ok: false, detail: "뉴스 검색 조건이 잘못되었습니다." });
        target.searchParams.set(key, value);
      }
    }
    try {
      const response = await (options.fetchImpl || fetch)(target, {
        method: req.method,
        redirect: "error",
        signal: AbortSignal.timeout(55000),
        headers: {
          "content-type": "application/json",
          "x-news-internal-token": token,
          "x-news-editor": encodeURIComponent(
            String(req.session?.adminUsername || "admin").slice(0, 100),
          ),
        },
        ...(write ? { body: JSON.stringify(req.body || {}) } : {}),
      });
      const data = await response.json();
      res.set("Cache-Control", "no-store").status(response.status).json(data);
    } catch {
      res
        .status(503)
        .json({
          ok: false,
          detail:
            "뉴스 서버에 연결할 수 없습니다. FastAPI(8001) 실행을 확인하세요.",
        });
    }
  });
  return router;
}
module.exports = createNewsProxy;
