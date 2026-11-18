/* Тиммейт — мини-приложение для Telegram и MAX.
   Без сборки и зависимостей: один файл, работает в обоих мессенджерах.
   Визуальный стиль — как у презентации: сетка в обводках, узкие заголовки капсом с точкой.
   Весь пользовательский текст вставляется через textContent (см. el()), не через innerHTML. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- площадка

  const P = (function () {
    const name = window.__PLATFORM__ || "web";
    const tg = name === "tg" ? (window.Telegram && window.Telegram.WebApp) : null;
    const mx = name === "max" ? window.WebApp : null;
    const sdk = tg || mx || null;

    let initData = (sdk && sdk.initData) || "";
    if (name === "max" && !initData) {
      // Запасной путь: MAX кладёт данные во фрагмент URL — #WebAppData=…&WebAppPlatform=…
      const frag = new URLSearchParams((location.hash || "").replace(/^#/, ""));
      initData = frag.get("WebAppData") || "";
    }

    let backHandler = null;
    const safe = (fn) => { try { return fn(); } catch (e) { return undefined; } };
    const paint = () => {
      if (!tg) return;
      const dark = document.documentElement.dataset.theme === "dark";
      safe(() => tg.setHeaderColor && tg.setHeaderColor(dark ? "#111111" : "#FFFFFF"));
      safe(() => tg.setBackgroundColor && tg.setBackgroundColor(dark ? "#111111" : "#FFFFFF"));
    };

    return {
      name,
      initData,
      label: { tg: "Telegram", max: "MAX" }[name] || "браузер",
      other: { tg: "MAX", max: "Telegram" }[name] || "Telegram или MAX",
      devName: new URLSearchParams(location.search).get("dev") || "local",
      ready() {
        if (tg) {
          safe(() => tg.ready());
          safe(() => tg.expand());
          safe(() => tg.disableVerticalSwipes && tg.disableVerticalSwipes());
          if (tg.colorScheme) document.documentElement.dataset.theme = tg.colorScheme;
          paint();
          safe(() => tg.onEvent("themeChanged", () => { document.documentElement.dataset.theme = tg.colorScheme; paint(); }));
        }
        if (mx) safe(() => mx.ready && mx.ready());
      },
      setBack(fn) {
        if (!sdk || !sdk.BackButton) { backHandler = fn; return; }
        if (backHandler) safe(() => sdk.BackButton.offClick(backHandler));
        backHandler = fn || null;
        if (fn) { safe(() => sdk.BackButton.onClick(fn)); safe(() => sdk.BackButton.show()); }
        else safe(() => sdk.BackButton.hide());
      },
      haptic(kind) {
        const h = sdk && sdk.HapticFeedback;
        if (!h) return;
        safe(() => {
          let r;
          if (kind === "success" || kind === "error" || kind === "warning") r = h.notificationOccurred(kind);
          else if (kind === "select") r = h.selectionChanged();
          else r = h.impactOccurred(kind || "light");
          if (r && r.catch) r.catch(() => {});
        });
      },
      closingConfirmation(on) {
        if (!sdk) return;
        safe(() => on ? sdk.enableClosingConfirmation() : sdk.disableClosingConfirmation());
      },
      openLink(url) {
        const abs = new URL(url, location.href).href;
        if (sdk && sdk.openLink) safe(() => sdk.openLink(abs));
        else window.open(abs, "_blank", "noopener");
      },
      openMessengerLink(url) {
        // Ссылка на бота в мессенджере: внутри Telegram — t.me, внутри MAX — max.ru.
        if (tg && url.startsWith("https://t.me/") && tg.openTelegramLink) return safe(() => tg.openTelegramLink(url));
        if (mx && url.startsWith("https://max.ru/") && mx.openMaxLink) return safe(() => mx.openMaxLink(url));
        this.openLink(url);
      },
    };
  })();

  // ---------------------------------------------------------------- API

  class ApiError extends Error {
    constructor(status, data) {
      super((data && data.detail) || "Ошибка");
      this.status = status; this.errors = (data && data.errors) || {}; this.data = data || {};
    }
  }

  async function api(method, path, body) {
    const headers = { "X-Platform": P.name };
    headers.Authorization = P.name === "web" ? "dev " + P.devName : "tma " + P.initData;
    const init = { method, headers };
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    let res;
    try { res = await fetch(path, init); }
    catch (e) { throw new ApiError(0, { detail: "Нет соединения. Проверь интернет и попробуй ещё раз" }); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* пустой ответ */ }
    if (!res.ok) throw new ApiError(res.status, data);
    return data;
  }

  // ---------------------------------------------------------------- DOM-хелперы

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "style") node.style.cssText = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  const grid = (cls, ...cells) => el("div", { class: "grid " + (cls || "") }, ...cells);
  // cell("класс", {атрибуты}?, ...дети)
  const cell = (cls, ...children) => {
    const first = children[0];
    const attrs = first && typeof first === "object" && !(first instanceof Node) && !Array.isArray(first) ? children.shift() : {};
    return el("div", Object.assign({}, attrs, { class: "cell " + (cls || "") }), ...children);
  };
  const k = (text) => el("p", { class: "k", text });
  const pad2 = (n) => String(n).padStart(2, "0");

  const ICONS = {
    x: "M6 6l12 12M18 6L6 18",
    heart: "M12 21s-7.5-4.6-9.6-9.2C.9 8.3 3 4.5 6.7 4.5c2.1 0 3.6 1.1 4.3 2.4.7-1.3 2.2-2.4 4.3-2.4 3.7 0 5.8 3.8 4.3 7.3C19.5 16.4 12 21 12 21z",
    msg: "M3 5h18v12H8l-5 4z",
    copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  };
  function icon(name, filled) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", ICONS[name]);
    path.setAttribute("fill", filled ? "currentColor" : "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", filled ? "0" : "2.6");
    path.setAttribute("stroke-linecap", "square");
    svg.append(path);
    return svg;
  }

  const $app = document.getElementById("app");
  const $sheetRoot = document.getElementById("sheet-root");
  const $toast = document.getElementById("toast");

  function mount(...nodes) {
    document.querySelectorAll(".actions").forEach((n) => n.remove()); // панель ленты живёт только на ленте
    $app.replaceChildren(...nodes);
    window.scrollTo(0, 0);
  }
  // Перерисовка той же формы (выбрали чип, добавили интерес) — без прыжка наверх.
  function keepScroll(fn) { const y = window.scrollY; fn(); window.scrollTo(0, y); }

  let toastTimer = null;
  function toast(text) {
    $toast.textContent = text;
    $toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $toast.classList.remove("show"), 2600);
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const t = el("textarea", { style: "position:fixed;opacity:0" }); t.value = text;
      document.body.append(t); t.select(); try { document.execCommand("copy"); } catch (_) {} t.remove();
    }
    P.haptic("success");
    toast("Скопировано");
  }

  // Верхняя панель, как на слайдах: ТИММЕЙТ. | раздел | жёлтая ячейка.
  function bar(section, pg) {
    return grid("gt g-bar bar",
      cell("", el("p", { class: "brand", text: "Тиммейт." })),
      cell("", el("p", { class: "kick", text: section })),
      cell("pg", el("p", { class: "n", text: pg })),
    );
  }

  // Шторка снизу или окно по центру. Возвращает функцию закрытия.
  const sheetStack = [];
  let currentBack = null;
  function setBack(fn) { currentBack = fn; P.setBack(fn); }

  function openSheet(content, { center = false, onClose } = {}) {
    const sheet = el("div", { class: "sheet", role: "dialog", "aria-modal": "true" }, content);
    const overlay = el("div", { class: "overlay" + (center ? " center" : "") }, sheet);
    const prevBack = currentBack;
    let closed = false;
    const close = () => {
      if (closed) return; closed = true;
      overlay.remove();
      const i = sheetStack.indexOf(close); if (i >= 0) sheetStack.splice(i, 1);
      setBack(prevBack);
      if (onClose) onClose();
    };
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    $sheetRoot.append(overlay);
    sheetStack.push(close);
    setBack(close);
    return close;
  }
  function closeAllSheets() { while (sheetStack.length) sheetStack[sheetStack.length - 1](); }

  function confirmSheet({ title, text, ok, danger }) {
    return new Promise((resolve) => {
      let result = false;
      const close = openSheet(el("div", { class: "stack" },
        el("h2", { class: "display sm", text: title }),
        text ? el("p", { text }) : null,
        el("button", { class: "btn" + (danger ? " danger" : ""), text: ok, onclick: () => { result = true; close(); } }),
        el("button", { class: "btn white", text: "Отмена", onclick: () => close() }),
      ), { center: true, onClose: () => resolve(result) });
    });
  }

  // ---------------------------------------------------------------- состояние

  const S = {
    me: null, options: null,
    feed: [], feedRemaining: 0, feedSkipped: 0, feedLoaded: false,
    matches: null, tab: "feed", startHandled: false,
  };

  const initials = (name) => (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

  function avatar(p, cls) {
    const box = el("div", { class: "avatar" + tone(p) + (cls ? " " + cls : "") });
    if (p.photo_url) box.append(el("img", { src: p.photo_url, alt: "", loading: "lazy" }));
    else box.textContent = initials(p.name);
    return box;
  }

  function studyLine(p) {
    // Обычная фраза, а не строка через точки-разделители: «3 курс НГУ, бакалавриат».
    let s = [p.course ? p.course + " курс" : "", p.university || ""].filter(Boolean).join(" ");
    if (p.degree) s = s ? s + ", " + p.degree : p.degree;
    return s;
  }

  // Тон обложки и аватара: один и тот же человек всегда одного цвета.
  function tone(p) {
    const s = String((p && (p.user_id || p.name)) || "");
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 4;
    return " t" + (h + 1);
  }

  // Ссылки на документы и закон — для экрана согласия и раздела «Анкета».
  function legalLink(text, url) {
    return el("a", { href: url, text, onclick: (e) => { e.preventDefault(); e.stopPropagation(); P.openLink(url); } });
  }

  // ---------------------------------------------------------------- старт

  async function boot() {
    P.ready();
    try {
      S.me = await api("GET", "/api/me");
      S.options = S.me.options;
      // Локальная разработка (?dev=tg:1 / ?dev=max:1): подписи как в настоящем мессенджере.
      const pf = S.me.user.platform;
      if (P.name === "web" && (pf === "tg" || pf === "max")) {
        P.label = pf === "tg" ? "Telegram" : "MAX";
        P.other = pf === "tg" ? "MAX" : "Telegram";
      }
    } catch (e) {
      return renderFatal(e);
    }
    if (S.me.profile) renderMain("feed");
    else renderWelcome();
    // Открыли по ссылке «подключить мессенджер» (startapp=link-КОД).
    const sp = S.me.user.start_param || "";
    if (!S.startHandled && sp.startsWith("link-")) {
      S.startHandled = true;
      openLinkSheet(sp.slice(5));
    }
  }

  function renderFatal(e) {
    const outside = e.status === 401;
    mount(el("div", { class: "screen stack" },
      bar("Ошибка", "!"),
      grid("",
        cell("btm", el("h1", { class: "display md", text: outside ? "Открой в мессенджере." : "Не загрузилось." }),
          el("p", { text: outside
            ? "Тиммейт работает внутри Telegram и MAX — найди бота и нажми «Открыть»."
            : e.message })),
      ),
      outside ? null : el("button", { class: "btn", text: "Попробовать ещё раз", onclick: boot }),
    ));
  }

  // ---------------------------------------------------------------- приветствие и согласие (152-ФЗ)

  function renderWelcome() {
    setBack(null);
    const legal = S.me.legal;
    const consent = el("input", { type: "checkbox", id: "consent" });
    const go = el("button", { class: "btn", text: "Создать анкету", disabled: true });
    consent.addEventListener("change", () => { go.disabled = !consent.checked; P.haptic("select"); });
    go.addEventListener("click", () => {
      const u = S.me.user;
      startWizard({ name: u.first_name || "", username: u.username ? "@" + u.username : "", interests: [] });
    });
    const steps = [
      ["Анкета за 2 минуты", "Почти всё — кнопками."],
      ["Лента подходящих людей", "Под каждым — почему он тебе подходит."],
      ["Взаимный лайк — обмен контактами", "До этого контакт скрыт."],
    ];
    mount(el("div", { class: "screen stack" },
      el("div", {},
        bar("Сервис подбора сокомандников", P.name === "web" ? "W" : P.name.toUpperCase()),
        grid("",
          cell("btm", { style: "padding-top:40px" },
            el("h1", { class: "display xl", text: "Тиммейт" }),
            el("p", { class: "lead", text: "Сокомандники на хакатон, кейс-чемпионат или олимпиаду" }),
          ),
        ),
        grid("", ...steps.map(([t, s], i) => cell(i === 1 ? "blue" : "",
          el("div", { class: "row", style: "align-items:flex-start" },
            el("p", { class: "n", text: pad2(i + 1) }),
            el("div", { class: "grow" }, el("p", { class: "lead", text: t }), el("p", { text: s })),
          )))),
        grid("",
          cell("soft",
            el("label", { class: "check", for: "consent" }, consent,
              el("span", {},
                "Даю ", legalLink("согласие на обработку персональных данных", legal.consent_url),
                " по ", legalLink("Федеральному закону № 152-ФЗ «О персональных данных»", legal.law_url),
                " и принимаю ", legalLink("политику обработки", legal.privacy_url),
                ". Анкету увидят участники сервиса, контакт — только при взаимном лайке. Удалить данные можно в любой момент.",
              ),
            ),
          ),
        ),
      ),
      go,
      el("button", { class: "btn white", text: "У меня уже есть анкета в " + P.other, onclick: () => openLinkSheet("") }),
    ));
  }

  // ---------------------------------------------------------------- одна анкета на человека

  // Ввод кода из другого мессенджера: аккаунт подключается к уже существующей анкете.
  function openLinkSheet(prefill) {
    const input = el("input", { class: "input code-input", id: "f-code", maxlength: "12", autocomplete: "off",
      autocapitalize: "characters", placeholder: "XXXXXXXX", enterkeyhint: "done" });
    input.value = prefill || "";
    const errorBox = el("p", { class: "field error hidden" });
    const submit = el("button", { class: "btn", text: "Подключить" });
    const close = openSheet(el("div", { class: "stack" },
      el("h2", { class: "display md", text: "Код." }),
      el("p", { text: "Открой Тиммейт в " + P.other + " → «Анкета» → «Подключить " + P.label + "». Там будет код из 8 символов — введи его здесь. Код действует 10 минут." }),
      input, errorBox, submit,
    ));
    const run = async (replace) => {
      submit.disabled = true;
      try {
        await api("POST", "/api/link", { code: input.value, replace: !!replace });
        P.haptic("success");
        close();
        toast(P.label + " подключён к твоей анкете");
        S.feed = []; S.feedLoaded = false;
        await boot();
      } catch (e) {
        submit.disabled = false;
        if (e.data.code === "has_profile") {
          const ok = await confirmSheet({
            title: "Две анкеты?",
            text: "В " + P.label + " у тебя уже есть своя анкета. Чтобы осталась одна — удалим анкету из " + P.label +
              " (вместе с её лайками и мэтчами) и подключим тебя к анкете из " + P.other + ".",
            ok: "Удалить и подключить", danger: true,
          });
          if (ok) return run(true);
          return;
        }
        P.haptic("error");
        errorBox.textContent = e.message; errorBox.classList.remove("hidden");
      }
    };
    submit.addEventListener("click", () => run(false));
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(false); });
    if (!prefill) setTimeout(() => input.focus(), 250);
  }

  // Выдать код для подключения второго мессенджера к моей анкете.
  async function openCodeSheet() {
    let r;
    try { r = await api("POST", "/api/link/code"); } catch (e) { return toast(e.message); }
    openSheet(el("div", { class: "stack" },
      el("h2", { class: "display md", text: "Подключить " + P.other + "." }),
      el("p", { text: "Открой Тиммейт в " + P.other + " и на первом экране нажми «У меня уже есть анкета» — введи код. Лента, лайки и мэтчи станут общими, второй анкеты не будет." }),
      grid("gt", cell("yellow mid", { style: "align-items:center;padding:22px" },
        el("p", { class: "display md", style: "letter-spacing:4px", text: r.code }),
        el("p", { class: "k", text: "Действует 10 минут · одноразовый" }),
      )),
      el("button", { class: "btn white", text: "Скопировать код", onclick: () => copy(r.code) }),
      r.link ? el("button", { class: "btn", text: "Открыть " + P.other, onclick: () => P.openMessengerLink(r.link) }) : null,
    ));
  }

  // ---------------------------------------------------------------- поля анкеты

  const CITY_SUGGEST = ["Новосибирск", "Москва", "Санкт-Петербург", "Томск", "Екатеринбург", "Казань"];
  const UNI_SUGGEST = ["НГУ", "НГТУ", "СГУПС", "НГУЭУ", "СибГУТИ", "НГПУ", "НГМУ", "НГАУ"];
  const INTEREST_SUGGEST = ["python", "ML", "аналитика", "данные", "frontend", "backend", "мобильная разработка",
    "дизайн", "figma", "ui", "продукт", "маркетинг", "финансы", "экономика", "нейросети", "gamedev",
    "кибербезопасность", "выступления", "IT", "стартапы"];
  const MAX_INTERESTS = 10;

  // Каждое поле — функция (draft, errors, rerender) → элемент.
  function textField(key, label, { placeholder, hint, suggest, multiline, optional, inputmode } = {}) {
    return (d, errors) => {
      const limit = (S.options.limits || {})[key] || 200;
      const counter = el("div", { class: "counter" });
      const input = el(multiline ? "textarea" : "input", {
        class: "input", id: "f-" + key, placeholder: placeholder || "", maxlength: String(limit),
        autocomplete: "off", inputmode: inputmode || null, enterkeyhint: "next",
      });
      input.value = d[key] || "";
      const sync = () => { d[key] = input.value; counter.textContent = input.value.length + " / " + limit; };
      input.addEventListener("input", sync);
      sync();
      return el("div", { class: "field" + (errors[key] ? " invalid" : "") },
        el("label", { class: "k", for: "f-" + key, text: label + (optional ? " · необязательно" : "") }),
        input,
        suggest ? el("div", { class: "chips" }, suggest.map((s) =>
          el("button", { class: "chip", type: "button", "aria-pressed": String(d[key] === s), text: s,
            onclick: () => { input.value = s; sync(); P.haptic("select"); } }))) : null,
        errors[key] ? el("div", { class: "error", text: errors[key] }) : (hint ? el("div", { class: "hint", text: hint }) : null),
        multiline ? counter : null,
      );
    };
  }

  function choiceField(key, label, getOptions, { onPick } = {}) {
    return (d, errors, rerender) => el("div", { class: "field" + (errors[key] ? " invalid" : "") },
      el("div", { class: "k", text: label }),
      el("div", { class: "chips", role: "group" }, getOptions(d).map((o) => {
        const value = typeof o === "object" ? o.value : o;
        const text = typeof o === "object" ? o.label : cap(o);
        return el("button", {
          class: "chip", type: "button", text, "aria-pressed": String(d[key] === value),
          onclick: () => { d[key] = value; if (onPick) onPick(d, o); P.haptic("select"); rerender(); },
        });
      })),
      errors[key] ? el("div", { class: "error", text: errors[key] }) : null,
    );
  }

  function interestsField(d, errors, rerender) {
    d.interests = d.interests || [];
    const has = (x) => d.interests.some((i) => i.toLowerCase() === x.toLowerCase());
    const add = (raw) => {
      raw.split(/[,;\n]+/).map((s) => s.trim()).filter(Boolean).forEach((s) => {
        if (d.interests.length < MAX_INTERESTS && !has(s) && s.length <= 40) d.interests.push(s);
      });
    };
    const input = el("input", { class: "input", id: "f-interests", placeholder: "Например: python, Цифровой прорыв", enterkeyhint: "done", autocomplete: "off" });
    const commit = () => { if (input.value.trim()) { add(input.value); input.value = ""; P.haptic("select"); rerender("f-interests"); } };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); } });
    input.addEventListener("blur", () => { if (input.value.trim()) { add(input.value); input.value = ""; rerender(); } });
    return el("div", { class: "field" + (errors.interests ? " invalid" : "") },
      el("label", { class: "k", for: "f-interests", text: "Твои интересы · " + d.interests.length + " из " + MAX_INTERESTS }),
      d.interests.length ? el("div", { class: "chips" }, d.interests.map((t, i) =>
        el("span", { class: "tag" }, t, el("button", { type: "button", "aria-label": "Убрать " + t, text: "×",
          onclick: () => { d.interests.splice(i, 1); rerender(); } })))) : null,
      el("div", { class: "row" }, el("div", { class: "grow" }, input),
        el("button", { class: "btn sm black", type: "button", style: "min-height:52px", text: "+", "aria-label": "Добавить", onclick: commit })),
      errors.interests ? el("div", { class: "error", text: errors.interests }) : null,
      el("div", { class: "k", style: "margin-top:8px", text: "Популярное" }),
      el("div", { class: "chips" }, INTEREST_SUGGEST.filter((s) => !has(s)).map((s) =>
        el("button", { class: "chip add", type: "button", text: "+ " + s, disabled: d.interests.length >= MAX_INTERESTS,
          onclick: () => { add(s); P.haptic("select"); rerender(); } }))),
    );
  }

  const FIELDS = {
    name: textField("name", "Имя", { placeholder: "Как к тебе обращаться" }),
    city: textField("city", "Город", { placeholder: "Где ты сейчас живёшь", suggest: CITY_SUGGEST }),
    university: textField("university", "Вуз", { placeholder: "Например, НГУ", suggest: UNI_SUGGEST }),
    degree: choiceField("degree", "Уровень образования", () => S.options.degrees, {
      onPick: (d, o) => { if (d.course && d.course > o.max_course) d.course = null; },
    }),
    course: (d, errors, rerender) => {
      const deg = S.options.degrees.find((x) => x.value === d.degree);
      if (!deg) return null;
      const list = Array.from({ length: deg.max_course }, (_, i) => ({ value: i + 1, label: String(i + 1) }));
      return choiceField("course", "Курс", () => list)(d, errors, rerender);
    },
    direction: textField("direction", "Направление подготовки", { placeholder: "Например, Прикладная информатика" }),
    role: choiceField("role", "Твоя роль в команде", () => S.options.roles),
    looking_for: choiceField("looking_for", "Для чего ищешь команду", () => S.options.looking_for),
    interests: interestsField,
    about: textField("about", "О себе", { multiline: true, optional: true, placeholder: "Опыт, что умеешь, какую команду ищешь" }),
    github: textField("github", "GitHub", { optional: true, placeholder: "github.com/username", inputmode: "url" }),
    username: textField("username", "Контакт для связи", {
      placeholder: "@username, телефон или e-mail",
      hint: "Увидит только тот, с кем у тебя взаимный лайк",
    }),
  };

  const REQUIRED = ["name", "city", "university", "degree", "course", "direction", "role", "looking_for", "interests", "username"];

  function localErrors(d, keys) {
    const errors = {};
    keys.forEach((key) => {
      if (!REQUIRED.includes(key)) return;
      const v = d[key];
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length) || (typeof v === "string" && !v.trim())) {
        errors[key] = key === "interests" ? "Добавь хотя бы один интерес"
          : (["degree", "course", "role", "looking_for"].includes(key) ? "Выбери вариант" : "Заполни это поле");
      }
    });
    return errors;
  }

  function payload(d, extra) {
    const keys = ["name", "city", "university", "degree", "course", "direction", "role", "looking_for", "interests", "about", "github", "username"];
    const out = {};
    keys.forEach((key) => { out[key] = typeof d[key] === "string" ? d[key].trim() : d[key]; });
    return Object.assign(out, extra || {});
  }

  // Поля формы — ячейки сетки, как таблицы на слайдах.
  function fieldsGrid(keys, draft, errors, rerender, first) {
    const cells = keys.map((key) => FIELDS[key](draft, errors, rerender)).filter(Boolean).map((f) => cell("", f));
    return grid(first ? "gt" : "", ...cells);
  }

  // ---------------------------------------------------------------- визард

  const STEPS = [
    { title: "Имя.", sub: "Имя и город увидят другие участники", fields: ["name", "city"] },
    { title: "Учёба.", sub: "Помогает искать людей из своего вуза", fields: ["university", "degree", "course", "direction"] },
    { title: "Команда.", sub: "Разработчику подбираем аналитиков, дизайнеров, экономистов — и наоборот", fields: ["role", "looking_for"] },
    { title: "Интересы.", sub: "Темы и конкретные соревнования. Чем больше общих — тем выше человек в ленте", fields: ["interests"] },
    { title: "О себе.", sub: "Можно пропустить, но с описанием лайкают чаще", fields: ["about", "github"] },
    { title: "Контакт.", sub: "Откроется только при взаимном лайке", fields: ["username"] },
    { title: "Проверка.", sub: "Так тебя увидят в ленте", fields: [] },
  ];

  function startWizard(draft) {
    P.closingConfirmation(true);
    let step = 0;
    let errors = {};

    const save = async (next, extra) => {
      next.disabled = true;
      try {
        await api("PUT", "/api/profile", payload(draft, Object.assign({ consent: true }, extra)));
        P.closingConfirmation(false);
        P.haptic("success");
        S.me = await api("GET", "/api/me");
        renderPhotoStep();
      } catch (e) {
        next.disabled = false;
        if (e.status === 409 && e.data.code === "duplicate") return duplicateSheet(e.data, () => save(next, { force_new: true }));
        if (e.status === 422 && e.errors) {
          errors = e.errors;
          const first = STEPS.findIndex((st) => st.fields.some((f) => errors[f]));
          if (first >= 0) step = first;
          P.haptic("error");
          toast(e.message);
          return render();
        }
        toast(e.message);
      }
    };

    const render = (focusId) => {
      const s = STEPS[step];
      setBack(step === 0 ? renderWelcome : () => { step -= 1; errors = {}; render(); });
      const isLast = step === STEPS.length - 1;
      const next = el("button", { class: "btn", text: isLast ? "Сохранить анкету" : "Далее →" });
      next.addEventListener("click", () => {
        if (isLast) return save(next);
        errors = localErrors(draft, s.fields);
        if (Object.keys(errors).length) { P.haptic("error"); return render(); }
        step += 1; errors = {}; render();
      });
      const body = s.fields.length
        ? fieldsGrid(s.fields, draft, errors, (id) => keepScroll(() => render(id)), true)
        : profileCard(previewProfile(draft), { mine: true });
      mount(el("div", { class: "screen stack" },
        el("div", {},
          bar("Анкета", (step + 1) + "/" + STEPS.length),
          el("div", { class: "progress", style: "border-top:0" }, el("i", { style: "width:" + Math.round(((step + 1) / STEPS.length) * 100) + "%" })),
        ),
        el("div", { class: "stack", style: "padding:18px 0 4px; gap:8px" },
          el("h1", { class: "display", text: s.title }),
          el("p", { class: "sub", text: s.sub }),
        ),
        body,
        el("div", { class: "form-footer stack", style: "gap:8px" },
          next,
          step > 0 ? el("button", { class: "btn text", text: "← Назад", onclick: () => { step -= 1; errors = {}; render(); } }) : null,
        ),
      ));
      if (focusId) { const f = document.getElementById(focusId); if (f) f.focus(); }
    };
    render();
  }

  // Анкета с тем же контактом уже есть в другом мессенджере.
  function duplicateSheet(info, forceSave) {
    P.haptic("warning");
    const close = openSheet(el("div", { class: "stack" },
      el("h2", { class: "display md", text: "Уже с нами?" }),
      el("p", {}, "В ", el("b", { text: info.platform }), " есть анкета с тем же контактом ",
        el("b", { text: info.contact }), ". Чтобы не было двух анкет, подключи её: в " + info.platform +
        " открой Тиммейт → «Анкета» → «Подключить " + P.label + "» и введи код здесь."),
      el("button", { class: "btn", text: "Ввести код", onclick: () => { close(); openLinkSheet(""); } }),
      el("button", { class: "btn white", text: "Это не я — создать анкету", onclick: () => { close(); forceSave(); } }),
    ), { center: true });
  }

  function previewProfile(d) {
    return {
      name: (d.name || "").trim(), university: d.university, degree: d.degree, course: d.course,
      direction: d.direction, city: d.city, role: d.role, looking_for: d.looking_for,
      interests: d.interests || [], about: d.about, github: d.github, contact: d.username, photo_url: d.photo_url || "",
    };
  }

  function renderPhotoStep() {
    setBack(null);
    const p = S.me.profile;
    const pick = photoPicker(() => renderPhotoStep());
    mount(el("div", { class: "screen stack" },
      el("div", {},
        bar("Анкета", "✓"),
        grid("",
          cell("btm", { style: "padding-top:32px" },
            el("h1", { class: "display xl", text: "Готово." }),
            el("p", { class: "lead", text: "Анкета сохранена" }),
          ),
        ),
        grid("g-bar",
          cell("blue mid", avatar(p, "xl")),
          cell("mid", el("p", { text: "Добавь фото — анкеты с фото лайкают охотнее. Можно сделать позже." })),
        ),
      ),
      el("button", { class: "btn" + (p.photo_url ? " white" : " yellow"), text: p.photo_url ? "Другое фото" : "Добавить фото", onclick: pick }),
      el("button", { class: "btn" + (p.photo_url ? "" : " white"), text: p.photo_url ? "К ленте →" : "Пропустить →", onclick: () => renderMain("feed") }),
    ));
  }

  function photoPicker(after) {
    return () => {
      const input = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", style: "display:none" });
      input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        input.remove();
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) return toast("Фото больше 5 МБ");
        const fd = new FormData(); fd.append("file", file);
        toast("Загружаю фото…");
        try {
          const r = await api("POST", "/api/profile/photo", fd);
          S.me.profile.photo_url = r.photo_url;
          P.haptic("success");
          toast("Фото обновлено");
          after();
        } catch (e) { toast(e.message); }
      });
      document.body.append(input);
      input.click();
    };
  }

  // ---------------------------------------------------------------- карточка анкеты

  function profileCard(p, { reasons, explainText, mine, contact } = {}) {
    const shared = new Set(((reasons && reasons.shared_interests) || []).map((x) => x.toLowerCase()));
    const cover = cell("blue cover" + tone(p));
    if (p.photo_url) cover.append(el("img", { src: p.photo_url, alt: "", draggable: "false" }));
    else cover.append(el("div", { class: "initials", text: initials(p.name) }));

    const why = [];
    if (reasons) {
      if (reasons.shared_interests && reasons.shared_interests.length) why.push("общие темы: " + reasons.shared_interests.join(", "));
      if (reasons.same_goal) why.push("ищете одно и то же");
      if (reasons.complementary_roles) why.push("роли дополняют друг друга");
      if (reasons.same_city) why.push("один город");
      if (!why.length) why.push(explainText || "пока мало общего");
    }
    const pair = (a, b) => grid("g2", a, b);
    const info = (label, value, cls) => cell(cls || "", k(label), el("p", { class: "v", text: value || "—" }));

    return el("article", { class: "pcard" },
      grid("gt", cover),
      grid("", cell("", el("h2", { class: "display md", text: (p.name || "Без имени") + "." }),
        studyLine(p) ? el("p", { class: "sub", text: studyLine(p) }) : null)),
      pair(info("Роль", p.role), info("Ищет", cap(p.looking_for), "yellow")),
      (p.direction || p.city) ? pair(info("Направление", p.direction), info("Город", p.city)) : null,
      reasons ? grid("", cell("black", k("Почему подходит"),
        el("div", { class: "reasons" }, why.map((w) => el("div", { text: w }))))) : null,
      p.interests && p.interests.length ? grid("", cell("", k("Интересы"),
        el("div", { class: "chips" }, p.interests.map((t) =>
          el("span", { class: "tag" + (shared.has(t.toLowerCase()) ? " shared" : ""), text: t }))))) : null,
      p.about ? grid("", cell("", k("О себе"), el("p", { class: "about", text: p.about }))) : null,
      p.github ? grid("", cell("", k("GitHub"), el("a", { href: p.github, class: "v", text: p.github.replace(/^https?:\/\//, ""),
        onclick: (e) => { e.preventDefault(); P.openLink(p.github); } }))) : null,
      (contact || mine) && p.contact ? contactGrid(p) : null,
    );
  }

  function contactGrid(p, standalone) {
    const c = (p.contact || "").trim();
    const nick = /^@?([A-Za-z0-9_]{5,32})$/.exec(c);
    const canOpenTg = nick && P.name === "tg";
    return grid(standalone ? "gt" : "", cell("blue contact",
      k("Контакт"),
      el("div", { class: "row" },
        el("p", { class: "value grow", text: c }),
        canOpenTg ? el("button", { class: "btn sm black", text: "Написать", onclick: () => P.openMessengerLink("https://t.me/" + nick[1]) }) : null,
        el("button", { class: "icon-btn", "aria-label": "Скопировать контакт", onclick: () => copy(c) }, icon("copy")),
      ),
    ));
  }

  // ---------------------------------------------------------------- основной экран

  function renderMain(tab) {
    closeAllSheets();
    P.closingConfirmation(false);
    S.tab = tab || S.tab;
    setBack(null);
    const content = el("div", { class: "screen with-tabs stack" });
    const tabs = [["feed", "Лента"], ["matches", "Мэтчи"], ["profile", "Анкета"]];
    const stats = S.me.stats || {};
    const tabbar = el("nav", { class: "tabbar" }, grid("g3", tabs.map(([id, label]) =>
      cell(S.tab === id ? "on" : "",
        el("button", { class: "tab", "aria-current": S.tab === id ? "page" : null, text: label,
          onclick: () => { if (S.tab !== id) { P.haptic("select"); renderMain(id); } } }),
        id === "matches" && stats.matches ? el("span", { class: "badge", text: String(stats.matches) }) : null,
      ))));
    mount(content, tabbar);
    if (S.tab === "feed") renderFeed(content);
    else if (S.tab === "matches") renderMatches(content);
    else renderProfile(content);
  }

  async function refreshMe() {
    try { S.me = await api("GET", "/api/me"); } catch (e) { /* не критично */ }
  }

  // ---------------------------------------------------------------- лента

  const MODES = [["all", "Все"], ["university", "Мой вуз"], ["city", "Мой город"]];

  async function loadFeed() {
    const r = await api("GET", "/api/feed");
    const known = new Set(S.feed.map((i) => i.profile.id));
    S.feed = S.feed.concat(r.items.filter((i) => !known.has(i.profile.id)));
    S.feedRemaining = r.remaining;
    S.feedSkipped = r.skipped;
    S.me.search_mode = r.search_mode;
    S.feedLoaded = true;
  }

  async function setMode(mode) {
    if (S.me.search_mode === mode) return;
    P.haptic("select");
    try {
      await api("PUT", "/api/settings", { search_mode: mode });
      S.me.search_mode = mode; S.feed = []; S.feedLoaded = false;
      renderMain("feed");
    } catch (e) { toast(e.message); }
  }

  async function renderFeed(root) {
    const counter = el("p", { class: "n", text: "…" });
    const head = grid("gt g-bar bar",
      cell("", el("p", { class: "brand", text: "Тиммейт." })),
      cell("", el("p", { class: "kick", text: "Лента" })),
      cell("pg", counter),
    );
    const filters = grid("g3 filters", MODES.map(([mode, label]) =>
      cell(S.me.search_mode === mode ? "on" : "",
        el("button", { "aria-pressed": String(S.me.search_mode === mode), text: label, onclick: () => setMode(mode) }))));
    const incoming = (S.me.stats || {}).incoming_likes || 0;
    const slot = el("div", {});
    root.append(
      el("div", {}, head, filters,
        incoming ? grid("", cell("yellow", el("p", { class: "lead", text: "Тебя лайкнули: " + incoming }),
          el("p", { text: "Они уже в ленте — лайкни в ответ, и будет мэтч." }))) : null),
      slot,
    );
    root.classList.add("with-actions");
    if (!S.feedLoaded) {
      slot.append(grid("", cell("", el("p", { class: "lead", text: "Подбираю людей…" }))));
      try { await loadFeed(); } catch (e) { slot.replaceChildren(grid("", cell("", el("p", { text: e.message })))); return; }
    }
    drawTop(slot, counter);
  }

  function drawTop(slot, counter) {
    const left = S.feed.length + S.feedRemaining;
    if (counter) counter.textContent = String(left);
    const old = document.querySelector(".actions");
    if (old) old.remove();
    const item = S.feed[0];
    if (!item) { slot.closest(".screen") && slot.closest(".screen").classList.remove("with-actions"); return slot.replaceChildren(feedEmpty()); }

    const card = profileCard(item.profile, { reasons: item.reasons, explainText: item.explain });
    card.classList.add("swipe");
    const stampLike = el("div", { class: "stamp like", text: "Лайк" });
    const stampNope = el("div", { class: "stamp nope", text: "Пропуск" });
    card.append(stampLike, stampNope);
    attachSwipe(card, stampLike, stampNope, (dir) => act(dir === "right" ? "like" : "skip"));

    let busy = false;
    async function act(kind, message) {
      if (busy) return;
      busy = true;
      const out = kind === "skip" ? -1 : 1;
      card.style.transform = "translateX(" + out * 120 + "%) rotate(" + out * 8 + "deg)";
      card.style.opacity = "0";
      P.haptic(kind === "skip" ? "light" : "medium");
      try {
        const r = await api("POST", "/api/swipe", { to_id: item.profile.id, action: kind === "skip" ? "skip" : "like", message: message || "" });
        S.feed.shift();
        if (S.feed.length < 3 && S.feedRemaining > 0) loadFeed().catch(() => {});
        if (!S.feed.length) { try { await loadFeed(); } catch (e) { /* покажем пустую ленту */ } }
        // После мэтча перерисовываем экран целиком — чтобы обновился счётчик на вкладке «Мэтчи».
        if (r.matched) { await refreshMe(); showMatch(r.partner, () => { if (S.tab === "feed" && slot.isConnected) renderMain("feed"); }); }
        else drawTop(slot, counter);
      } catch (e) {
        if (e.status === 404) { S.feed.shift(); drawTop(slot, counter); return; }
        card.style.transform = ""; card.style.opacity = "";
        busy = false;
        toast(e.message);
      }
    }

    const actions = el("div", { class: "actions" }, grid("g3",
      cell("", el("button", { "aria-label": "Пропустить", onclick: () => act("skip") }, icon("x"), "Пропуск")),
      cell("yellow", el("button", { "aria-label": "Лайк с сообщением", onclick: () => askMessage(item.profile, (m) => act("like", m)) }, icon("msg"), "Письмо")),
      cell("blue", el("button", { "aria-label": "Лайк", onclick: () => act("like") }, icon("heart", true), "Лайк")),
    ));
    slot.replaceChildren(card);
    document.body.append(actions);
  }

  function attachSwipe(card, stampLike, stampNope, onSwipe) {
    let startX = 0, startY = 0, dx = 0, active = false, horizontal = null;
    card.addEventListener("pointerdown", (e) => {
      if (e.target.closest("a,button")) return;
      active = true; horizontal = null; startX = e.clientX; startY = e.clientY; dx = 0;
    });
    card.addEventListener("pointermove", (e) => {
      if (!active) return;
      const mx = e.clientX - startX, my = e.clientY - startY;
      if (horizontal === null && (Math.abs(mx) > 8 || Math.abs(my) > 8)) {
        horizontal = Math.abs(mx) > Math.abs(my);
        if (horizontal) { card.setPointerCapture(e.pointerId); card.classList.add("dragging"); }
      }
      if (!horizontal) return;
      dx = mx;
      card.style.transform = "translateX(" + dx + "px) rotate(" + dx / 30 + "deg)";
      stampLike.style.opacity = String(Math.max(0, Math.min(1, dx / 90)));
      stampNope.style.opacity = String(Math.max(0, Math.min(1, -dx / 90)));
    });
    const end = () => {
      if (!active) return;
      active = false;
      card.classList.remove("dragging");
      if (horizontal && Math.abs(dx) > 110) { onSwipe(dx > 0 ? "right" : "left"); return; }
      card.style.transform = ""; stampLike.style.opacity = "0"; stampNope.style.opacity = "0";
    };
    card.addEventListener("pointerup", end);
    card.addEventListener("pointercancel", end);
  }

  function feedEmpty() {
    if (S.me.search_mode !== "all") {
      return el("div", { class: "stack" }, grid("",
        cell("btm", { style: "padding-top:28px" }, el("h2", { class: "display md", text: "Пусто." }),
          el("p", { text: "По этому фильтру анкет пока нет. Покажи всех — подбор всё равно отсортирует людей по совместимости." }))),
        el("button", { class: "btn", text: "Показать всех", onclick: () => setMode("all") }));
    }
    return el("div", { class: "stack" }, grid("",
      cell("btm", { style: "padding-top:28px" }, el("h2", { class: "display md", text: "Всё." }),
        el("p", { text: S.feedSkipped
          ? "Подходящие анкеты закончились. Ты пропустил(а) " + S.feedSkipped + " — можно пройтись по ним ещё раз. Лайкнутых не покажем: если ответят взаимностью, придёт мэтч."
          : "Подходящие анкеты закончились. Загляни позже — появятся новые люди. А пока позови в Тиммейт однокурсников." }))),
      S.feedSkipped ? el("button", { class: "btn yellow", text: "Посмотреть пропущенных", onclick: async () => {
        try { await api("POST", "/api/feed/reset-skips"); S.feed = []; S.feedLoaded = false; renderMain("feed"); }
        catch (e) { toast(e.message); }
      } }) : null);
  }

  function askMessage(p, send) {
    const limit = (S.options.limits || {}).message || 300;
    const input = el("textarea", { class: "input", maxlength: String(limit), placeholder: "Привет! Ищу дизайнера на «Цифровой прорыв», пойдёшь в команду?" });
    const counter = el("div", { class: "counter", text: "0 / " + limit });
    input.addEventListener("input", () => { counter.textContent = input.value.length + " / " + limit; });
    const close = openSheet(el("div", { class: "stack" },
      el("h2", { class: "display md", text: "Письмо." }),
      el("p", { text: (p.name || "Участник") + " увидит его, когда лайкнет тебя в ответ. Ссылки нельзя — контакты придут обоим при мэтче." }),
      el("div", { class: "field" }, input, counter),
      el("button", { class: "btn", text: "Отправить лайк", onclick: () => {
        const text = input.value.trim();
        if (!text) { toast("Напиши пару слов или просто поставь лайк"); return; }
        close(); send(text);
      } }),
    ));
    setTimeout(() => input.focus(), 250);
  }

  function showMatch(partner, onContinue) {
    P.haptic("success");
    const old = document.querySelector(".actions"); if (old) old.remove();
    const close = openSheet(el("div", { class: "stack" },
      grid("gt g-bar",
        cell("blue btm", { style: "padding-top:26px" }, el("h1", { class: "display xl", text: "Мэтч." })),
        cell("mid", { style: "align-items:center" }, avatar(S.me.profile), avatar(partner)),
      ),
      el("p", { text: "Вы с " + partner.name + " лайкнули друг друга. Напиши первым — договоритесь о команде." }),
      partner.contact ? contactGrid(partner, true) : el("p", { class: "sub", text: "Контакт не указан." }),
      el("button", { class: "btn", text: "Смотреть дальше →", onclick: () => close() }),
      el("button", { class: "btn white", text: "Все мэтчи", onclick: () => { close(); renderMain("matches"); } }),
    ), { center: true, onClose: onContinue });
    return close;
  }

  // ---------------------------------------------------------------- мэтчи

  async function renderMatches(root) {
    const counter = el("p", { class: "n", text: String((S.me.stats || {}).matches || 0) });
    root.append(el("div", {},
      grid("gt g-bar bar", cell("", el("p", { class: "brand", text: "Тиммейт." })),
        cell("", el("p", { class: "kick", text: "Мэтчи" })), cell("pg", counter)),
      grid("", cell("btm", { style: "padding-top:24px" }, el("h1", { class: "display", text: "Мэтчи." }),
        el("p", { class: "sub", text: "Взаимные лайки. Контакт открыт — напиши первым." }))),
    ));
    const slot = el("div", {}, grid("", cell("", el("p", { class: "lead", text: "Загружаю…" }))));
    root.append(slot);
    try {
      const r = await api("GET", "/api/matches");
      S.matches = r.items;
    } catch (e) { slot.replaceChildren(grid("", cell("", el("p", { text: e.message })))); return; }
    counter.textContent = String(S.matches.length);
    if (!S.matches.length) {
      slot.replaceChildren(el("div", { class: "stack" },
        grid("", cell("soft", el("p", { class: "lead", text: "Пока мэтчей нет" }),
          el("p", { text: "Лайкай анкеты в ленте. Когда интерес взаимный — здесь появится контакт." }))),
        el("button", { class: "btn", text: "Открыть ленту", onclick: () => renderMain("feed") }),
      ));
      return;
    }
    slot.replaceChildren(grid("", S.matches.map((m, i) => el("div", { class: "cell item", role: "button", tabindex: "0",
      onclick: () => openMatch(m), onkeydown: (e) => { if (e.key === "Enter") openMatch(m); } },
      el("p", { class: "n", text: pad2(i + 1) }),
      avatar(m.profile),
      el("div", { class: "grow" },
        el("p", { class: "title", text: m.profile.name }),
        el("p", { class: "meta", text: [m.profile.role, m.profile.university].filter(Boolean).join(" · ") }),
        el("p", { class: "meta", text: m.their_message ? "✉ " + m.their_message : (m.profile.contact || "") }),
      ),
    ))));
  }

  function openMatch(m) {
    openSheet(el("div", { class: "stack" },
      m.their_message ? grid("gt", cell("yellow", k("Письмо от " + m.profile.name), el("p", { class: "about", text: m.their_message }))) : null,
      profileCard(m.profile, { contact: true }),
    ));
  }

  // ---------------------------------------------------------------- моя анкета

  function renderProfile(root) {
    const p = S.me.profile;
    const legal = S.me.legal;
    const linked = new Set(S.me.linked || []);
    const otherKey = S.me.user.platform === "max" ? "tg" : "max";
    const visible = el("input", { type: "checkbox", id: "visible" });
    visible.checked = !!p.is_active;
    visible.addEventListener("change", async () => {
      try {
        const r = await api("POST", "/api/profile/visibility", { active: visible.checked });
        p.is_active = r.is_active;
        P.haptic("select");
        toast(r.is_active ? "Анкета снова видна в ленте" : "Анкета скрыта: другие тебя не увидят");
      } catch (e) { visible.checked = !visible.checked; toast(e.message); }
    });
    const messenger = (key, name) => cell(linked.has(key) ? "" : "soft",
      k(name),
      el("p", { class: "lead", text: linked.has(key) ? "Подключён ✓" : "Не подключён" }),
      !linked.has(key) && key === otherKey
        ? el("button", { class: "btn sm yellow", style: "width:100%", text: "Подключить", onclick: openCodeSheet }) : null,
    );

    // Node.append, в отличие от el(), печатает null как текст — пропуски отфильтровываем.
    root.append(...[
      el("div", {},
        bar("Моя анкета", p.is_active ? "ON" : "OFF"),
        grid("", cell("btm", { style: "padding-top:24px" }, el("h1", { class: "display", text: "Анкета." }))),
      ),
      profileCard(p, { mine: true }),
      grid("gt g2",
        cell("", el("button", { class: "btn", text: "Изменить", onclick: openEditor })),
        cell("", el("button", { class: "btn white", text: p.photo_url ? "Сменить фото" : "Добавить фото", onclick: photoPicker(() => renderMain("profile")) })),
      ),
      grid("gt",
        cell("", el("label", { class: "check", for: "visible" }, visible,
          el("span", {}, el("b", { text: "Показывать меня в ленте. " }), "Выключи, если команда уже собрана."))),
      ),
      el("div", {},
        grid("gt", cell("black", el("p", { class: "lead", text: "Мессенджеры" }),
          el("p", { text: "Одна анкета на оба мессенджера: лента, лайки и мэтчи общие." }))),
        grid("g2", messenger("tg", "Telegram"), messenger("max", "MAX")),
      ),
      grid("gt",
        cell("", k("Документы"),
          el("p", {}, legalLink("Согласие на обработку ПД", legal.consent_url)),
          el("p", {}, legalLink("Политика обработки ПД", legal.privacy_url)),
          el("p", {}, legalLink("Закон № 152-ФЗ «О персональных данных»", legal.law_url)),
        ),
      ),
      p.photo_url ? el("button", { class: "btn white", text: "Убрать фото", onclick: async () => {
        try { await api("DELETE", "/api/profile/photo"); p.photo_url = ""; renderMain("profile"); } catch (e) { toast(e.message); }
      } }) : null,
      el("button", { class: "btn white", text: "Пожаловаться / ошибка", onclick: () => {
        openSheet(el("div", { class: "stack" },
          el("h2", { class: "display md", text: "Жалоба." }),
          el("p", { text: "Неприемлемая анкета, спам или ошибка? Напиши нам — укажи имя из анкеты и что случилось. Разберёмся и при необходимости скроем анкету." }),
          grid("gt", cell("yellow", el("div", { class: "row" }, el("p", { class: "v grow", text: S.me.report_email }),
            el("button", { class: "icon-btn", "aria-label": "Скопировать адрес", onclick: () => copy(S.me.report_email) }, icon("copy"))))),
        ));
      } }),
      el("button", { class: "btn danger", text: "Удалить мои данные", onclick: async () => {
        const ok = await confirmSheet({ title: "Удалить всё?",
          text: "Анкета, фото, лайки, мэтчи и привязки мессенджеров будут удалены везде — в Telegram и в MAX. Восстановить нельзя.",
          ok: "Да, удалить всё", danger: true });
        if (!ok) return;
        try {
          await api("DELETE", "/api/profile");
          P.haptic("warning");
          S.feed = []; S.feedLoaded = false; S.matches = null;
          await boot();
          toast("Все твои данные удалены");
        } catch (e) { toast(e.message); }
      } }),
    ].filter(Boolean));
  }

  function openEditor() {
    const p = S.me.profile;
    const draft = {
      name: p.name, city: p.city, university: p.university, degree: p.degree, course: p.course,
      direction: p.direction, role: p.role, looking_for: p.looking_for, interests: (p.interests || []).slice(),
      about: p.about, github: p.github, username: p.contact,
    };
    let errors = {};
    P.closingConfirmation(true);
    const sections = [
      ["Основное", ["name", "city"]],
      ["Учёба", ["university", "degree", "course", "direction"]],
      ["Команда", ["role", "looking_for"]],
      ["Интересы", ["interests"]],
      ["О себе", ["about", "github"]],
      ["Контакт", ["username"]],
    ];
    const render = (focusId) => {
      setBack(() => renderMain("profile"));
      const save = el("button", { class: "btn", text: "Сохранить" });
      save.addEventListener("click", async () => {
        errors = localErrors(draft, REQUIRED);
        if (Object.keys(errors).length) { P.haptic("error"); toast("Проверь отмеченные поля"); return render(); }
        save.disabled = true;
        try {
          await api("PUT", "/api/profile", payload(draft));
          await refreshMe();
          S.feed = []; S.feedLoaded = false;
          P.haptic("success");
          toast("Изменения сохранены");
          renderMain("profile");
        } catch (e) {
          save.disabled = false;
          if (e.status === 422 && e.errors) { errors = e.errors; P.haptic("error"); toast(e.message); return render(); }
          toast(e.message);
        }
      });
      const rerender = (id) => keepScroll(() => render(id));
      mount(el("div", { class: "screen stack" },
        el("div", {},
          bar("Редактирование", "✎"),
          grid("", cell("btm", { style: "padding-top:24px" }, el("h1", { class: "display", text: "Правка." }))),
        ),
        sections.map(([title, keys]) => el("section", {},
          grid("gt", cell("black", el("p", { class: "lead", text: title }))),
          fieldsGrid(keys, draft, errors, rerender, false),
        )),
        el("div", { class: "form-footer stack", style: "gap:8px" },
          save,
          el("button", { class: "btn text", text: "Отмена", onclick: () => renderMain("profile") }),
        ),
      ));
      if (focusId) { const f = document.getElementById(focusId); if (f) f.focus(); }
    };
    render();
  }

  boot();
})();
