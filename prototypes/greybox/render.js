(function () {
  "use strict";
  const sim = globalThis.PromisedWay;
  const $ = (id) => document.getElementById(id);
  const key = "promised-way-greybox-v1";
  let state = sim.initial();
  let saveMessage = "";
  try {
    const saved = localStorage.getItem(key);
    if (saved) {
      state = sim.restore(saved);
      saveMessage = "已恢复上次进度。";
    }
  } catch {
    saveMessage = "无法恢复本机进度，可导入存档文件。";
  }

  function save() {
    try {
      localStorage.setItem(key, sim.serialize(state));
      saveMessage = "进度已保存。";
    } catch {
      saveMessage = "浏览器未开放本机存储，可用「导出存档」保存。";
    }
  }

  function group(name, title, items) {
    const buttons = items.map(([value, label, detail, disabled]) =>
      `<button type="button" class="card" data-key="${name}" data-value="${value}"
          aria-pressed="${state.choice[name] === value}" ${disabled ? "disabled" : ""}><strong>${label}</strong>
          <small>${detail}</small></button>`).join("");
    return `<fieldset><legend>${title}</legend><div class="choices">${buttons}</div></fieldset>`;
  }

  function day() {
    const incident = sim.incidents[state.day];
    const evidence = incident.claims.map((line, i) =>
      state.seen.includes(i) ? `<p class="clue">${line}</p>` :
        `<button type="button" data-clue="${i}">听${i === 0 ? "守卫" : "另一位目击者"}</button>`).join("");
    const jobOptions = Object.entries(sim.jobs).map(([id, job]) =>
      [id, job.name, `粮 +${job.food} · 木 +${job.timber} · 备勤 ${job.guard}`]);
    const buildOptions = Object.entries(sim.sectors).map(([id, name]) =>
      [id, name + "加固", state.wall[id] >= 2 ? "已加固两层" : "木 −3 · 此处守备 +2", state.wall[id] >= 2]);
    return `<h2>天黑前，安排营地</h2><p class="muted">为入夜做准备。围栏的保护只覆盖它所在的位置。</p>
    <div class="groups">
      ${group("job", "经营 · 派工", jobOptions)}
      ${group("ration", "模拟 · 给居民发口粮", [
        ["full", "足额", "粮 −4 · 疲劳 −2"], ["lean", "减量", "粮 −2 · 劳作疲劳会累积"]])}
      ${group("build", "建城 · 加固一道围栏", [...buildOptions, ["none", "留木料", "本轮不加固"]])}
      <fieldset><legend>灵战 · 分辨传言</legend><p>${incident.hint}</p>
        <div class="clues">${evidence}</div>
        <p class="hint">听完两边才可核对证词。信任和恐惧会影响夜间协作。</p>
        <div class="choices">${[
          ["weigh", "核对后再传话", "多用一袋粮供核对人员 · 信任↑ 恐惧↓", state.seen.length !== 2],
          ["warn", "立即传警", "备勤 +1 · 信任↓ 恐惧↑"],
          ["hush", "压下传言", "不耗粮 · 恐惧↑"]
        ].map(([value, label, detail, disabled]) => `<button type="button" class="card"
          data-key="counsel" data-value="${value}" aria-pressed="${state.choice.counsel === value}"
          ${disabled ? "disabled" : ""}><strong>${label}</strong><small>${detail}</small></button>`).join("")}</div>
      </fieldset>
    </div>
    <p class="hint">${sim.canAdvance(state) ? "夜间将用到你现在的安排。" :
      ["job","ration","build","counsel"].every((k) => state.choice[k]) ?
        "粮食或木料不足，改派工、口粮或工事。" : "为四项各选一个安排。"} </p>`;
  }

  function night() {
    return `<h2>守夜</h2><p class="muted">${sim.incidents[state.day].hint} 让主队驻守一处，决定如何应对。</p>
    <div class="groups">
      ${group("post", "战斗 · 部署主队", Object.entries(sim.sectors).map(([id, name]) =>
        [id, name, "驻守点守备 +3"]))}
      ${group("tactic", "战斗 · 下达指令", [
        ["hold", "据栏守住", "若部署正确，守备再 +2"], ["escort", "护送居民", "守备 +1 · 失守最多损失 1 袋粮"]])}
    </div>`;
  }

  function report() {
    const r = state.summary;
    const labels = { readiness: "白天备勤", rested: "居民体力", coop: "彼此信任",
      team: "主队部署", walls: "该处围栏", tactic: "夜间指令", strain: "恐惧拖累" };
    const parts = Object.entries(r.parts).map(([id, value]) =>
      `<dt>${labels[id]}</dt><dd>${id === "strain" && value ? "−" : ""}${value}</dd>`).join("");
    return `<h2 class="${r.breach ? "bad" : "good"}">${r.title}</h2>
      <p>实际守备 <strong>${r.defense}</strong> ／ 需要 ${r.pressure}。
      ${r.breach ? `损失 ${r.loss} 袋粮，该处围栏受损。` : "居民平安，粮食保住了。"}</p>
      <dl class="breakdown">${parts}</dl>`;
  }

  function end() {
    const lost = state.losses;
    return `<h2 class="${lost ? "bad" : "good"}">${lost === 0 ? "守住了两夜" :
      lost === 2 ? "营地两夜失守" : "守住了一夜"}</h2>
      <p>剩余粮食 ${state.food} 袋，信任 ${state.trust}，恐惧 ${state.fear}。</p>
      <p class="muted">在营地纪事里回看结果，重开可从同一起点试另一种安排。</p>`;
  }

  function paint(focus) {
    const isNight = state.phase === "night" || state.phase === "report";
    $("board").classList.toggle("night", isNight);
    $("metrics").innerHTML = [
      ["粮食", state.food], ["木料", state.timber], ["疲劳", state.fatigue],
      ["信任", state.trust], ["恐惧", state.fear]
    ].map(([name, number]) => `<div><span>${name}</span><strong>${number}</strong></div>`).join("");
    $("map").innerHTML = '<div class="ridge" aria-hidden="true"></div>' +
      Object.entries(sim.sectors).map(([id, name]) => {
        const guard = isNight && state.choice.post === id;
        const wall = [0, 1].map((i) => `<i class="${i < state.wall[id] ? "built" : ""}"></i>`).join("");
        return `<div class="site${guard ? " guarded" : ""}">${id === "store" ? '<span class="shelter" aria-hidden="true"></span>' : ""}
        <div class="terrain" aria-hidden="true">${wall}</div><strong>${name}</strong>
        <small>围栏 ${state.wall[id]}/2${guard ? " · 主队驻守" : ""}</small></div>`;
      }).join("");
    $("history").innerHTML = state.log.length ? state.log.map((line) => `<li>${line}</li>`).join("") : "<li>营地刚安顿下来。</li>";
    $("boardState").textContent = state.phase === "end" ? "行程小结" :
      `第 ${state.day + 1} 天 ／ 2 · ${{day:"白昼",night:"入夜",report:"守夜结果"}[state.phase]}`;
    const action = {day:"敲响暮钟",night:"开始守夜",report:state.day === 0 ? "到下一天" : "查看全局结果"};
    $("scene").innerHTML = {day, night, report, end}[state.phase]() + (state.phase === "end" ? "" :
      `<button type="button" id="advance" class="primary" ${sim.canAdvance(state) ? "" : "disabled"}>${action[state.phase]}</button>`);
    $("saveStatus").textContent = saveMessage;
    if (focus) {
      const target = $("scene").querySelector(focus) || $("scene").querySelector("h2");
      if (target.tagName === "H2") target.tabIndex = -1;
      target.focus();
    }
  }

  $("scene").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    let move;
    let focus = "h2";
    if (button.id === "advance") move = { type:"advance" };
    else if (button.dataset.clue !== undefined) {
      move = { type:"listen", value:Number(button.dataset.clue) };
      focus = "[data-clue], [data-value=weigh]:not([disabled])";
    } else if (button.dataset.key) {
      const { key, value } = button.dataset;
      move = { type:"choose", key, value };
      focus = `[data-key="${key}"][data-value="${value}"]`;
    }
    if (move && sim.dispatch(state, move)) {
      save();
      paint(focus);
    }
  });

  $("restart").addEventListener("click", () => {
    if (state.history.length && !window.confirm("重开将替换本机进度。继续吗？")) return;
    state = sim.initial();
    save();
    paint("h2");
  });
  $("exportSave").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([sim.serialize(state)], { type:"application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "promised-way-save.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("importSave").addEventListener("click", () => $("saveInput").click());
  $("saveInput").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      if (file.size > 50000) throw new Error("文件超过 50 KB。");
      const restored = sim.restore(await file.text());
      if (!state.history.length || window.confirm("用导入的存档替换当前进度？")) {
        state = restored;
        save();
        saveMessage = "存档已恢复。" + (saveMessage === "进度已保存。" ? "" : saveMessage);
      }
    } catch (error) {
      saveMessage = error instanceof SyntaxError ? "这个文件不是有效的游戏存档。" : error.message;
    }
    event.target.value = "";
    paint("h2");
  });
  paint();
})();
