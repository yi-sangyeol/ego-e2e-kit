// ego-browser nodejs で動く録画ランナー。make.sh が先頭に `const OUT = "<作業ディレクトリ>";` を付けて渡す。
// scenario.json の steps を順に実操作し、操作中のフレームだけ連写して timeline.json に残す（静止区間は build.py が保持する）。
const fs = await import("node:fs/promises");

const readJson = async (name) => JSON.parse(await fs.readFile(`${OUT}/${name}`, "utf8"));
const scenario = await readJson("scenario.json");
const eff = await readJson("effective.json"); // make.sh が既定値・個人設定・プロジェクト設定・scenario をまとめたもの
const { credit = "" } = await readJson("voice.json");
const narr = await readJson("narration.json"); // { 文: { file, sec, disp } }  disp = 字幕に出す文（漢数字を半角数字にしたもの）
const secOf = (text) => narr[text]?.sec ?? 3;
const dispOf = (text) => narr[text]?.disp ?? text;

// 1 回の依頼で 1 つの TaskSpace を使い回す。並列で撮るときは scenario.json の video.taskSpace でケースごとに分ける
const task = await taskSpace(eff.video.taskSpace);
const page = task.page("p1");
const pause = (ms) => page.waitForTimeout(ms);
// 録画用に viewport を固定する（既定 1280x800）。広い画面のまま撮ると文字が小さく、フレームも重くなる
const VIEW = { width: 1280, height: 800, ...eff.video.viewport };
await page.cdp("Emulation.setDeviceMetricsOverride", { ...VIEW, deviceScaleFactor: 1, mobile: false });
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// 字幕の帯。goto のたびに消えるので毎回入れ直す。赤枠と重なるなら画面の上に移す。文字列は textContent で入れる
async function caption(header, text, foot = "") {
  await page.evaluate(({ header, text, foot }) => {
    let el = document.getElementById("__test_caption__");
    if (!el) {
      el = document.createElement("div");
      el.id = "__test_caption__";
      el.style.cssText =
        "position:fixed;left:0;right:0;z-index:2147483647;pointer-events:none;" +
        "background:rgba(0,0,0,.78);color:#fff;padding:12px 18px 14px;" +
        "font:600 17px/1.55 'Hiragino Sans','Hiragino Kaku Gothic ProN',sans-serif;";
      document.documentElement.appendChild(el);
    }
    el.textContent = "";
    const h = document.createElement("div");
    h.style.cssText = "font-size:13px;color:#ffd166;margin-bottom:4px";
    h.textContent = header;
    const b = document.createElement("div");
    b.textContent = text;
    el.append(h, b);
    if (foot) {
      const f = document.createElement("div");
      f.style.cssText = "font-size:12px;font-weight:400;color:#ccc;margin-top:6px";
      f.textContent = foot;
      el.append(f);
    }
    const box = document.getElementById("__test_box__")?.getBoundingClientRect();
    const covered = box && box.bottom > window.innerHeight - el.offsetHeight;
    el.style.top = covered ? "0" : "auto";
    el.style.bottom = covered ? "auto" : "0";
  }, { header, text, foot });
}

// 文言が一致する一番内側の要素を探し、up 段だけ親へ上がった要素を赤枠で囲む。mark が無ければ枠を消す
async function highlight(mark) {
  return page.evaluate(({ mark }) => {
    document.getElementById("__test_box__")?.remove();
    if (!mark) return null;
    const { text, up = 0, scope } = mark;
    const root = scope ? document.querySelector(scope) ?? document.body : document.body;
    const hits = [...root.querySelectorAll("*")].filter(
      (e) => e.id !== "__test_caption__" && e.offsetParent !== null && e.innerText?.trim() === text,
    );
    let el = hits.find((e) => ![...e.children].some((c) => c.innerText?.trim() === text)) ?? hits[0];
    if (!el) return false;
    for (let i = 0; i < up && el.parentElement; i++) el = el.parentElement;
    el.scrollIntoView({ block: "center", behavior: "instant" });
    const r = el.getBoundingClientRect();
    const box = document.createElement("div");
    box.id = "__test_box__";
    box.style.cssText =
      `position:fixed;left:${r.left - 6}px;top:${r.top - 6}px;width:${r.width + 12}px;height:${r.height + 12}px;` +
      "border:4px solid #e11d48;border-radius:8px;box-shadow:0 0 0 4px rgba(225,29,72,.25);" +
      "z-index:2147483646;pointer-events:none;";
    document.documentElement.appendChild(box);
    return true;
  }, { mark });
}

// 文言が一致する一番内側の要素を実際にクリックする
async function clickText({ text, scope }) {
  const ok = await page.evaluate(({ text, scope }) => {
    const root = scope ? document.querySelector(scope) ?? document.body : document.body;
    const hits = [...root.querySelectorAll("*")].filter((e) => e.offsetParent !== null && e.innerText?.trim() === text);
    const el = hits.find((e) => ![...e.children].some((c) => c.innerText?.trim() === text)) ?? hits[0];
    el?.click();
    return Boolean(el);
  }, { text, scope });
  if (!ok) throw new Error(`click 対象が見つからない: ${text}`);
}

const framesDir = `${OUT}/frames`;
await fs.rm(framesDir, { recursive: true, force: true });
await fs.mkdir(framesDir, { recursive: true });

