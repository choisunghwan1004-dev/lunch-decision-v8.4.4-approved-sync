const test = require("node:test"),
  assert = require("node:assert/strict");
const express = require("express"),
  session = require("express-session");
const proxy = require("../routes/news-proxy");
const { once } = require("node:events");

test("news proxy restricts private routes, methods and browser writes; keeps secret on server", async () => {
  const seen = [];
  const app = express();
  app.use(express.json());
  app.use(
    session({
      secret: "test-news-session-at-least-thirty-two-characters",
      resave: false,
      saveUninitialized: false,
    }),
  );
  app.post("/test-login", (req, res) => {
    req.session.adminId = "env";
    req.session.adminUsername = "editor";
    res.json({ ok: true });
  });
  app.use(
    "/api/news",
    proxy({
      token: "a".repeat(64),
      fetchImpl: async (url, options) => {
        seen.push({ url: String(url), options });
        return { status: 200, json: async () => ({ ok: true }) };
      },
    }),
  );
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  const base = "http://127.0.0.1:" + server.address().port;
  try {
    assert.equal((await fetch(base + "/api/news/topics")).status, 401);
    assert.equal((await fetch(base + "/api/news/ai/status")).status, 401);
    assert.equal((await fetch(base + "/api/news/drafts/1/verify-and-save", {method:"POST"})).status, 401);
    assert.equal((await fetch(base + "/api/news/ai/check", {method: "POST"})).status, 401);
    assert.equal(
      (await fetch(base + "/api/news/public?district_id=2&limit=6")).status,
      200,
    );
    assert.equal((await fetch(base + "/api/news/public/1")).status, 200);
    assert.equal((await fetch(base + "/api/news/public/version")).status, 200);
    assert.equal(seen.at(-1).url, "http://127.0.0.1:8001/public/version");
    assert.equal((await fetch(base + "/api/news/public/version", {method:"POST"})).status, 401);
    assert.equal((await fetch(base + "/api/news/public/1?district_id=2")).status, 200);
    assert.equal(seen.at(-1).url, "http://127.0.0.1:8001/public/1?district_id=2");
    assert.equal((await fetch(base + "/api/news/public/feed?limit=30")).status, 200);
    assert.equal(seen.at(-1).url, "http://127.0.0.1:8001/public/feed?limit=30");
    const facts = await fetch(base + "/api/news/public/facts/1");
    assert.equal(facts.status, 200);
    assert.equal(facts.headers.get("cache-control"), "no-store");
    assert.equal((await fetch(base + "/api/news/public/facts/1", {method:"POST"})).status, 401);
    assert.equal((await fetch(base + "/api/news/public/facts/1/evidence")).status, 401);
    assert.equal(
      (await fetch(base + "/api/news/public?token=anything")).status,
      422,
    );
    assert.equal(
      (await fetch(base + "/api/news/public/1/../topics")).status,
      401,
    );
    assert.equal(
      (await fetch(base + "/api/news/public", { method: "POST" })).status,
      401,
    );
    const login = await fetch(base + "/test-login", { method: "POST" }),
      cookie = login.headers.get("set-cookie").split(";")[0];
    assert.equal(
      (await fetch(base + "/api/news/topics", { headers: { cookie } })).status,
      200,
    );
    assert.equal(
      (await fetch(base + "/api/news/secrets", { headers: { cookie } })).status,
      404,
    );
    const write = {
      method: "POST",
      headers: { cookie, "content-type": "application/json" },
      body: JSON.stringify({ title: "test" }),
    };
    assert.equal((await fetch(base + "/api/news/topics", write)).status, 403);
    assert.equal((await fetch(base + "/api/news/drafts/1/verify-and-save", write)).status, 403);
    write.headers["x-news-request"] = "1";
    write.headers.origin = "https://elsewhere.example";
    assert.equal((await fetch(base + "/api/news/topics", write)).status, 403);
    write.headers.origin = base;
    const response = await fetch(base + "/api/news/topics", write);
    assert.equal(response.status, 200);
    assert.ok(!JSON.stringify(await response.json()).includes("a".repeat(64)));
    assert.equal(
      seen.at(-1).options.headers["x-news-internal-token"],
      "a".repeat(64),
    );
    assert.equal(seen.at(-1).options.headers["x-news-editor"], "editor");
    assert.equal(seen.at(-1).url, "http://127.0.0.1:8001/topics");
    assert.equal((await fetch(base + "/api/news/ai/status", {headers: {cookie}})).status, 200);
    write.body = JSON.stringify({confirmation: "CALL_OPENAI"});
    assert.equal((await fetch(base + "/api/news/ai/check", write)).status, 200);
    assert.equal(seen.at(-1).url, "http://127.0.0.1:8001/ai/check");
    write.headers.origin = "https://elsewhere.example";
    assert.equal((await fetch(base + "/api/news/ai/check", write)).status, 403);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("invalid internal configuration fails closed without affecting the main app", async () => {
  const app = express();
  app.use("/api/news", proxy({ token: "" }));
  const server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const response = await fetch(
      "http://127.0.0.1:" + server.address().port + "/api/news/public",
    );
    assert.equal(response.status, 503);
    const body = await response.json();
    assert.equal(body.code, "news_not_configured");
    assert.match(body.detail, /18_뉴스_연결복구/);
    assert.ok(!JSON.stringify(body).includes("NEWS_INTERNAL_TOKEN="));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
