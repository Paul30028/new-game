(function (root) {
  "use strict";

  const VERSION = 1;
  const sectors = { gate: "营门", store: "粮棚" };
  const jobs = {
    gather: { name: "运粮", food: 4, timber: 1, fatigue: 2, guard: 1 },
    timber: { name: "拾木", food: 1, timber: 4, fatigue: 2, guard: 1 },
    watch: { name: "备勤", food: 1, timber: 1, fatigue: 1, guard: 3 }
  };
  const incidents = [
    { hint: "有人说营门外有一群人。", target: "gate", pressure: 5,
      claims: ["守夜人：我听见营门外有脚步，天太暗，没数清有几个人。",
        "运粮人：我从粮棚回来，也听见了同一阵脚步。路上没有其他脚印。"] },
    { hint: "有人劝你撤掉粮棚的守卫。", target: "store", pressure: 7,
      claims: ["营门守卫：有人传话说粮棚安全，叫我把那边的人调来。",
        "粮棚伙计：这话不是我传的。我看见木栏外有新痕，原来的巡查还没回来。"] }
  ];

  function initial() {
    return { day: 0, phase: "day", food: 8, timber: 4, fatigue: 1, trust: 3, fear: 2,
      wall: { gate: 0, store: 0 }, losses: 0, seen: [], choice: {},
      summary: null, log: [], history: [] };
  }

  function valid(key, group) {
    return typeof key === "string" && Object.hasOwn(group, key);
  }

  function note(s, text) {
    s.log.push(text);
  }

  function bounded(value, cap) {
    return Math.max(0, Math.min(cap, value));
  }

  function dayTurn(s) {
    const { job, ration, build, counsel } = s.choice;
    const labor = jobs[job];
    s.food += labor.food - (ration === "full" ? 4 : 2) - Number(counsel === "weigh");
    s.timber += labor.timber - (build === "none" ? 0 : 3);
    s.fatigue = bounded(s.fatigue + labor.fatigue - (ration === "full" ? 2 : 0), 8);
    if (build !== "none") s.wall[build]++;
    let message;
    if (counsel === "weigh") {
      s.trust = bounded(s.trust + 1, 6);
      s.fear = bounded(s.fear - 1, 6);
      message = "核对证词后只传已知实情，巡夜的人更愿意配合。";
    } else if (counsel === "warn") {
      s.trust = bounded(s.trust - (s.day === 1 ? 2 : 1), 6);
      s.fear = bounded(s.fear + 2, 6);
      message = "未经核对的消息扩散，营地更紧张。";
    } else {
      s.fear = bounded(s.fear + 1, 6);
      message = "你让传话的人闭嘴，居民仍在猜测。";
    }
    s.phase = "night";
    note(s, `第${s.day + 1}日入夜 · ${message}`);
  }

  function nightTurn(s) {
    const c = s.choice;
    const { target, pressure } = incidents[s.day];
    const rested = Math.max(0, 3 - s.fatigue);
    const coop = Math.floor(s.trust / 2);
    const strain = Math.floor(s.fear / 2);
    const team = Number(c.post === target) * 3;
    const walls = s.wall[target] * 2;
    const readiness = jobs[c.job].guard + Number(c.counsel === "warn");
    const tactic = c.tactic === "escort" ? 1 : team ? 2 : 0;
    const defense = Math.max(0, readiness + rested + coop + team + walls + tactic - strain);
    const breach = defense < pressure;
    const loss = breach ? Math.min(s.food, c.tactic === "escort" ? 1 : 3) : 0;
    s.food -= loss;
    s.losses += Number(breach);
    if (breach) {
      s.wall[target] = Math.max(0, s.wall[target] - 1);
      s.fear = bounded(s.fear + 1, 6);
    }
    s.summary = { day: s.day + 1, target, pressure, defense, breach, loss,
      parts: { readiness, rested, coop, team, walls, tactic, strain },
      title: breach ? `${sectors[target]}失守` : `${sectors[target]}守住了` };
    note(s, `第${s.day + 1}夜 · ${s.summary.title}${breach ? `，损失 ${loss} 袋粮` : "，居民平安"}。`);
    s.phase = "report";
  }

  function apply(s, event) {
    if (!event || typeof event !== "object") return false;
    const { type, key, value } = event;
    if (type === "listen" && s.phase === "day" && (value === 0 || value === 1) && !s.seen.includes(value)) {
      s.seen.push(value);
      return true;
    }
    if (type === "choose") {
      const choices = s.phase === "day"
        ? { job: jobs, ration: { full: 1, lean: 1 }, build: { ...sectors, none: 1 },
          counsel: { weigh: 1, warn: 1, hush: 1 } }
        : s.phase === "night" ? { post: sectors, tactic: { hold: 1, escort: 1 } } : {};
      if (!valid(key, choices) || !valid(value, choices[key]) ||
          (key === "counsel" && value === "weigh" && s.seen.length !== 2) ||
          (key === "build" && value !== "none" && s.wall[value] >= 2) ||
          s.choice[key] === value) return false;
      s.choice[key] = value;
      return true;
    }
    if (type !== "advance" || !canAdvance(s)) return false;
    if (s.phase === "day") dayTurn(s);
    else if (s.phase === "night") nightTurn(s);
    else if (s.day === 1) s.phase = "end";
    else {
      s.day++;
      s.phase = "day";
      s.fatigue = bounded(s.fatigue - 1, 8);
      s.seen = [];
      s.choice = {};
    }
    return true;
  }

  function canAdvance(s) {
    const c = s.choice;
    if (s.phase === "day") {
      if (!c.job || !c.ration || !c.build || !c.counsel) return false;
      return s.food + jobs[c.job].food >= (c.ration === "full" ? 4 : 2) + Number(c.counsel === "weigh") &&
        s.timber + jobs[c.job].timber >= (c.build === "none" ? 0 : 3);
    }
    if (s.phase === "night") return Boolean(c.post && c.tactic);
    return s.phase === "report";
  }

  function dispatch(s, event) {
    const clean = { type: event?.type, key: event?.key, value: event?.value };
    if (!apply(s, clean)) return false;
    s.history.push(clean);
    return true;
  }

  function serialize(s) {
    return JSON.stringify({ version: VERSION, moves: s.history });
  }

  function restore(text) {
    if (typeof text !== "string" || text.length > 50000) throw new Error("存档过大或为空。");
    const data = JSON.parse(text);
    if (data?.version !== VERSION || !Array.isArray(data.moves) || data.moves.length > 1000) {
      throw new Error("存档格式与这版灰模不兼容。");
    }
    const s = initial();
    for (const event of data.moves) {
      if (!dispatch(s, event)) throw new Error("存档中含无法重现的操作。");
    }
    return s;
  }

  const api = { initial, dispatch, canAdvance, serialize, restore, jobs, sectors, incidents };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PromisedWay = api;
})(globalThis);