let seq = 0;
async function shot(t) {
  const r = await page.cdp("Page.captureScreenshot", { format: "jpeg", quality: 75 });
  const name = `f${String(seq++).padStart(5, "0")}.jpg`;
  await fs.writeFile(`${framesDir}/${name}`, Buffer.from(r.data, "base64"));
  return { name, t };
}

// 動画とは別に残す PNG (screenshots: per-step | on-fail)。字幕と赤枠が入った状態で撮る
const shotsDir = `${OUT}/shots`;
await fs.rm(shotsDir, { recursive: true, force: true });
async function still(name) {
  await fs.mkdir(shotsDir, { recursive: true });
  const r = await page.cdp("Page.captureScreenshot", { format: "png" });
  const file = `${shotsDir}/${name}.png`;
  await fs.writeFile(file, Buffer.from(r.data, "base64"));
  return file;
}

// 操作中だけ連写する。stop() で止めて、撮れたフレームを返す
function capture(t0) {
  const st = { on: true, frames: [] };
  st.done = (async () => {
    while (st.on) {
      try { st.frames.push(await shot(Date.now() - t0)); } catch { await new Promise((r) => setTimeout(r, 50)); }
    }
  })();
  st.stop = async () => { st.on = false; await st.done; return st.frames; };
  return st;
}

const steps = [], found = [], failed = [], checks = {};
const total = scenario.steps.length;

// 画面が落ち着くまで待つ（読み込み完了 + 本文が 300ms 変わらない）。固定の待ちより短く、遅い画面には長く待てる
async function settle(maxMs = 8000) {
  const end = Date.now() + maxMs;
  let prev = -1, same = 0;
  while (Date.now() < end) {
    const cur = await page.evaluate(() => (document.readyState === "complete" ? document.body.innerText.length : -2));
    same = cur === prev && cur >= 0 ? same + 1 : 0;
    if (same >= 2) return;
    prev = cur;
    await pause(150);
  }
}

async function runStep(i, s) {
  const header = `${scenario.title} (${i}/${total})`;
  const say = dispOf(s.say);
  let cap, t0;
  try {
    // 読み込み中の画面は動かないので録画しない。ページが開いてから撮り始める
    if (s.goto) { await page.goto(s.goto); await settle(); }
    t0 = Date.now();
    cap = capture(t0);
    await caption(header, say); // 字幕は操作の開始時に出す（ナレーションも同時に始まる）
    if (s.click) { await clickText(typeof s.click === "string" ? { text: s.click } : s.click); await pause(400); await settle(s.wait ?? 4000); }
    if (s.run) { await new AsyncFunction("page", "pause", "task", "checks", s.run)(page, pause, task, checks); await pause(400); await settle(s.wait ?? 4000); }
    const hit = await highlight(s.mark);
    if (s.mark) found.push({ step: i, text: s.mark.text, found: hit });
    let ok = true;
    if (s.expect) {
      const body = await page.evaluate(() => document.body.innerText);
      checks[`step${i}`] = body;
      const want = Array.isArray(s.expect) ? s.expect : [s.expect];
      ok = want.every((w) => body.includes(w));
      if (!ok) failed.push({ step: i, expect: s.expect });
    }
    await caption(header, say); // goto / click で消えた字幕を戻し、赤枠と重なるなら位置を替える
    await pause(120);
    const frames = await cap.stop();
    const last = await shot(Date.now() - t0); // 字幕と赤枠が入った最後の 1 枚（音声のほうが長ければここから静止）
    frames.push(last);
    if (eff.screenshots === "per-step" || (eff.screenshots === "on-fail" && !ok)) {
      await still(`step-${String(i).padStart(2, "0")}${ok ? "" : "-fail"}`);
    }
    steps.push({ step: i, text: s.say, sec: secOf(s.say), A: last.t, frames, ok });
  } catch (e) {
    await cap?.stop().catch(() => {});
    throw new Error(`step ${i} で失敗: ${e.message}`);
  }
}

for (let i = 1; i <= total; i++) await runStep(i, scenario.steps[i - 1]);

// 結論のナレーションは、expect の実結果で自動的に選ぶ（録画を 2 回しない）
const verdictText = failed.length ? scenario.verdict.fail : scenario.verdict.pass;
{
  const t0 = Date.now();
  await caption(`${scenario.title} (結論)`, dispOf(verdictText), credit); // VOICEVOX は利用規約でクレジット表記が必要
  await pause(150);
  const last = await shot(Date.now() - t0);
  if (eff.screenshots === "per-step") await still("verdict");
  steps.push({ step: total + 1, text: verdictText, sec: secOf(verdictText), A: 0, frames: [{ ...last, t: 0 }], ok: !failed.length });
}

await page.cdp("Emulation.clearDeviceMetricsOverride", {}).catch(() => {}); // 共有 TaskSpace の画面を元に戻す
await fs.writeFile(`${OUT}/timeline.json`, JSON.stringify({ steps }, null, 2));
await fs.writeFile(`${OUT}/result.json`, JSON.stringify({ verdict: failed.length ? "fail" : "pass", failed, found, checks }, null, 2));
const missing = found.filter((f) => f.found === false);
console.log(JSON.stringify({ verdict: failed.length ? "fail" : "pass", failed, missing, frames: seq }));
