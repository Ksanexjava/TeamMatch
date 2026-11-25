/**
 * Ретранслятор мини-приложения на Cloudflare Workers.
 *
 * Зачем. Сервер стоит на российском IP, и часть пользователей до него не
 * доходит: у кого включён VPN, тот упирается в стену — сам мессенджер
 * работает, а встроенный браузер не может открыть наш домен. Этот скрипт
 * принимает запросы на адрес вида https://имя.поддомен.workers.dev и
 * передаёт их на наш сервер, отдавая ответ обратно.
 *
 * Чем за это платим. TLS обрывается на стороне Cloudflare: платформа видит
 * содержимое запросов, включая анкеты. Сейчас в базе только тестовые данные,
 * поэтому это приемлемо. Перед пилотом с живыми людьми ретранслятор надо
 * убрать, а сервис перенести на хостинг, доступный напрямую.
 *
 * Уже выложен как воркер teammate-app, адрес:
 *   https://teammate-app.michael-biysk.workers.dev
 *
 * Если понадобится развернуть заново: Cloudflare → Workers & Pages → Create →
 * Start with Hello World, имя teammate-app, затем Edit code и вставить этот
 * файл целиком. Адрес прописывается на сервере в TELEGRAM_WEBAPP_URL и в
 * @BotFather → Bot Settings → Menu Button.
 *
 * MAX оставляем на прямом домене: мини-приложение там уже прошло модерацию
 * платформы, и смена адреса потребовала бы её заново.
 */

const ORIGIN = "https://teammatensu.ru";

// Редактор мероприятий через ретранслятор не пускаем: он защищён токеном,
// но незачем выставлять его ещё и наружу. Открывается по прямому адресу.
const BLOCKED = ["/admin", "/api/admin"];

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (BLOCKED.some((p) => url.pathname === p || url.pathname.startsWith(p + "/"))) {
      return new Response("Not found", { status: 404 });
    }

    const headers = new Headers(request.headers);
    // Host подставит сам fetch по адресу назначения.
    headers.delete("Host");
    // Чтобы сервер видел настоящего посетителя, а не узел Cloudflare.
    const ip = request.headers.get("CF-Connecting-IP");
    if (ip) headers.set("X-Forwarded-For", ip);
    headers.set("X-Forwarded-Proto", "https");

    const noBody = request.method === "GET" || request.method === "HEAD";
    let upstream;
    try {
      upstream = await fetch(ORIGIN + url.pathname + url.search, {
        method: request.method,
        headers,
        // Анкеты и фотографии невелики: читаем тело целиком, так надёжнее потока.
        body: noBody ? undefined : await request.arrayBuffer(),
        redirect: "manual",
      });
    } catch (e) {
      // Понятный текст вместо пустой страницы, если сервер не отвечает.
      return new Response(
        "Сервер Тиммейта не отвечает: " + ((e && e.message) || "нет соединения"),
        { status: 502, headers: { "Content-Type": "text/plain; charset=utf-8" } },
      );
    }

    const out = new Headers(upstream.headers);
    // Переадресация не должна уводить человека с ретранслятора на прямой домен.
    const loc = out.get("Location");
    if (loc && loc.startsWith(ORIGIN)) out.set("Location", url.origin + loc.slice(ORIGIN.length));
    // Ответы приложения не кэшируем: лента и анкеты у каждого свои.
    if (url.pathname.startsWith("/api/")) {
      out.set("Cache-Control", "no-store");
    }

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: out,
    });
  },
};
